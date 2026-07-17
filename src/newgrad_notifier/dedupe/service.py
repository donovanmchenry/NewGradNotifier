"""Batch deduplication for normalized jobs."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from newgrad_notifier.contracts import NormalizedJob


@dataclass(slots=True)
class DedupeResult:
    """Deduped jobs plus duplicate counts."""

    unique_jobs: list[NormalizedJob]
    duplicate_count: int


class BatchDeduper:
    """Deduplicate jobs within a single run before database upsert."""

    def dedupe(self, jobs: list[NormalizedJob]) -> DedupeResult:
        primary_by_key: dict[str, NormalizedJob] = {}
        alias_to_key: dict[str, str] = {}
        duplicate_count = 0
        for job in jobs:
            identity_candidates = self._aliases(job)
            existing_primary_key = next((alias_to_key[candidate] for candidate in identity_candidates if candidate in alias_to_key), None)
            if existing_primary_key is None:
                primary_by_key[job.canonical_key] = job
                for alias in identity_candidates:
                    alias_to_key[alias] = job.canonical_key
                continue

            duplicate_count += 1
            primary_by_key[existing_primary_key] = self._merge(primary_by_key[existing_primary_key], job)
            for alias in identity_candidates:
                alias_to_key[alias] = existing_primary_key

        return DedupeResult(unique_jobs=list(primary_by_key.values()), duplicate_count=duplicate_count)

    def _aliases(self, job: NormalizedJob) -> list[str]:
        aliases = [job.canonical_key, f"url::{self._normalized_url(job.apply_url)}"]
        aliases.append(f"title::{job.company_name.lower()}::{job.title_normalized}")
        if job.external_job_id:
            aliases.append(f"external::{job.company_name.lower()}::{job.external_job_id.lower()}")
        return aliases

    @staticmethod
    def _normalized_url(url: str) -> str:
        parts = urlsplit(url)
        path = parts.path.rstrip("/")
        if path.endswith("/application"):
            path = path.removesuffix("/application")
        ignored_query_keys = {"embed", "gh_src", "source", "utm_source", "utm_medium", "utm_campaign"}
        query = urlencode(sorted((key, value) for key, value in parse_qsl(parts.query) if key.lower() not in ignored_query_keys))
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))

    def _merge(self, primary: NormalizedJob, duplicate: NormalizedJob) -> NormalizedJob:
        merged_metadata = dict(primary.metadata)
        merged_metadata.setdefault("seen_in_sources", [])
        existing_sources = set(merged_metadata["seen_in_sources"])
        existing_sources.update([primary.source_name, duplicate.source_name])
        merged_metadata["seen_in_sources"] = sorted(existing_sources)
        if len(duplicate.description_text) > len(primary.description_text):
            primary.description_text = duplicate.description_text
            primary.description_hash = duplicate.description_hash
            primary.content_hash = duplicate.content_hash
        primary.confidence = max(primary.confidence, duplicate.confidence)
        primary.metadata = merged_metadata
        return primary
