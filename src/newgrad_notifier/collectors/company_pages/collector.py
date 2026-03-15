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
from newgrad_notifier.contracts import CollectedJob, SourceType

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
        self.platform_collectors: dict[str, ATSBoardCollector] = {
            "ashby": AshbyCollector(),
            "greenhouse": GreenhouseCollector(),
            "lever": LeverCollector(),
            "smartrecruiters": SmartRecruitersCollector(),
        }

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
            try:
                jobs.extend(collector.collect_board(board, context))
            except Exception as exc:  # pragma: no cover - network/provider failures
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
        companies = load_company_list(self.company_list_path)
        for company in companies:
            if not company.get("enabled", True):
                continue
            source_url = company.get("careers_url") or urljoin(company["homepage"], "/careers")
            try:
                html = context.http_client.get_text(
                    source_url,
                    render_js=bool(context.settings.collection.use_playwright_for_js and company.get("js_heavy")),
                )
            except Exception as exc:  # pragma: no cover - logging path
                context.logger.warning(
                    "Failed to scan careers page",
                    extra={"context": {"company": company["name"], "error": str(exc)}},
                )
                continue
            jobs.extend(
                self._collect_discovered_ats_jobs(
                    company=company,
                    html=html,
                    source_url=source_url,
                    context=context,
                )
            )
            jobs.extend(
                extract_jobs_from_html(
                    html=html,
                    base_url=source_url,
                    source_name=f"company:{company['slug']}",
                    source_type=SourceType.COMPANY_PAGE,
                    settings=context.settings,
                    default_company_name=company["name"],
                    allow_anchor_fallback=int(company.get("priority_tier", 3)) <= 1,
                )
            )
        return jobs[: context.settings.collection.max_jobs_per_source]
