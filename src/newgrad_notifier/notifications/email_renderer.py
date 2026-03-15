"""Daily digest email rendering."""

from __future__ import annotations

from datetime import datetime

from newgrad_notifier.contracts import DigestStats, PipelineError, RankedJob, Recommendation


def _render_job_line(job: RankedJob) -> str:
    location = job.normalized_job.location_text or "Location not listed"
    posted = job.normalized_job.posted_at.isoformat() if job.normalized_job.posted_at else "Unknown"
    rationale = f"{job.ranking.fit_summary} {job.ranking.difficulty_summary}"
    return (
        f"- {job.normalized_job.company_name} | {job.normalized_job.title} | {location} | "
        f"posted {posted} | fit {job.ranking.fit_score} | difficulty {job.ranking.difficulty_score} | "
        f"{job.ranking.recommendation.value}\n"
        f"  Apply: {job.normalized_job.apply_url}\n"
        f"  Why: {rationale}"
    )


def render_daily_digest(
    *,
    run_date: datetime,
    ranked_jobs: list[RankedJob],
    stats: DigestStats,
    errors: list[PipelineError],
    high_signal_threshold: int,
    top_priority_threshold: int,
) -> tuple[str, str]:
    """Return the subject and plaintext digest body."""

    sorted_jobs = sorted(ranked_jobs, key=lambda item: (item.ranking.fit_score, -item.ranking.difficulty_score), reverse=True)
    top_matches = [job for job in sorted_jobs if job.ranking.fit_score >= top_priority_threshold]
    reach_roles = [
        job
        for job in sorted_jobs
        if job.ranking.fit_score >= high_signal_threshold and job.ranking.fit_score < top_priority_threshold
    ]
    lower_priority = [job for job in sorted_jobs if job.ranking.fit_score < high_signal_threshold]
    subject = f"[NewGradNotifier] {run_date.date().isoformat()} - {len(top_matches) + len(reach_roles)} high-signal new roles"

    sections = [
        f"Daily New Grad SWE Digest for {run_date.date().isoformat()}",
        "",
        "Section 1: Top new matches today",
        *(["(none)"] if not top_matches else [_render_job_line(job) for job in top_matches]),
        "",
        "Section 2: Reach roles worth applying to",
        *(["(none)"] if not reach_roles else [_render_job_line(job) for job in reach_roles]),
        "",
        "Section 3: Lower-priority or mismatched roles",
        *(["(none)"] if not lower_priority else [_render_job_line(job) for job in lower_priority]),
        "",
        "Section 4: Summary stats by source",
        *(["(none)"] if not stats.source_counts else [f"- {source}: {count}" for source, count in sorted(stats.source_counts.items())]),
        "",
        "Section 5: Errors or failures",
        *(["(none)"] if not errors else [f"- {error.source_name} [{error.stage}]: {error.message}" for error in errors]),
    ]
    return subject, "\n".join(sections)


def should_send_immediate_alert(job: RankedJob, threshold: int) -> bool:
    """Return True when a job qualifies for immediate alerting."""

    return job.ranking.fit_score >= threshold and job.ranking.recommendation in {
        Recommendation.APPLY_NOW,
        Recommendation.APPLY_IF_INTERESTED,
    }

