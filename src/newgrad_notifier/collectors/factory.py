"""Collector construction helpers."""

from __future__ import annotations

from newgrad_notifier.collectors.ats.service import ATSCollectorService
from newgrad_notifier.collectors.base import Collector
from newgrad_notifier.collectors.company_pages.collector import CompanyPagesCollector
from newgrad_notifier.collectors.github_markdown import GitHubMarkdownCollector
from newgrad_notifier.collectors.simplify import SimplifyCollector
from newgrad_notifier.collectors.web_search.collector import WebSearchCollector
from newgrad_notifier.config.company_loader import load_default_ats_boards
from newgrad_notifier.config.settings import ATSBoardConfig
from newgrad_notifier.config.settings import AppSettings


def build_collectors(settings: AppSettings) -> list[Collector]:
    """Instantiate the enabled collectors for the current settings."""

    collectors: list[Collector] = []
    enabled_ats_boards = [board for board in settings.ats_boards if board.enabled]
    if settings.sources.simplify_enabled and settings.structured_feeds:
        collectors.extend(GitHubMarkdownCollector(feed) for feed in settings.markdown_feeds if feed.url)
        collectors.extend(SimplifyCollector([feed]) for feed in settings.structured_feeds if feed.url)
    if settings.sources.ats_enabled:
        boards = enabled_ats_boards
        if not boards:
            boards = [ATSBoardConfig.model_validate(board) for board in load_default_ats_boards()]
        if boards:
            collectors.append(ATSCollectorService(boards))
    if settings.sources.company_pages_enabled:
        collectors.append(CompanyPagesCollector(settings.company_coverage.list_path or None))
    if settings.sources.web_search_enabled:
        collectors.append(
            WebSearchCollector(
                provider_name=settings.web_search.provider,
                queries=settings.web_search.queries,
                fixture_path=settings.web_search.fixture_path or None,
            )
        )
    return collectors
