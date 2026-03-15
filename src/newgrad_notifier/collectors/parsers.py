"""HTML parsers shared by company page and web search collectors."""

from __future__ import annotations

import json
import re
from html import unescape
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from newgrad_notifier.collectors.relevance import is_relevant_role, location_allowed
from newgrad_notifier.config.settings import AppSettings
from newgrad_notifier.contracts import CollectedJob, SourceType

TITLE_LOCATION_SEPARATOR_PATTERN = re.compile(r"\s(?:\||-|—|–)\s")
TRAILING_PARENS_PATTERN = re.compile(r"\(([^()]+)\)\s*$")
COMMON_LOCATION_HINTS = (
    "remote",
    "united states",
    "usa",
    "u.s.",
    "california",
    "new york",
    "washington",
    "texas",
    "massachusetts",
    "illinois",
    "georgia",
    "florida",
    "virginia",
    "los angeles",
    "san francisco",
    "new york city",
    "seattle",
    "austin",
    "boston",
    "chicago",
    "atlanta",
    "toronto",
    "vancouver",
    "london",
    "hyderabad",
    "berlin",
    "india",
    "canada",
    "united kingdom",
)
ATS_LINK_HINTS = (
    "boards.greenhouse.io",
    "jobs.lever.co",
    "jobs.ashbyhq.com",
    "jobs.smartrecruiters.com",
    "myworkdayjobs.com",
)


def _strip_html(value: str | None) -> str:
    if not value:
        return ""
    return BeautifulSoup(unescape(value), "html.parser").get_text(" ", strip=True)


def _iter_job_postings(node: Any) -> list[dict[str, Any]]:
    if isinstance(node, list):
        jobs: list[dict[str, Any]] = []
        for item in node:
            jobs.extend(_iter_job_postings(item))
        return jobs
    if isinstance(node, dict):
        node_type = node.get("@type")
        if node_type == "JobPosting":
            return [node]
        if "@graph" in node:
            return _iter_job_postings(node["@graph"])
        jobs: list[dict[str, Any]] = []
        for value in node.values():
            jobs.extend(_iter_job_postings(value))
        return jobs
    return []


def _job_location(job_posting: dict[str, Any]) -> str | None:
    job_location = job_posting.get("jobLocation")
    if isinstance(job_location, list) and job_location:
        job_location = job_location[0]
    if isinstance(job_location, dict):
        address = job_location.get("address", {})
        parts = [address.get("addressLocality"), address.get("addressRegion"), address.get("addressCountry")]
        return ", ".join(part for part in parts if part)
    applicant_restrictions = job_posting.get("applicantLocationRequirements")
    if isinstance(applicant_restrictions, dict):
        name = applicant_restrictions.get("name")
        if name:
            return str(name)
    return None


def _looks_like_location_blob(value: str) -> bool:
    lowered = value.lower().strip()
    if not lowered:
        return False
    if any(hint in lowered for hint in COMMON_LOCATION_HINTS):
        return True
    return ";" in value or value.count(",") >= 1


def _split_embedded_title_location(title: str) -> tuple[str, str | None]:
    cleaned = " ".join(title.split())

    paren_match = TRAILING_PARENS_PATTERN.search(cleaned)
    if paren_match and _looks_like_location_blob(paren_match.group(1)):
        location = paren_match.group(1).strip()
        cleaned = cleaned[: paren_match.start()].rstrip(" -|,")
        return cleaned, location

    separator_match = None
    for match in TITLE_LOCATION_SEPARATOR_PATTERN.finditer(cleaned):
        tail = cleaned[match.end() :].strip()
        if _looks_like_location_blob(tail):
            separator_match = match
    if separator_match:
        return cleaned[: separator_match.start()].rstrip(" -|,"), cleaned[separator_match.end() :].strip()

    early_career_markers = ("early career", "new grad", "new graduate", "entry level", "entry-level")
    lowered = cleaned.lower()
    for marker in early_career_markers:
        marker_index = lowered.find(marker)
        if marker_index == -1:
            continue
        role_end = marker_index + len(marker)
        location_candidate = cleaned[role_end:].strip(" ,;-")
        if location_candidate and _looks_like_location_blob(location_candidate):
            return cleaned[:role_end].rstrip(" -|,"), location_candidate

    return cleaned, None


def _href_is_job_like(href: str) -> bool:
    lowered = href.lower()
    if any(token in lowered for token in ATS_LINK_HINTS):
        return True
    return any(token in lowered for token in ("/job", "/jobs", "/career", "/careers", "/openings", "/positions"))


def _anchor_confident_enough(
    *,
    title: str,
    location: str | None,
    href: str,
    settings: AppSettings,
) -> bool:
    if not _href_is_job_like(href):
        return False
    if len(title) > 140:
        return False
    if location:
        return location_allowed(location, settings)
    return any(hint in title.lower() for hint in ("early career", "new grad", "entry level", "entry-level"))


def extract_jobs_from_html(
    *,
    html: str,
    base_url: str,
    source_name: str,
    source_type: SourceType,
    settings: AppSettings,
    default_company_name: str | None = None,
    allow_anchor_fallback: bool = True,
) -> list[CollectedJob]:
    """Extract job postings from JSON-LD or relevant anchor tags."""

    soup = BeautifulSoup(html, "lxml")
    jobs: list[CollectedJob] = []

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        for posting in _iter_job_postings(payload):
            title = posting.get("title")
            description = _strip_html(posting.get("description"))
            company_name = (
                posting.get("hiringOrganization", {}).get("name")
                if isinstance(posting.get("hiringOrganization"), dict)
                else default_company_name
            )
            apply_url = posting.get("url") or base_url
            location = _job_location(posting)
            if not title or not company_name:
                continue
            if not is_relevant_role(title, description, settings):
                continue
            if not location_allowed(location, settings):
                continue
            jobs.append(
                CollectedJob(
                    source_name=source_name,
                    source_type=source_type,
                    source_url=base_url,
                    apply_url=urljoin(base_url, apply_url),
                    company_name=company_name,
                    title=title,
                    external_job_id=str(posting.get("identifier", {}).get("value", "")) or None
                    if isinstance(posting.get("identifier"), dict)
                    else None,
                    location_text=location,
                    posted_at=posting.get("datePosted"),
                    description_text=description,
                    employment_type=posting.get("employmentType"),
                    metadata={"parser": "json_ld"},
                )
            )

    if jobs or not allow_anchor_fallback:
        return jobs

    for anchor in soup.find_all("a", href=True):
        anchor_text = anchor.get_text(" ", strip=True)
        if not anchor_text:
            continue
        href = str(anchor["href"])
        cleaned_title, inferred_location = _split_embedded_title_location(anchor_text)
        if not cleaned_title:
            continue
        if not _anchor_confident_enough(title=cleaned_title, location=inferred_location, href=href, settings=settings):
            continue
        if not is_relevant_role(cleaned_title, "", settings):
            continue
        jobs.append(
            CollectedJob(
                source_name=source_name,
                source_type=source_type,
                source_url=base_url,
                apply_url=urljoin(base_url, href),
                company_name=default_company_name or soup.title.get_text(strip=True) if soup.title else "Unknown Company",
                title=cleaned_title,
                location_text=inferred_location,
                description_text="",
                confidence=0.6,
                metadata={"parser": "anchor_fallback", "raw_anchor_text": anchor_text},
            )
        )

    return jobs
