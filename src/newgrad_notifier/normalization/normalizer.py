"""Normalization logic for raw jobs."""

from __future__ import annotations

import re
from datetime import datetime

from dateutil import parser as date_parser

from newgrad_notifier.contracts import CollectedJob, NormalizedJob
from newgrad_notifier.normalization.job_details import extract_job_details
from newgrad_notifier.utils.hashing import sha256_text
from newgrad_notifier.utils.time import utc_now

TITLE_CLEANUP_PATTERN = re.compile(r"[^a-z0-9]+")
REMOTE_HINTS = ("remote", "hybrid", "distributed", "work from home")


def normalize_title(value: str) -> str:
    """Normalize role titles into a comparison-friendly slug."""

    lowered = value.lower().strip()
    return TITLE_CLEANUP_PATTERN.sub(" ", lowered).strip()


def normalize_location(value: str | None) -> tuple[str | None, bool]:
    """Normalize location text and detect remote roles."""

    if not value:
        return None, False
    collapsed = " ".join(value.split())
    lowered = collapsed.lower()
    is_remote = any(hint in lowered for hint in REMOTE_HINTS)
    return collapsed, is_remote


def parse_posted_at(value: datetime | str | None) -> datetime | None:
    """Parse a posted-at value when one is present."""

    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return date_parser.parse(value)
    except (ValueError, TypeError, OverflowError):
        return None


def build_canonical_key(job: CollectedJob, description_hash: str) -> str:
    """Build a stable identity key from the strongest available identifiers."""

    if job.external_job_id:
        return sha256_text(f"{job.company_name.lower()}::{job.external_job_id.lower()}")
    return sha256_text(
        "::".join(
            [
                job.company_name.lower().strip(),
                normalize_title(job.title),
                (job.location_text or "").lower().strip(),
                description_hash,
            ]
        )
    )


def normalize_job(job: CollectedJob) -> NormalizedJob:
    """Normalize a collected job into the canonical internal representation."""

    posted_at = parse_posted_at(job.posted_at)
    normalized_location, is_remote = normalize_location(job.location_text)
    description_text = (job.description_text or "").strip()
    description_hash = sha256_text(description_text or job.title)
    content_hash = sha256_text(
        "::".join(
            [
                job.company_name,
                job.title,
                job.location_text or "",
                description_text,
                job.apply_url,
            ]
        )
    )
    metadata = dict(job.metadata)
    metadata["normalized_at"] = utc_now().isoformat()
    metadata["description_hash"] = description_hash
    metadata["job_details"] = extract_job_details(
        title=job.title,
        description=description_text,
        location=normalized_location,
        is_remote=is_remote,
    )
    return NormalizedJob(
        canonical_key=build_canonical_key(job, description_hash),
        source_name=job.source_name,
        source_type=job.source_type,
        source_url=job.source_url,
        apply_url=job.apply_url,
        company_name=job.company_name.strip(),
        title=job.title.strip(),
        title_normalized=normalize_title(job.title),
        external_job_id=job.external_job_id,
        job_family=job.job_family,
        location_text=job.location_text,
        location_normalized=normalized_location,
        is_remote=is_remote,
        posted_at=posted_at,
        description_text=description_text,
        description_hash=description_hash,
        first_seen_at=utc_now(),
        last_seen_at=utc_now(),
        content_hash=content_hash,
        confidence=job.confidence,
        metadata=metadata,
    )
