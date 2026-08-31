"""Best-effort job-description enrichment for sparse repository listings."""

from __future__ import annotations

import json
import logging
from html import unescape
from typing import Any

from bs4 import BeautifulSoup

from newgrad_notifier.contracts import NormalizedJob
from newgrad_notifier.normalization.job_details import extract_job_details
from newgrad_notifier.utils.hashing import sha256_text
from newgrad_notifier.utils.http import CachedHttpClient

_DESCRIPTION_SELECTORS = (
    "[itemprop='description']",
    ".job__description",
    ".job-description",
    "#job-description",
    "#content",
)


def _iter_job_postings(value: Any):
    if isinstance(value, list):
        for item in value:
            yield from _iter_job_postings(item)
    elif isinstance(value, dict):
        if value.get("@type") == "JobPosting":
            yield value
        for child in value.values():
            yield from _iter_job_postings(child)


def _plain_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(BeautifulSoup(unescape(value), "html.parser").get_text(" ", strip=True).split())


def extract_description_from_html(html: str) -> str:
    """Extract the most specific job-description text available in a posting page."""

    soup = BeautifulSoup(html, "lxml")
    candidates: list[str] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for posting in _iter_job_postings(payload):
            candidates.append(_plain_text(posting.get("description")))

    for selector in _DESCRIPTION_SELECTORS:
        node = soup.select_one(selector)
        if node is not None:
            candidates.append(" ".join(node.get_text(" ", strip=True).split()))

    for selector in ("meta[property='og:description']", "meta[name='description']"):
        node = soup.select_one(selector)
        if node is not None:
            candidates.append(_plain_text(node.get("content")))

    return max((candidate for candidate in candidates if candidate), key=len, default="")


def enrich_sparse_jobs(
    jobs: list[NormalizedJob],
    *,
    http_client: CachedHttpClient,
    max_fetches: int,
    min_characters: int,
    logger: logging.Logger,
) -> list[NormalizedJob]:
    """Fetch descriptions for the strongest sparse listings, bounded for predictable runtime."""

    explicit_hints = ("2027", "new grad", "new graduate", "university grad", "college grad", "early career")
    candidates = [job for job in jobs if len(job.description_text) < min_characters]
    candidates.sort(
        key=lambda job: (
            any(hint in job.title.lower() for hint in explicit_hints),
            job.posted_at is not None,
            job.posted_at.isoformat() if job.posted_at else "",
        ),
        reverse=True,
    )
    selected_keys = {job.canonical_key for job in candidates[:max_fetches]}
    enriched: list[NormalizedJob] = []

    for job in jobs:
        if job.canonical_key not in selected_keys:
            enriched.append(job)
            continue
        try:
            description = extract_description_from_html(http_client.get_text(job.apply_url))
        except Exception as exc:  # best-effort enrichment must not break discovery
            logger.info(
                "Description enrichment skipped",
                extra={"context": {"company": job.company_name, "url": job.apply_url, "error": str(exc)}},
            )
            enriched.append(job)
            continue
        if len(description) < min_characters:
            enriched.append(job)
            continue

        description_hash = sha256_text(description)
        content_hash = sha256_text(
            "::".join([job.company_name, job.title, job.location_text or "", description, job.apply_url])
        )
        metadata = dict(job.metadata)
        metadata["description_enriched"] = True
        metadata["job_details"] = extract_job_details(
            title=job.title,
            description=description,
            location=job.location_normalized,
            is_remote=job.is_remote,
        )
        enriched.append(
            job.model_copy(
                update={
                    "description_text": description,
                    "description_hash": description_hash,
                    "content_hash": content_hash,
                    "metadata": metadata,
                }
            )
        )
    return enriched
