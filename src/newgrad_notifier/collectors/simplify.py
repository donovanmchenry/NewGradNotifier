"""Structured source ingestion for Simplify or equivalent early-career feeds."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from dateutil import parser as date_parser

from newgrad_notifier.collectors.base import Collector, CollectorContext
from newgrad_notifier.collectors.relevance import cohort_allowed, is_relevant_role, location_allowed
from newgrad_notifier.config.settings import StructuredFeedConfig
from newgrad_notifier.contracts import CollectedJob, SourceType

_AGGREGATOR_DOMAINS = {
    "indeed.com",
    "linkedin.com",
    "glassdoor.com",
    "ziprecruiter.com",
    "jobright.ai",
}


def _is_direct_application_url(url: str) -> bool:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return not any(host == domain or host.endswith(f".{domain}") for domain in _AGGREGATOR_DOMAINS)


def _is_recent(value: Any, max_age_days: int) -> bool:
    if not value:
        return True
    try:
        if isinstance(value, datetime):
            posted_at = value
        elif isinstance(value, (int, float)):
            posted_at = datetime.fromtimestamp(value, tz=UTC)
        else:
            posted_at = date_parser.parse(str(value))
    except (ValueError, TypeError, OverflowError):
        return True
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=UTC)
    return posted_at >= datetime.now(UTC) - timedelta(days=max_age_days)


def _extract_path(payload: Any, dotted_path: str) -> Any:
    if not dotted_path:
        return payload
    cursor = payload
    for part in dotted_path.split("."):
        if isinstance(cursor, list):
            cursor = cursor[int(part)]
        else:
            cursor = cursor[part]
    return cursor


class SimplifyCollector(Collector):
    """Collector for configurable structured feeds."""

    name = "simplify"

    def __init__(self, feeds: list[StructuredFeedConfig]) -> None:
        self.feeds = [feed for feed in feeds if feed.url]
        self.name = f"structured:{self.feeds[0].name}" if len(self.feeds) == 1 else "structured_feeds"

    def collect(self, context: CollectorContext) -> list[CollectedJob]:
        jobs: list[CollectedJob] = []
        for feed in self.feeds:
            if feed.format == "csv":
                jobs.extend(self._collect_csv(feed, context))
            else:
                jobs.extend(self._collect_json(feed, context))
        return jobs[: context.settings.collection.max_jobs_per_source]

    def _collect_csv(self, feed: StructuredFeedConfig, context: CollectorContext) -> list[CollectedJob]:
        content = context.http_client.get_text(feed.url)
        rows = list(csv.DictReader(io.StringIO(content)))
        return self._map_rows(feed, rows, context)

    def _collect_json(self, feed: StructuredFeedConfig, context: CollectorContext) -> list[CollectedJob]:
        payload = context.http_client.get_json(feed.url)
        rows = _extract_path(payload, feed.job_path)
        if not isinstance(rows, list):
            return []
        return self._map_rows(feed, rows, context)

    def _map_rows(
        self,
        feed: StructuredFeedConfig,
        rows: list[dict[str, Any]],
        context: CollectorContext,
    ) -> list[CollectedJob]:
        jobs: list[CollectedJob] = []
        for row in rows:
            # Skip stale/inactive listings when the feed provides these flags
            if (
                row.get("active") is False
                or row.get("is_visible") is False
                or row.get("is_closed") is True
                or (feed.closed_key and row.get(feed.closed_key) is True)
            ):
                continue
            title = str(row.get(feed.title_key, "")).strip()
            description = str(row.get(feed.description_key, "")).strip()
            # Description-rich feeds must prove early-career relevance themselves;
            # sparse curated feeds may use their repository context as the signal.
            source_context = "" if description else f"{feed.name} {feed.url}"
            raw_location = row.get(feed.location_key, "")
            if isinstance(raw_location, list):
                location = ", ".join(str(l) for l in raw_location) or None
            else:
                location = str(raw_location).strip() or None
            if not title or not row.get(feed.company_key) or not row.get(feed.url_key):
                continue
            if not _is_recent(row.get(feed.posted_at_key), context.settings.collection.max_job_age_days):
                continue
            apply_url = str(row[feed.url_key])
            if not _is_direct_application_url(apply_url):
                continue
            if not cohort_allowed(f"{title} {apply_url}", context.settings):
                continue
            if not is_relevant_role(title, description, context.settings, source_context=source_context):
                continue
            if not location_allowed(location, context.settings):
                continue
            jobs.append(
                CollectedJob(
                    source_name=feed.name,
                    source_type=SourceType.STRUCTURED,
                    source_url=feed.url,
                    apply_url=apply_url,
                    company_name=str(row[feed.company_key]),
                    title=title,
                    external_job_id=str(row.get(feed.job_id_key or "", "")).strip() or None,
                    location_text=location,
                    posted_at=row.get(feed.posted_at_key),
                    description_text=description,
                    metadata={"feed": feed.name, "format": feed.format},
                )
            )
        return jobs
