"""Company careers page collector."""

from __future__ import annotations

from urllib.parse import urljoin

from newgrad_notifier.collectors.base import Collector, CollectorContext
from newgrad_notifier.collectors.parsers import extract_jobs_from_html
from newgrad_notifier.config.company_loader import load_company_list
from newgrad_notifier.contracts import CollectedJob, SourceType


class CompanyPagesCollector(Collector):
    """Scan configured career pages for direct job postings."""

    name = "company_pages"

    def __init__(self, company_list_path: str | None = None) -> None:
        self.company_list_path = company_list_path

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
                extract_jobs_from_html(
                    html=html,
                    base_url=source_url,
                    source_name=f"company:{company['slug']}",
                    source_type=SourceType.COMPANY_PAGE,
                    settings=context.settings,
                    default_company_name=company["name"],
                )
            )
        return jobs[: context.settings.collection.max_jobs_per_source]

