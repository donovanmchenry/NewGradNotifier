"""HTML parsers shared by company page and web search collectors."""

from __future__ import annotations

import json
from html import unescape
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from newgrad_notifier.collectors.relevance import is_relevant_role, location_allowed
from newgrad_notifier.config.settings import AppSettings
from newgrad_notifier.contracts import CollectedJob, SourceType


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


def extract_jobs_from_html(
    *,
    html: str,
    base_url: str,
    source_name: str,
    source_type: SourceType,
    settings: AppSettings,
    default_company_name: str | None = None,
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

    if jobs:
        return jobs

    for anchor in soup.find_all("a", href=True):
        anchor_text = anchor.get_text(" ", strip=True)
        if not anchor_text:
            continue
        if not is_relevant_role(anchor_text, "", settings):
            continue
        jobs.append(
            CollectedJob(
                source_name=source_name,
                source_type=source_type,
                source_url=base_url,
                apply_url=urljoin(base_url, anchor["href"]),
                company_name=default_company_name or soup.title.get_text(strip=True) if soup.title else "Unknown Company",
                title=anchor_text,
                location_text=None,
                description_text="",
                metadata={"parser": "anchor_fallback"},
            )
        )

    return jobs

