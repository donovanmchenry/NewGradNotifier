"""Daily digest email rendering."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
import re

from newgrad_notifier.contracts import DigestStats, JobLifecycleState, PipelineError, RankedJob, Recommendation
from newgrad_notifier.tracking.security import build_tracking_url


@dataclass(slots=True)
class RenderedEmail:
    """Rendered email payload with plaintext and HTML bodies."""

    subject: str
    text_body: str
    html_body: str
    job_count: int = 0


def _clean_plain_text(value: str, label: str) -> str:
    """Turn stored scorer prose into short, readable email copy."""

    value = re.sub(r"[\x00-\x1f\x7f-\x9f]\d?", " ", value)
    value = value.translate(str.maketrans({"\u2013": "-", "\u2014": "-", "\u2011": "-", "\u2018": "'", "\u2019": "'"}))
    value = re.sub(rf"^{label}\s+\d+/100\s*[-:]*\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r";\s*", ". ", value)
    value = re.sub(r"\s+", " ", value).strip(" .-")
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", value) if part.strip()]
    sentences = [part[0].upper() + part[1:] for part in sentences]
    value = " ".join(sentences[:2])
    if not value:
        return "No additional detail was available."
    value = value[0].upper() + value[1:]
    return value if value.endswith((".", "!", "?")) else f"{value}."


def _match_label(score: int) -> str:
    if score >= 80:
        return "Excellent"
    if score >= 70:
        return "Strong"
    if score >= 60:
        return "Good"
    return "Possible"


def _competition_label(score: int) -> str:
    if score >= 70:
        return "Very high"
    if score >= 55:
        return "High"
    if score >= 40:
        return "Moderate"
    return "Typical"


def _recommendation_text(recommendation: Recommendation) -> str:
    return {
        Recommendation.APPLY_NOW: "Apply soon",
        Recommendation.APPLY_IF_INTERESTED: "Worth applying",
        Recommendation.LOW_PRIORITY: "Optional",
        Recommendation.SKIP: "Skip",
    }[recommendation]


def _readable_date(value: datetime | None) -> str:
    if value is None:
        return "date not listed"
    return f"{value.strftime('%b')} {value.day}"


def _run_date_text(value: datetime) -> str:
    return f"{value.strftime('%A, %B')} {value.day}"


def _job_detail_items(job: RankedJob) -> list[str]:
    details = job.normalized_job.metadata.get("job_details", {})
    items: list[str] = []
    for label, key in (
        ("Work mode", "work_mode"),
        ("Salary", "salary"),
        ("Sponsorship", "sponsorship"),
        ("Citizenship", "citizenship"),
        ("Clearance", "clearance"),
        ("Deadline", "application_deadline"),
    ):
        value = details.get(key)
        if value and value != "Not specified":
            items.append(f"{label}: {value}")
    graduation_years = details.get("graduation_years") or []
    if graduation_years:
        items.append(f"Graduation: {', '.join(graduation_years)}")
    return items


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


def _render_job_line(
    job: RankedJob,
    run_date: datetime,
    tracking_base_url: str,
    tracking_secret: str,
) -> str:
    location = job.normalized_job.location_text or "Location not listed"
    recommendation = _recommendation_text(job.ranking.recommendation)
    fit_summary = _clean_plain_text(job.ranking.fit_summary, "Fit")
    difficulty_summary = _clean_plain_text(job.ranking.difficulty_summary, "Difficulty")
    matching = ", ".join(job.ranking.top_matching_skills[:5]) or "general software engineering experience"
    lines = [
        f"- {job.normalized_job.company_name} - {job.normalized_job.title}",
        f"  {location} | Posted {_readable_date(job.normalized_job.posted_at)}",
        f"  Recommendation: {recommendation}",
        f"  Match: {_match_label(job.ranking.fit_score)} ({job.ranking.fit_score}/100) | "
        f"Competition: {_competition_label(job.ranking.difficulty_score)} ({job.ranking.difficulty_score}/100)",
        f"  Why it fits: {fit_summary}",
        f"  Keep in mind: {difficulty_summary}",
        f"  Matching experience: {matching}",
        *([f"  Details: {' | '.join(_job_detail_items(job))}"] if _job_detail_items(job) else []),
        f"  Apply: {job.normalized_job.apply_url}",
    ]
    if tracking_base_url and tracking_secret:
        lines.append(
            "  Track: "
            + build_tracking_url(
                tracking_base_url,
                job.normalized_job.canonical_key,
                tracking_secret,
            )
        )
    cross = _cross_analysis_text(job, run_date)
    if cross:
        lines.append(f"  Cross-analysis: {cross}")
    return "\n".join(lines)


def _render_text_section(
    title: str,
    jobs: list[RankedJob],
    run_date: datetime,
    tracking_base_url: str,
    tracking_secret: str,
) -> list[str]:
    return [
        title,
        *(
            ["(none)"]
            if not jobs
            else [_render_job_line(job, run_date, tracking_base_url, tracking_secret) for job in jobs]
        ),
        "",
    ]


def _render_html_job(
    job: RankedJob,
    run_date: datetime,
    tracking_base_url: str,
    tracking_secret: str,
) -> str:
    location = escape(job.normalized_job.location_text or "Location not listed")
    posted = escape(_readable_date(job.normalized_job.posted_at))
    recommendation = escape(_recommendation_text(job.ranking.recommendation))
    fit_summary = escape(_clean_plain_text(job.ranking.fit_summary, "Fit"))
    difficulty_summary = escape(_clean_plain_text(job.ranking.difficulty_summary, "Difficulty"))
    matching = escape(", ".join(job.ranking.top_matching_skills[:5]) or "General software engineering experience")
    details = _job_detail_items(job)
    details_html = (
        f'<p style="margin:0 0 16px; font-size:13px; color:#d4d4d8;"><strong>Job details:</strong> '
        f'{escape(" · ".join(details))}</p>'
        if details
        else ""
    )
    tracking_html = ""
    if tracking_base_url and tracking_secret:
        action_links = []
        for action, label in (("saved", "Save"), ("applied", "Mark applied"), ("ignored", "Not interested")):
            url = build_tracking_url(
                tracking_base_url,
                job.normalized_job.canonical_key,
                tracking_secret,
                action=action,
            )
            action_links.append(
                f'<a href="{escape(url)}" style="color:#d4d4d8; text-decoration:underline; margin-right:12px;">{label}</a>'
            )
        tracking_html = f'<p style="margin:14px 0 0; font-size:13px;">{"".join(action_links)}</p>'
    cross = _cross_analysis_text(job, run_date)
    cross_html = f'<p style="margin:10px 0 0; font-size:12px; color:#a1a1aa;">{escape(cross)}</p>' if cross else ""
    return (
        f'<div style="margin:0 0 16px; padding:20px; background:#18181b; border:1px solid #27272a; border-radius:8px;">'
        f'<p style="margin:0 0 4px; font-size:17px; line-height:1.35; color:#fafafa;"><strong>{escape(job.normalized_job.company_name)}</strong></p>'
        f'<p style="margin:0 0 8px; font-size:15px; line-height:1.4; color:#e4e4e7;">{escape(job.normalized_job.title)}</p>'
        f'<p style="margin:0 0 12px; font-size:13px; color:#a1a1aa;">{location} &nbsp;&bull;&nbsp; Posted {posted}</p>'
        f'<p style="margin:0 0 10px; font-size:14px;"><strong>{recommendation}</strong> &nbsp;&bull;&nbsp; '
        f'{_match_label(job.ranking.fit_score)} match ({job.ranking.fit_score}/100) &nbsp;&bull;&nbsp; '
        f'{_competition_label(job.ranking.difficulty_score)} competition ({job.ranking.difficulty_score}/100)</p>'
        f'<p style="margin:0 0 8px; font-size:14px; line-height:1.5;"><strong>Why it fits:</strong> {fit_summary}</p>'
        f'<p style="margin:0 0 8px; font-size:14px; line-height:1.5;"><strong>Keep in mind:</strong> {difficulty_summary}</p>'
        f'<p style="margin:0 0 16px; font-size:13px; color:#a1a1aa;"><strong>Matching experience:</strong> {matching}</p>'
        f'{details_html}'
        f'<a href="{escape(job.normalized_job.apply_url)}" style="display:inline-block; padding:9px 14px; background:#fafafa; color:#18181b; text-decoration:none; border:1px solid #fafafa; border-radius:6px; font-size:14px; font-weight:bold;">Apply now</a>'
        f'{tracking_html}'
        f'{cross_html}'
        f'</div>'
    )


def _render_html_section(
    title: str,
    jobs: list[RankedJob],
    run_date: datetime,
    tracking_base_url: str,
    tracking_secret: str,
) -> str:
    if not jobs:
        entries = "<p><em>No roles in this section today.</em></p>"
    else:
        entries = "\n".join(
            _render_html_job(job, run_date, tracking_base_url, tracking_secret) for job in jobs
        )
    return (
        f'<h2 style="margin:28px 0 12px; font-size:18px; color:#fafafa;">'
        f'{escape(title)}</h2>\n{entries}'
    )


def render_daily_digest(
    *,
    run_date: datetime,
    ranked_jobs: list[RankedJob],
    stats: DigestStats,
    errors: list[PipelineError],
    high_signal_threshold: int,
    top_priority_threshold: int,
    digest_min_fit: int = 0,
    max_digest_jobs: int = 10,
    tracking_base_url: str = "",
    tracking_secret: str = "",
) -> RenderedEmail:
    """Return the rendered daily digest."""

    eligible_jobs = [
        job
        for job in ranked_jobs
        if job.lifecycle_state in {JobLifecycleState.NEW, JobLifecycleState.REOPENED}
        and job.ranking.fit_score >= digest_min_fit
        and job.ranking.recommendation != Recommendation.SKIP
    ]
    sorted_jobs = sorted(
        eligible_jobs,
        key=lambda item: (item.ranking.fit_score, -item.ranking.difficulty_score),
        reverse=True,
    )[:max_digest_jobs]
    top_matches = [job for job in sorted_jobs if job.ranking.fit_score >= top_priority_threshold]
    reach_roles = [
        job for job in sorted_jobs
        if high_signal_threshold <= job.ranking.fit_score < top_priority_threshold
    ]
    lower_priority = [job for job in sorted_jobs if digest_min_fit <= job.ranking.fit_score < high_signal_threshold]
    subject = (
        f"[NewGradNotifier] {len(sorted_jobs)} job{'s' if len(sorted_jobs) != 1 else ''} worth a look - "
        f"{run_date.strftime('%b')} {run_date.day}"
    )
    if not sorted_jobs:
        subject = f"[NewGradNotifier] No strong new matches - {run_date.strftime('%b')} {run_date.day}"

    text_sections = [
        f"Your new-grad job shortlist - {_run_date_text(run_date)}",
        f"{len(sorted_jobs)} role{'s' if len(sorted_jobs) != 1 else ''} worth a look from {stats.total_new} new listings.",
        "",
        *_render_text_section("Best matches", top_matches, run_date, tracking_base_url, tracking_secret),
        *_render_text_section("Also worth a look", reach_roles, run_date, tracking_base_url, tracking_secret),
        *_render_text_section("Lower priority", lower_priority, run_date, tracking_base_url, tracking_secret),
        "Search details",
        f"- Checked {stats.total_collected} listings and found {stats.total_new} jobs you had not seen before.",
        f"- Source issues: {len(errors)}",
        "",
        *([] if not errors else ["Source notes", *[f"- {error.source_name}: {error.message}" for error in errors]]),
    ]

    error_html = ""
    if errors:
        error_items_html = "".join(
            f"<li><strong>{escape(error.source_name)}</strong>: {escape(error.message)}</li>" for error in errors
        )
        error_html = (
            '<h2 style="margin:28px 0 8px; font-size:18px; color:#fafafa;">Source notes</h2>'
            f'<ul style="margin:0; padding-left:20px; font-size:13px; color:#a1a1aa;">{error_items_html}</ul>'
        )

    html_sections = "\n".join([
        _render_html_section("Best matches", top_matches, run_date, tracking_base_url, tracking_secret),
        _render_html_section("Also worth a look", reach_roles, run_date, tracking_base_url, tracking_secret),
        _render_html_section("Lower priority", lower_priority, run_date, tracking_base_url, tracking_secret),
    ])

    html_body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark">
  <meta name="supported-color-schemes" content="dark">
  <title>{escape(subject)}</title>
</head>
<body style="margin:0; padding:0; background:#09090b; color:#e4e4e7; font-family:Arial, Helvetica, sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="#09090b">
    <tr>
      <td align="center">
        <table role="presentation" width="640" cellpadding="0" cellspacing="0" style="max-width:640px; width:100%;">
          <tr>
            <td style="padding:32px 20px 40px;">
              <h1 style="margin:0 0 6px; font-size:24px; line-height:1.25; color:#fafafa;">Your new-grad job shortlist</h1>
              <p style="margin:0 0 6px; font-size:14px; color:#a1a1aa;">{escape(_run_date_text(run_date))}</p>
              <p style="margin:0 0 24px; font-size:15px; line-height:1.5; color:#d4d4d8;">{len(sorted_jobs)} role{'s' if len(sorted_jobs) != 1 else ''} worth a look from {stats.total_new} new listings.</p>
              {html_sections}
              <p style="margin:28px 0 0; padding-top:16px; border-top:1px solid #27272a; font-size:12px; line-height:1.5; color:#a1a1aa;">Search details: {stats.total_collected} listings checked &nbsp;&bull;&nbsp; {stats.total_new} new &nbsp;&bull;&nbsp; {len(errors)} source issue{'s' if len(errors) != 1 else ''}</p>
              {error_html}
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    return RenderedEmail(
        subject=subject,
        text_body="\n".join(text_sections),
        html_body=html_body,
        job_count=len(sorted_jobs),
    )


def should_send_immediate_alert(job: RankedJob, threshold: int) -> bool:
    """Return True when a job qualifies for immediate alerting."""
    return (
        job.lifecycle_state in {JobLifecycleState.NEW, JobLifecycleState.REOPENED}
        and job.ranking.fit_score >= threshold
        and job.ranking.recommendation in {Recommendation.APPLY_NOW, Recommendation.APPLY_IF_INTERESTED}
    )
