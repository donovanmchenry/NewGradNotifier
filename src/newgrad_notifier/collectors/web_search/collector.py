"""Search the web for newly posted SWE early-career roles."""

from __future__ import annotations

from newgrad_notifier.collectors.base import Collector, CollectorContext
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

    def collect(self, context: CollectorContext) -> list[CollectedJob]:
        jobs: list[CollectedJob] = []
        queries = self.queries or context.settings.filters.keywords
        for query in queries:
            results = self.provider.search(query, context, context.settings.web_search.max_results_per_query)
            for result in results:
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

