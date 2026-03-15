"""Collector construction helpers."""

from __future__ import annotations

from newgrad_notifier.collectors.ats.service import ATSCollectorService
from newgrad_notifier.collectors.base import Collector
from newgrad_notifier.collectors.company_pages.collector import CompanyPagesCollector
from newgrad_notifier.collectors.simplify import SimplifyCollector
from newgrad_notifier.collectors.web_search.collector import WebSearchCollector
from newgrad_notifier.config.settings import AppSettings


def build_collectors(settings: AppSettings) -> list[Collector]:
    """Instantiate the enabled collectors for the current settings."""

    collectors: list[Collector] = []
    if settings.sources.ats_enabled and settings.ats_boards:
        collectors.append(ATSCollectorService(settings.ats_boards))
    if settings.sources.simplify_enabled and settings.structured_feeds:
        collectors.append(SimplifyCollector(settings.structured_feeds))
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
