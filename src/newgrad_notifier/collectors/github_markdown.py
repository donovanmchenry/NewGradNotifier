"""Collector for GitHub-hosted markdown job tables."""

from __future__ import annotations

import re
from datetime import timedelta

from bs4 import BeautifulSoup

from newgrad_notifier.collectors.base import Collector, CollectorContext
from newgrad_notifier.collectors.relevance import cohort_allowed, is_relevant_role, location_allowed
from newgrad_notifier.config.settings import MarkdownFeedConfig
from newgrad_notifier.contracts import CollectedJob, SourceType
from newgrad_notifier.utils.hashing import sha256_text
from newgrad_notifier.utils.time import utc_now

_AGE_PATTERN = re.compile(r"^(\d+)d$", re.IGNORECASE)


def _cell_text(value: str) -> str:
    return BeautifulSoup(value, "html.parser").get_text(" ", strip=True)


def _first_href(value: str) -> str | None:
    anchor = BeautifulSoup(value, "html.parser").find("a", href=True)
    return str(anchor["href"]).strip() if anchor else None


class GitHubMarkdownCollector(Collector):
    """Parse frequently updated GitHub markdown tables into jobs."""

    def __init__(self, feed: MarkdownFeedConfig) -> None:
        self.feed = feed
        self.name = f"markdown:{feed.name}"
        self.source_health: dict[str, dict[str, object]] = {}

    def collect(self, context: CollectorContext) -> list[CollectedJob]:
        markdown = context.http_client.get_text(self.feed.url)
        jobs: list[CollectedJob] = []
        headers: dict[str, int] = {}
        total_available = 0

        for raw_line in markdown.splitlines():
            line = raw_line.strip()
            if not line.startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            lowered_cells = [_cell_text(cell).lower() for cell in cells]
            if "company" in lowered_cells and any(name in lowered_cells for name in ("position", "role", "job title")):
                headers = {name: index for index, name in enumerate(lowered_cells)}
                continue
            if not headers or all(set(cell) <= {"-", ":", " "} for cell in cells):
                continue

            company_index = headers.get("company")
            title_index = next((headers[name] for name in ("position", "role", "job title") if name in headers), None)
            location_index = headers.get("location")
            posting_index = next((headers[name] for name in ("posting", "application", "apply") if name in headers), None)
            age_index = headers.get("age")
            required = (company_index, title_index, location_index, posting_index)
            if any(index is None or index >= len(cells) for index in required):
                continue
            total_available += 1

            company = _cell_text(cells[company_index])
            title = _cell_text(cells[title_index])
            location = _cell_text(cells[location_index]) or None
            apply_url = _first_href(cells[posting_index])
            if not company or company == "↳" or not title or not apply_url:
                continue

            posted_at = None
            age_days = None
            if age_index is not None and age_index < len(cells):
                age_match = _AGE_PATTERN.match(_cell_text(cells[age_index]))
                if age_match:
                    age_days = int(age_match.group(1))
                    if age_days > self.feed.max_age_days:
                        continue
                    posted_at = utc_now() - timedelta(days=age_days)

            if not is_relevant_role(title, "", context.settings, source_context=self.feed.name):
                continue
            if not cohort_allowed(f"{title} {apply_url}", context.settings):
                continue
            if not location_allowed(location, context.settings):
                continue

            jobs.append(
                CollectedJob(
                    source_name=self.feed.name,
                    source_type=SourceType.STRUCTURED,
                    source_url=self.feed.url,
                    apply_url=apply_url,
                    company_name=company,
                    title=title,
                    external_job_id=sha256_text(apply_url)[:32],
                    location_text=location,
                    posted_at=posted_at,
                    description_text="",
                    confidence=0.8,
                    metadata={"format": "github_markdown", "age_days": age_days},
                )
            )
            if len(jobs) >= context.settings.collection.max_jobs_per_source:
                break

        self.source_health = {
            self.feed.name: {
                "status": "healthy",
                "total_available": total_available,
                "relevant_jobs": len(jobs),
            }
        }
        return jobs
