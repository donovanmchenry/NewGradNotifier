"""Structured source ingestion for Simplify or equivalent early-career feeds."""

from __future__ import annotations

import csv
import io
from typing import Any

from newgrad_notifier.collectors.base import Collector, CollectorContext
from newgrad_notifier.collectors.relevance import is_relevant_role, location_allowed
from newgrad_notifier.config.settings import StructuredFeedConfig
from newgrad_notifier.contracts import CollectedJob, SourceType


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
            if row.get("active") is False or row.get("is_visible") is False:
                continue
            title = str(row.get(feed.title_key, "")).strip()
            description = str(row.get(feed.description_key, "")).strip()
            source_context = f"{feed.name} {feed.url}"
            raw_location = row.get(feed.location_key, "")
            if isinstance(raw_location, list):
                location = ", ".join(str(l) for l in raw_location) or None
            else:
                location = str(raw_location).strip() or None
            if not title or not row.get(feed.company_key) or not row.get(feed.url_key):
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
                    apply_url=str(row[feed.url_key]),
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
