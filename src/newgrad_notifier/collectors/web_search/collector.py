"""Search the web for newly posted SWE early-career roles."""

from __future__ import annotations

from urllib.parse import urlparse

from newgrad_notifier.collectors.base import Collector, CollectorContext
from newgrad_notifier.collectors.parsers import _split_embedded_title_location
from newgrad_notifier.collectors.relevance import is_relevant_role, location_allowed
from newgrad_notifier.collectors.parsers import extract_jobs_from_html
from newgrad_notifier.collectors.web_search.base import SearchProvider
from newgrad_notifier.collectors.web_search.duckduckgo import DuckDuckGoHtmlSearchProvider
from newgrad_notifier.collectors.web_search.fixture import FixtureSearchProvider
from newgrad_notifier.contracts import CollectedJob, SourceType


class WebSearchCollector(Collector):
    """Search provider backed collector."""

    name = "web_search"

    def __init__(self, provider_name: str, queries: list[str], fixture_path: str | None = None) -> None:
        self.provider = self._build_provider(provider_name, fixture_path)
        self.queries = queries

    def _build_provider(self, provider_name: str, fixture_path: str | None) -> SearchProvider:
        if provider_name == "fixture":
            if not fixture_path:
                raise ValueError("fixture search provider requires a fixture path")
            return FixtureSearchProvider(fixture_path)
        return DuckDuckGoHtmlSearchProvider()

    @staticmethod
    def _infer_company_name(result_title: str, url: str) -> str | None:
        parsed = urlparse(str(url))
        host = parsed.netloc.lower()
        path_parts = [part for part in parsed.path.split("/") if part]
        if "jobs.ashbyhq.com" in host and path_parts:
            return path_parts[0].replace("-", " ").title()
        if "jobs.lever.co" in host and path_parts:
            return path_parts[0].replace("-", " ").title()
        if "greenhouse.io" in host and path_parts:
            for index, part in enumerate(path_parts):
                if part == "boards" and index + 1 < len(path_parts):
                    return path_parts[index + 1].replace("-", " ").title()
            return path_parts[0].replace("-", " ").title()
        if "smartrecruiters.com" in host and path_parts:
            return path_parts[0].replace("-", " ").title()
        return None

    def _job_from_search_result(self, result, query: str, context: CollectorContext) -> CollectedJob | None:
        cleaned_title, inferred_location = _split_embedded_title_location(result.title)
        description = (result.snippet or "").strip()
        if not is_relevant_role(cleaned_title, description, context.settings):
            return None
        if inferred_location and not location_allowed(inferred_location, context.settings):
            return None
        company_name = self._infer_company_name(cleaned_title, str(result.url))
        if not company_name:
            return None
        return CollectedJob(
            source_name=f"search:{result.source_name}",
            source_type=SourceType.WEB_SEARCH,
            source_url=str(result.url),
            apply_url=str(result.url),
            company_name=company_name,
            title=cleaned_title,
            location_text=inferred_location,
            description_text=description,
            posted_at=result.published_at,
            search_query=query,
            confidence=0.55,
            metadata={"parser": "search_result_direct"},
        )

    def collect(self, context: CollectorContext) -> list[CollectedJob]:
        jobs: list[CollectedJob] = []
        queries = self.queries or context.settings.filters.keywords
        for query in queries:
            results = self.provider.search(query, context, context.settings.web_search.max_results_per_query)
            for result in results:
                direct_job = self._job_from_search_result(result, query, context)
                if direct_job:
                    jobs.append(direct_job)
                try:
                    html = context.http_client.get_text(str(result.url))
                except Exception:  # pragma: no cover - network/HTML failures
                    continue
                extracted = extract_jobs_from_html(
                    html=html,
                    base_url=str(result.url),
                    source_name=f"search:{result.source_name}",
                    source_type=SourceType.WEB_SEARCH,
                    settings=context.settings,
                )
                for job in extracted:
                    job.search_query = query
                    jobs.append(job)
        return jobs[: context.settings.collection.max_jobs_per_source]
