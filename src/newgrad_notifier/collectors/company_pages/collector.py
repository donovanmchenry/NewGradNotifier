"""Company careers page collector."""

from __future__ import annotations

import re
from urllib.parse import urljoin

from newgrad_notifier.collectors.ats.ashby import AshbyCollector
from newgrad_notifier.collectors.ats.greenhouse import GreenhouseCollector
from newgrad_notifier.collectors.ats.lever import LeverCollector
from newgrad_notifier.collectors.ats.smartrecruiters import SmartRecruitersCollector
from newgrad_notifier.collectors.ats.base import ATSBoardCollector
from newgrad_notifier.collectors.base import Collector, CollectorContext
from newgrad_notifier.collectors.parsers import extract_jobs_from_html
from newgrad_notifier.config.company_loader import load_company_list
from newgrad_notifier.config.settings import ATSBoardConfig
from newgrad_notifier.contracts import CollectedJob, PipelineError, SourceType

ATS_DISCOVERY_PATTERNS: dict[str, re.Pattern[str]] = {
    "greenhouse": re.compile(r"https?://(?:boards|job-boards)\.greenhouse\.io/([A-Za-z0-9_-]+)", re.IGNORECASE),
    "lever": re.compile(r"https?://jobs\.lever\.co/([A-Za-z0-9_-]+)", re.IGNORECASE),
    "ashby": re.compile(r"https?://jobs\.ashbyhq\.com/([A-Za-z0-9_-]+)", re.IGNORECASE),
    "smartrecruiters": re.compile(r"https?://jobs\.smartrecruiters\.com/([A-Za-z0-9_-]+)", re.IGNORECASE),
}


class CompanyPagesCollector(Collector):
    """Scan configured career pages for direct job postings."""

    name = "company_pages"

    def __init__(self, company_list_path: str | None = None) -> None:
        self.company_list_path = company_list_path
        self.errors: list[PipelineError] = []
        self.source_health: dict[str, dict[str, object]] = {}
        self.platform_collectors: dict[str, ATSBoardCollector] = {
            "ashby": AshbyCollector(),
            "greenhouse": GreenhouseCollector(),
            "lever": LeverCollector(),
            "smartrecruiters": SmartRecruitersCollector(),
        }

    @staticmethod
    def _prioritized_companies(companies: list[dict[str, object]], context: CollectorContext) -> list[dict[str, object]]:
        priority_names = {name.lower() for name in context.settings.filters.priority_companies}
        prioritized = sorted(
            (company for company in companies if company.get("enabled", True)),
            key=lambda company: (
                str(company.get("name", "")).lower() not in priority_names,
                int(company.get("priority_tier", 3)),
                str(company.get("name", "")).lower(),
            ),
        )
        return prioritized[: context.settings.collection.max_company_pages_per_run]

    def _discover_ats_boards(self, company: dict[str, object], html: str, source_url: str) -> list[ATSBoardConfig]:
        discovered: list[ATSBoardConfig] = []
        seen: set[tuple[str, str]] = set()
        for platform, pattern in ATS_DISCOVERY_PATTERNS.items():
            for match in pattern.finditer(html):
                identifier = match.group(1)
                dedupe_key = (platform, identifier.lower())
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                discovered.append(
                    ATSBoardConfig(
                        company_name=str(company["name"]),
                        platform=platform,
                        identifier=identifier,
                        careers_url=source_url,
                        priority_tier=int(company.get("priority_tier", 3)),
                        enabled=True,
                    )
                )
        return discovered

    def _collect_discovered_ats_jobs(
        self,
        *,
        company: dict[str, object],
        html: str,
        source_url: str,
        context: CollectorContext,
    ) -> list[CollectedJob]:
        jobs: list[CollectedJob] = []
        for board in self._discover_ats_boards(company, html, source_url):
            collector = self.platform_collectors.get(board.platform.lower())
            if collector is None:
                continue
            health_key = f"discovered:{board.platform.lower()}:{company['name']}"
            try:
                board_jobs = collector.collect_board(board, context)
                jobs.extend(board_jobs)
                self.source_health[health_key] = {
                    "status": "healthy",
                    "total_available": collector.last_total_available,
                    "relevant_jobs": len(board_jobs),
                }
            except Exception as exc:  # pragma: no cover - network/provider failures
                self.source_health[health_key] = {
                    "status": "failed",
                    "total_available": None,
                    "relevant_jobs": 0,
                    "error": str(exc),
                }
                self.errors.append(
                    PipelineError(
                        source_name=health_key,
                        stage="collect",
                        message="Discovered ATS board failed",
                        detail=str(exc),
                    )
                )
                context.logger.warning(
                    "Discovered ATS board failed",
                    extra={
                        "context": {
                            "company": company["name"],
                            "platform": board.platform,
                            "identifier": board.identifier,
                            "error": str(exc),
                        }
                    },
                )
        return jobs

    def collect(self, context: CollectorContext) -> list[CollectedJob]:
        jobs: list[CollectedJob] = []
        self.errors = []
        self.source_health = {}
        companies = self._prioritized_companies(load_company_list(self.company_list_path), context)
        for company in companies:
            source_url = company.get("careers_url") or urljoin(company["homepage"], "/careers")
            health_key = f"company:{company['slug']}"
            try:
                html = context.http_client.get_text(
                    source_url,
                    render_js=bool(context.settings.collection.use_playwright_for_js and company.get("js_heavy")),
                )
            except Exception as exc:  # pragma: no cover - logging path
                self.source_health[health_key] = {
                    "status": "failed",
                    "total_available": None,
                    "relevant_jobs": 0,
                    "error": str(exc),
                }
                self.errors.append(
                    PipelineError(
                        source_name=health_key,
                        stage="collect",
                        message="Company careers page failed",
                        detail=str(exc),
                    )
                )
                context.logger.warning(
                    "Failed to scan careers page",
                    extra={"context": {"company": company["name"], "error": str(exc)}},
                )
                continue
            discovered_jobs = self._collect_discovered_ats_jobs(
                company=company,
                html=html,
                source_url=source_url,
                context=context,
            )
            jobs.extend(discovered_jobs)
            if discovered_jobs:
                self.source_health[health_key] = {
                    "status": "healthy",
                    "total_available": None,
                    "relevant_jobs": len(discovered_jobs),
                }
                continue
            page_jobs = extract_jobs_from_html(
                html=html,
                base_url=source_url,
                source_name=f"company:{company['slug']}",
                source_type=SourceType.COMPANY_PAGE,
                settings=context.settings,
                default_company_name=company["name"],
                allow_anchor_fallback=int(company.get("priority_tier", 3)) <= 1,
            )
            jobs.extend(page_jobs)
            self.source_health[health_key] = {
                "status": "healthy",
                "total_available": None,
                "relevant_jobs": len(page_jobs),
            }
        return jobs[: context.settings.collection.max_jobs_per_source]
