"""Extract application-relevant facts from job descriptions."""

from __future__ import annotations

import re
from typing import Any

_SALARY_PATTERN = re.compile(
    r"(?:USD\s*)?\$\s?\d{2,3}(?:,\d{3})?(?:\.\d{2})?"
    r"(?:\s*(?:-|to|–|—)\s*(?:USD\s*)?\$?\s?\d{2,3}(?:,\d{3})?(?:\.\d{2})?)?"
    r"(?:\s*(?:per\s+year|annually|/\s*(?:year|yr|hour|hr)))?",
    re.IGNORECASE,
)
_DEADLINE_PATTERN = re.compile(
    r"(?:apply\s+by|application\s+deadline|deadline)\s*[:\-]?\s*"
    r"([A-Z][a-z]+\s+\d{1,2}(?:,\s*\d{4})?|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})",
    re.IGNORECASE,
)
_GRAD_YEAR_PATTERN = re.compile(r"\b(?:class\s+of|graduat(?:e|ing|ion)[^\d]{0,20})(20\d{2})\b", re.IGNORECASE)


def extract_job_details(
    *,
    title: str,
    description: str,
    location: str | None,
    is_remote: bool,
) -> dict[str, Any]:
    """Return normalized details useful when deciding whether to apply."""

    text = " ".join(f"{title} {description} {location or ''}".split())
    lowered = text.lower()
    salary_match = _SALARY_PATTERN.search(text)
    deadline_match = _DEADLINE_PATTERN.search(text)
    graduation_years = sorted(set(_GRAD_YEAR_PATTERN.findall(text)))

    if is_remote or "fully remote" in lowered or "remote role" in lowered:
        work_mode = "Remote"
    elif "hybrid" in lowered:
        work_mode = "Hybrid"
    elif any(term in lowered for term in ("on-site", "onsite", "in office", "in-office")):
        work_mode = "On-site"
    else:
        work_mode = "Not specified"

    if any(
        term in lowered
        for term in (
            "no visa sponsorship",
            "cannot provide visa sponsorship",
            "unable to sponsor",
            "will not sponsor",
            "does not sponsor",
            "without sponsorship now or in the future",
        )
    ):
        sponsorship = "Not offered"
    elif any(term in lowered for term in ("visa sponsorship available", "sponsorship is available", "will sponsor")):
        sponsorship = "Available"
    elif "sponsor" in lowered or "sponsorship" in lowered:
        sponsorship = "Check posting"
    else:
        sponsorship = "Not specified"

    if any(term in lowered for term in ("must be a u.s. citizen", "must be a us citizen", "u.s. citizenship required", "us citizenship required")):
        citizenship = "U.S. citizenship required"
    elif "u.s. person" in lowered or "us person" in lowered:
        citizenship = "U.S. person requirement"
    else:
        citizenship = "Not specified"

    if any(term in lowered for term in ("active security clearance", "current security clearance")):
        clearance = "Active clearance required"
    elif any(term in lowered for term in ("ability to obtain a security clearance", "eligible for a security clearance")):
        clearance = "Must be eligible for clearance"
    elif "security clearance" in lowered:
        clearance = "Check posting"
    else:
        clearance = "Not specified"

    return {
        "salary": salary_match.group(0).strip() if salary_match else None,
        "work_mode": work_mode,
        "sponsorship": sponsorship,
        "citizenship": citizenship,
        "clearance": clearance,
        "graduation_years": graduation_years,
        "application_deadline": deadline_match.group(1).strip() if deadline_match else None,
    }
