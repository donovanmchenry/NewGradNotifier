"""Extension hooks for generating resume-tailoring briefs from ranked jobs."""

from __future__ import annotations

from newgrad_notifier.config.settings import CandidateProfile
from newgrad_notifier.contracts import RankedJob


def build_resume_tailoring_brief(job: RankedJob, profile: CandidateProfile) -> str:
    """Return a concise brief that downstream tooling can use to tailor a resume."""

    matching_skills = ", ".join(job.ranking.top_matching_skills) or "general software engineering fundamentals"
    missing_skills = ", ".join(job.ranking.missing_or_weaker_skills) or "no major gaps identified"
    return (
        f"Tailor the resume for {job.normalized_job.company_name} - {job.normalized_job.title}. "
        f"Lead with internships ({'; '.join(profile.internships)}) and highlight {matching_skills}. "
        f"Address or de-emphasize weaker areas such as {missing_skills}. "
        f"Keep the story centered on product engineering, full-stack delivery, and shipped user-facing systems."
    )
