"""DuckDuckGo HTML search provider."""

from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

from newgrad_notifier.collectors.base import CollectorContext
from newgrad_notifier.collectors.web_search.base import SearchProvider
from newgrad_notifier.contracts import SearchResult


class DuckDuckGoHtmlSearchProvider(SearchProvider):
    """HTML search provider without additional credentials."""

    def search(self, query: str, context: CollectorContext, max_results: int) -> list[SearchResult]:
        html = context.http_client.get_text(
            "https://html.duckduckgo.com/html/",
            method="POST",
            data={"q": query},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if not html:
            return []
        soup = BeautifulSoup(html, "lxml")
        results: list[SearchResult] = []
        for anchor in soup.select("a.result__a"):
            href = anchor.get("href")
            if not href:
                continue
            parsed = urlparse(href)
            if parsed.netloc.endswith("duckduckgo.com"):
                params = parse_qs(parsed.query)
                href = unquote(params.get("uddg", [href])[0])
            snippet_node = anchor.find_parent("div", class_="result")
            snippet_text = snippet_node.get_text(" ", strip=True) if snippet_node else None
            results.append(
                SearchResult(
                    title=anchor.get_text(" ", strip=True),
                    url=href,
                    snippet=snippet_text,
                    source_name="duckduckgo_html",
                )
            )
            if len(results) >= max_results:
                break
        return results
