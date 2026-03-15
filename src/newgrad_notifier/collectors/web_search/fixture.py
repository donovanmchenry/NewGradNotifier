"""Fixture-backed search provider for local development."""

from __future__ import annotations

from newgrad_notifier.collectors.base import CollectorContext
from newgrad_notifier.collectors.web_search.base import SearchProvider
from newgrad_notifier.contracts import SearchResult


class FixtureSearchProvider(SearchProvider):
    """Load precomputed search results from JSON fixtures."""

    def __init__(self, fixture_path: str) -> None:
        self.fixture_path = fixture_path

    def search(self, query: str, context: CollectorContext, max_results: int) -> list[SearchResult]:
        payload = context.http_client.get_json(self.fixture_path)
        query_map = payload.get("queries", payload)
        results = query_map.get(query, [])
        return [SearchResult.model_validate(result) for result in results[:max_results]]

