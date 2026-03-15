"""Role filtering and relevance heuristics used during discovery."""

from __future__ import annotations

import re

from newgrad_notifier.config.settings import AppSettings

ROLE_HINTS = (
    "software engineer",
    "software developer",
    "full stack",
    "full-stack",
    "frontend",
    "front end",
    "backend",
    "back end",
    "product engineer",
    "engineer i",
    "software engineer i",
    "associate software engineer",
)

EARLY_CAREER_HINTS = (
    "new grad",
    "new graduate",
    "recent graduate",
    "university graduate",
    "early career",
    "class of 2027",
    "2027 graduates",
    "graduate program",
    "entry level",
    "entry-level",
)

EXCLUSION_HINTS = (
    "intern ",
    " internship",
    "co-op",
    "co op",
    "firmware",
    "embedded",
    "it support",
    "help desk",
    "qa ",
    "quality assurance",
    "data analyst",
    "business analyst",
    "sales engineer",
    "developer advocate",
    "hardware",
    "site reliability",
    "sre",
    "devops",
    "ml researcher",
    "machine learning research",
    "research scientist",
)

US_STATE_ABBREVIATIONS = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DC", "DE", "FL", "GA", "HI", "IA", "ID", "IL", "IN", "KS", "KY",
    "LA", "MA", "MD", "ME", "MI", "MN", "MO", "MS", "MT", "NC", "ND", "NE", "NH", "NJ", "NM", "NV", "NY", "OH",
    "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VA", "VT", "WA", "WI", "WV", "WY",
}
US_STATE_PATTERN = re.compile(r",\s*([A-Z]{2})(?:\b|,)")


def is_relevant_role(title: str, description: str, settings: AppSettings) -> bool:
    """Return True when the role resembles an entry-level SWE role."""

    haystack = f"{title} {description}".lower()
    if any(hint in haystack for hint in EXCLUSION_HINTS):
        return False
    if any(job_family.lower() in haystack for job_family in settings.filters.excluded_job_families):
        return False
    if any(keyword.lower() in haystack for keyword in settings.filters.keywords):
        return True
    if any(hint in haystack for hint in ROLE_HINTS) and any(hint in haystack for hint in EARLY_CAREER_HINTS):
        return True
    return any(hint in haystack for hint in ROLE_HINTS)


def location_allowed(location_text: str | None, settings: AppSettings) -> bool:
    """Return True when the location passes configured filters."""

    if not location_text:
        return True
    lowered = location_text.lower()
    if "remote" in lowered:
        return True
    excluded_locations = [location.lower() for location in settings.filters.excluded_locations]
    if any(excluded in lowered for excluded in excluded_locations):
        return False
    allowed_locations = [location.lower() for location in settings.filters.allowed_locations]
    if "united states" in allowed_locations:
        if "united states" in lowered or "usa" in lowered or "us" == lowered.strip():
            return True
        state_match = US_STATE_PATTERN.search(location_text)
        if state_match and state_match.group(1) in US_STATE_ABBREVIATIONS:
            return True
    return any(allowed in lowered for allowed in allowed_locations)
