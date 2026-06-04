"""Daily digest email rendering."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape

from newgrad_notifier.contracts import DigestStats, JobLifecycleState, PipelineError, RankedJob, Recommendation


@dataclass(slots=True)
class RenderedEmail:
    """Rendered email payload with plaintext and HTML bodies."""

    subject: str
    text_body: str
    html_body: str


def _posted_text(job: RankedJob) -> str:
    return job.normalized_job.posted_at.date().isoformat() if job.normalized_job.posted_at else "Unknown"


def _job_rationale(job: RankedJob) -> str:
    return f"{job.ranking.fit_summary} {job.ranking.difficulty_summary}".strip()


def _days_since(dt: datetime, run_date: datetime) -> int:
    rd = run_date if run_date.tzinfo is not None else run_date.replace(tzinfo=UTC)
    d = dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    return max(0, (rd - d).days)


def _cross_analysis_text(job: RankedJob, run_date: datetime) -> str:
    if job.lifecycle_state == JobLifecycleState.NEW:
        return ""
    days = _days_since(job.normalized_job.first_seen_at, run_date)
    parts = [f"first seen {days} day{'s' if days != 1 else ''} ago"]
    if job.prev_fit_score is not None:
        delta = job.ranking.fit_score - job.prev_fit_score
        sign = "+" if delta >= 0 else ""
        parts.append(f"prev fit {job.prev_fit_score} ({sign}{delta})")
    if job.lifecycle_state == JobLifecycleState.REOPENED:
        parts.append("reopened")
    return " | ".join(parts)


def _render_job_line(job: RankedJob, run_date: datetime) -> str:
    location = job.normalized_job.location_text or "Location not listed"
    posted = _posted_text(job)
    rationale = _job_rationale(job)
    recommendation = job.ranking.recommendation.value.replace("_", " ")
    lines = [
        f"- {job.normalized_job.company_name} | {job.normalized_job.title} | {location} | "
        f"posted {posted} | fit {job.ranking.fit_score} | difficulty {job.ranking.difficulty_score} | "
        f"{recommendation}",
        f"  Apply: {job.normalized_job.apply_url}",
        f"  Why: {rationale}",
    ]
    cross = _cross_analysis_text(job, run_date)
    if cross:
        lines.append(f"  Cross-analysis: {cross}")
    return "\n".join(lines)


def _render_text_section(title: str, jobs: list[RankedJob], run_date: datetime) -> list[str]:
    return [title, *(["(none)"] if not jobs else [_render_job_line(job, run_date) for job in jobs]), ""]


def _render_html_job(job: RankedJob, run_date: datetime) -> str:
    location = escape(job.normalized_job.location_text or "Location not listed")
    posted = escape(_posted_text(job))
    recommendation = escape(job.ranking.recommendation.value.replace("_", " "))
    rationale = escape(_job_rationale(job))
    matching = escape(", ".join(job.ranking.top_matching_skills[:4]) or "Relevant SWE signals")
    cross = _cross_analysis_text(job, run_date)
    cross_html = f'<br><em style="font-size:13px; color:#555555;">{escape(cross)}</em>' if cross else ""
    return (
        f'<div style="margin:0 0 20px; padding:0 0 20px; border-bottom:1px solid #cccccc;">'
        f'<strong>{escape(job.normalized_job.company_name)}</strong> &mdash; {escape(job.normalized_job.title)}<br>'
        f'{location} | Posted {posted} | Fit: {job.ranking.fit_score} | Difficulty: {job.ranking.difficulty_score} | {recommendation}'
        f'{cross_html}<br>'
        f'{rationale}<br>'
        f'<span style="font-size:13px; color:#555555;">Skills: {matching}</span><br>'
        f'<a href="{escape(job.normalized_job.apply_url)}" style="color:#000000;">Apply</a>'
        f'</div>'
    )


def _render_html_section(title: str, jobs: list[RankedJob], run_date: datetime) -> str:
    if not jobs:
        entries = "<p><em>No roles in this section today.</em></p>"
    else:
        entries = "\n".join(_render_html_job(job, run_date) for job in jobs)
    return (
        f'<h3 style="margin:28px 0 12px; font-size:16px; border-bottom:1px solid #000000; padding-bottom:4px;">'
        f'{escape(title)}</h3>\n{entries}'
    )


def render_daily_digest(
    *,
    run_date: datetime,
    ranked_jobs: list[RankedJob],
    stats: DigestStats,
    errors: list[PipelineError],
    high_signal_threshold: int,
    top_priority_threshold: int,
) -> RenderedEmail:
    """Return the rendered daily digest."""

    sorted_jobs = sorted(ranked_jobs, key=lambda item: (item.ranking.fit_score, -item.ranking.difficulty_score), reverse=True)
    top_matches = [job for job in sorted_jobs if job.ranking.fit_score >= top_priority_threshold]
    reach_roles = [
        job for job in sorted_jobs
        if high_signal_threshold <= job.ranking.fit_score < top_priority_threshold
    ]
    lower_priority = [job for job in sorted_jobs if job.ranking.fit_score < high_signal_threshold]
    total_high_signal = len(top_matches) + len(reach_roles)
    subject = f"[NewGradNotifier] {run_date.date().isoformat()} - {total_high_signal} high-signal new roles"

    text_sections = [
        f"Daily New Grad SWE Digest -- {run_date.date().isoformat()}",
        "",
        *_render_text_section("Section 1: Top new matches today", top_matches, run_date),
        *_render_text_section("Section 2: Reach roles worth applying to", reach_roles, run_date),
        *_render_text_section("Section 3: Lower-priority or mismatched roles", lower_priority, run_date),
        "Section 4: Summary stats by source",
        *(["(none)"] if not stats.source_counts else [f"- {source}: {count}" for source, count in sorted(stats.source_counts.items())]),
        "",
        "Section 5: Errors or failures",
        *(["(none)"] if not errors else [f"- {error.source_name} [{error.stage}]: {error.message}" for error in errors]),
    ]

    source_stats_html = "".join(
        f"<li>{escape(source)}: {count}</li>"
        for source, count in sorted(stats.source_counts.items())
    ) or "<li>No source stats recorded.</li>"
    error_items_html = "".join(
        f"<li><strong>{escape(error.source_name)}</strong> [{escape(error.stage)}]: {escape(error.message)}</li>"
        for error in errors
    ) or "<li>No collection failures reported.</li>"

    html_sections = "\n".join([
        _render_html_section("Top new matches today", top_matches, run_date),
        _render_html_section("Reach roles worth applying to", reach_roles, run_date),
        _render_html_section("Lower-priority or mismatched roles", lower_priority, run_date),
    ])

    html_body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(subject)}</title>
</head>
<body style="margin:0; padding:0; background:#ffffff; color:#000000; font-family:'Times New Roman', Times, serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="#ffffff">
    <tr>
      <td align="center">
        <table role="presentation" width="640" cellpadding="0" cellspacing="0" style="max-width:640px; width:100%;">
          <tr>
            <td style="padding:32px 24px;">
              <h1 style="margin:0 0 4px; font-size:22px; font-weight:bold; font-family:'Times New Roman', Times, serif;">Daily New Grad SWE Digest</h1>
              <p style="margin:0 0 4px; font-size:14px;">{escape(run_date.date().isoformat())}</p>
              <p style="margin:0 0 0; font-size:14px;">{total_high_signal} high-signal &nbsp;|&nbsp; {stats.total_new} new today &nbsp;|&nbsp; {stats.total_errors} errors</p>
              <hr style="border:none; border-top:2px solid #000000; margin:16px 0 0;">
              {html_sections}
              <h3 style="margin:28px 0 8px; font-size:16px; border-bottom:1px solid #000000; padding-bottom:4px;">Summary stats by source</h3>
              <ul style="margin:0 0 24px; padding-left:20px; font-size:14px;">{source_stats_html}</ul>
              <h3 style="margin:0 0 8px; font-size:16px; border-bottom:1px solid #000000; padding-bottom:4px;">Collection errors</h3>
              <ul style="margin:0; padding-left:20px; font-size:14px;">{error_items_html}</ul>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    return RenderedEmail(subject=subject, text_body="\n".join(text_sections), html_body=html_body)


def should_send_immediate_alert(job: RankedJob, threshold: int) -> bool:
    """Return True when a job qualifies for immediate alerting."""
    return job.ranking.fit_score >= threshold and job.ranking.recommendation in {
        Recommendation.APPLY_NOW,
        Recommendation.APPLY_IF_INTERESTED,
    }
