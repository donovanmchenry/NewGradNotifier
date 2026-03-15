"""Search provider contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from newgrad_notifier.collectors.base import CollectorContext
from newgrad_notifier.contracts import SearchResult


class SearchProvider(ABC):
    """Base web search provider interface."""

    @abstractmethod
    def search(self, query: str, context: CollectorContext, max_results: int) -> list[SearchResult]:
        """Return search results for a query."""

