"""Stable job identities shared by normalization, dedupe, and persistence."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_IGNORED_QUERY_KEYS = {
    "embed",
    "gh_src",
    "source",
    "ref",
    "referrer",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}
_UUID_PATTERN = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def normalize_job_url(url: str) -> str:
    """Remove tracking and application-page noise from a direct job URL."""

    parts = urlsplit(url.strip())
    scheme = "https" if parts.scheme.lower() in {"http", "https"} else parts.scheme.lower()
    hostname = parts.netloc.lower().removeprefix("www.")
    path = re.sub(r"/(?:application|apply)/?$", "", parts.path.rstrip("/"), flags=re.IGNORECASE)
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() not in _IGNORED_QUERY_KEYS and not key.lower().startswith("utm_")
        )
    )
    return urlunsplit((scheme, hostname, path, query, ""))


def ats_job_identity(url: str) -> str | None:
    """Extract a source-independent ATS requisition identity when possible."""

    normalized = normalize_job_url(url)
    parts = urlsplit(normalized)
    host = parts.netloc
    path = parts.path
    query = dict(parse_qsl(parts.query))

    greenhouse_id = query.get("gh_jid") or query.get("token")
    if greenhouse_id and greenhouse_id.isdigit():
        return f"greenhouse::{greenhouse_id}"

    if "ashbyhq.com" in host:
        match = re.search(rf"/([^/]+)/({_UUID_PATTERN})(?:/|$)", path, flags=re.IGNORECASE)
        if match:
            return f"ashby::{match.group(1).lower()}::{match.group(2).lower()}"

    if "lever.co" in host:
        match = re.search(rf"/([^/]+)/({_UUID_PATTERN})(?:/|$)", path, flags=re.IGNORECASE)
        if match:
            return f"lever::{match.group(1).lower()}::{match.group(2).lower()}"

    if "greenhouse" in host:
        match = re.search(r"/jobs/(\d+)(?:/|$)", path, flags=re.IGNORECASE)
        if match:
            return f"greenhouse::{match.group(1)}"

    if "myworkdayjobs.com" in host:
        match = re.search(r"_((?:JR|R)[A-Z0-9-]+)$", path, flags=re.IGNORECASE)
        if match:
            return f"workday::{host}::{match.group(1).lower()}"

    if "icims.com" in host:
        match = re.search(r"/jobs/(\d+)(?:/|$)", path, flags=re.IGNORECASE)
        if match:
            return f"icims::{host}::{match.group(1)}"

    return None


def identity_aliases(url: str) -> tuple[str, ...]:
    """Return all durable aliases by which a job should be recognized."""

    normalized_url = normalize_job_url(url)
    ats_identity = ats_job_identity(url)
    aliases = [f"url::{normalized_url}"]
    if ats_identity:
        aliases.insert(0, f"ats::{ats_identity}")
    return tuple(aliases)


def primary_job_identity(url: str) -> str:
    """Return the strongest durable identity available for a job URL."""

    return identity_aliases(url)[0]
