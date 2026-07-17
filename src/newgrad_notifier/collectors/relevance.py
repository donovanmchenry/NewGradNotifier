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
    "new college grad",
    "recent graduate",
    "university graduate",
    "early career",
    "class of 2027",
    "2027 graduates",
    "graduate program",
    "entry level",
    "entry-level",
)

ENTRY_LEVEL_TITLE_HINTS = (
    "engineer i",
    "software engineer i",
    "associate software engineer",
    "new grad",
    "new graduate",
    "new college grad",
    "recent graduate",
    "university graduate",
    "early career",
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

SENIORITY_EXCLUSION_HINTS = (
    "senior",
    "sr ",
    "sr.",
    "staff",
    "principal",
    "lead ",
    "manager",
    "director",
    "head of",
    "vice president",
    "vp ",
    "distinguished",
    "architect",
    "level 5",
    "level 6",
    "level 7",
    "l5",
    "l6",
    "l7",
)

NON_US_LOCATION_HINTS = (
    "canada",
    "toronto",
    "vancouver",
    "montreal",
    "united kingdom",
    "uk",
    "london",
    "poland",
    "warsaw",
    "india",
    "israel",
    "tel aviv",
    "australia",
    "china",
    "singapore",
    "japan",
    "germany",
    "france",
    "spain",
    "netherlands",
    "ireland",
    "brazil",
    "mexico",
    "argentina",
    "emea",
    "apac",
    "latam",
    "europe",
)

US_LOCATION_HINTS = (
    "united states",
    "united states only",
    "usa",
    "u.s.",
    "u.s.a.",
    "us-only",
    "u.s.-only",
)
US_METRO_SHORTHANDS = (
    "sf",
    "nyc",
    "la",
)
US_STATE_NAMES = (
    "alabama",
    "alaska",
    "arizona",
    "arkansas",
    "california",
    "colorado",
    "connecticut",
    "delaware",
    "florida",
    "georgia",
    "hawaii",
    "idaho",
    "illinois",
    "indiana",
    "iowa",
    "kansas",
    "kentucky",
    "louisiana",
    "maine",
    "maryland",
    "massachusetts",
    "michigan",
    "minnesota",
    "mississippi",
    "missouri",
    "montana",
    "nebraska",
    "nevada",
    "new hampshire",
    "new jersey",
    "new mexico",
    "new york",
    "north carolina",
    "north dakota",
    "ohio",
    "oklahoma",
    "oregon",
    "pennsylvania",
    "rhode island",
    "south carolina",
    "south dakota",
    "tennessee",
    "texas",
    "utah",
    "vermont",
    "virginia",
    "washington",
    "west virginia",
    "wisconsin",
    "wyoming",
    "district of columbia",
)

US_STATE_ABBREVIATIONS = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DC", "DE", "FL", "GA", "HI", "IA", "ID", "IL", "IN", "KS", "KY",
    "LA", "MA", "MD", "ME", "MI", "MN", "MO", "MS", "MT", "NC", "ND", "NE", "NH", "NJ", "NM", "NV", "NY", "OH",
    "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VA", "VT", "WA", "WI", "WV", "WY",
}
US_STATE_PATTERN = re.compile(r",\s*([A-Z]{2})(?:\b|,)")
NON_ENTRY_EXPERIENCE_PATTERN = re.compile(r"\b([3-9]|\d{2,})\+?\s+years?\b")
MID_LEVEL_TITLE_PATTERN = re.compile(
    r"\b(?:software engineer|software developer|frontend engineer|backend engineer|full stack engineer|fullstack engineer|product engineer|engineer)\s+(?:ii|iii|iv|v)\b"
)


def _contains_any(text: str, hints: tuple[str, ...]) -> bool:
    return any(hint in text for hint in hints)


def _normalize_hint_text(text: str) -> str:
    return text.lower().replace("-", " ").replace("_", " ").strip()


def cohort_allowed(text: str, settings: AppSettings) -> bool:
    """Reject listings explicitly tied only to a different graduation cohort."""

    years = set(re.findall(r"\b20\d{2}\b", text.lower().replace("-", " ").replace("_", " ")))
    target_year = str(settings.candidate_profile.graduation_year)
    return not years or target_year in years


def _has_us_signal(location_text: str) -> bool:
    lowered = _normalize_hint_text(location_text)
    if _contains_any(lowered, US_LOCATION_HINTS) or _contains_any(lowered, US_STATE_NAMES):
        return True
    if lowered in US_METRO_SHORTHANDS:
        return True
    state_match = US_STATE_PATTERN.search(location_text)
    return bool(state_match and state_match.group(1) in US_STATE_ABBREVIATIONS)


def _has_non_us_signal(location_text: str) -> bool:
    return _contains_any(location_text.lower(), NON_US_LOCATION_HINTS)


def is_relevant_role(title: str, description: str, settings: AppSettings, source_context: str = "") -> bool:
    """Return True when the role resembles an entry-level SWE role."""

    title_lower = title.lower()
    if not cohort_allowed(title, settings):
        return False
    haystack = f"{title} {description}".lower()
    source_context_lower = _normalize_hint_text(source_context)
    if _contains_any(haystack, EXCLUSION_HINTS):
        return False
    if _contains_any(title_lower, SENIORITY_EXCLUSION_HINTS):
        return False
    if MID_LEVEL_TITLE_PATTERN.search(title_lower):
        return False
    if NON_ENTRY_EXPERIENCE_PATTERN.search(haystack):
        return False
    if any(job_family.lower() in haystack for job_family in settings.filters.excluded_job_families):
        return False

    role_match_in_title = _contains_any(title_lower, ROLE_HINTS)
    role_match_anywhere = role_match_in_title or _contains_any(haystack, ROLE_HINTS)
    if not role_match_anywhere:
        return False

    early_career_match = _contains_any(haystack, EARLY_CAREER_HINTS)
    entry_title_match = _contains_any(title_lower, ENTRY_LEVEL_TITLE_HINTS)
    entry_description_match = bool(
        re.search(
            r"\b(0-2|0 to 2|1-2|1 to 2)\s+years?\b|\b(entry level|entry-level|recent graduate|new grad|university graduate)\b",
            haystack,
        )
    )
    source_implies_early_career = _contains_any(source_context_lower, EARLY_CAREER_HINTS)
    return role_match_in_title and (
        early_career_match or entry_title_match or entry_description_match or source_implies_early_career
    )


def location_allowed(location_text: str | None, settings: AppSettings) -> bool:
    """Return True when the location passes configured filters."""

    if not location_text:
        return True
    lowered = location_text.lower()
    excluded_locations = [location.lower() for location in settings.filters.excluded_locations]
    if any(excluded in lowered for excluded in excluded_locations):
        return False
    has_us_signal = _has_us_signal(location_text)
    has_non_us_signal = _has_non_us_signal(location_text)
    if has_non_us_signal and not has_us_signal:
        return False
    if "remote" in lowered:
        return True
    allowed_locations = [location.lower() for location in settings.filters.allowed_locations]
    if "united states" in allowed_locations:
        if has_us_signal or lowered.strip() == "us":
            return True
    return any(allowed in lowered for allowed in allowed_locations)
