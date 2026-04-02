"""Daily digest email rendering."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape

from newgrad_notifier.contracts import DigestStats, PipelineError, RankedJob, Recommendation


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


def _render_job_line(job: RankedJob) -> str:
    location = job.normalized_job.location_text or "Location not listed"
    posted = _posted_text(job)
    rationale = _job_rationale(job)
    return (
        f"- {job.normalized_job.company_name} | {job.normalized_job.title} | {location} | "
        f"posted {posted} | fit {job.ranking.fit_score} | difficulty {job.ranking.difficulty_score} | "
        f"{job.ranking.recommendation.value}\n"
        f"  Apply: {job.normalized_job.apply_url}\n"
        f"  Why: {rationale}"
    )


def _render_text_section(title: str, jobs: list[RankedJob]) -> list[str]:
    return [title, *(["(none)"] if not jobs else [_render_job_line(job) for job in jobs]), ""]


def _render_html_job(job: RankedJob) -> str:
    location = escape(job.normalized_job.location_text or "Location not listed")
    posted = escape(_posted_text(job))
    recommendation = escape(job.ranking.recommendation.value.replace("_", " "))
    rationale = escape(_job_rationale(job))
    matching = ", ".join(job.ranking.top_matching_skills[:4]) or "Relevant SWE and product engineering signals"
    tags = ", ".join(job.ranking.tags[:4]) or "entry-level"
    return f"""
    <article class="job-card">
      <div class="job-card__header">
        <div>
          <p class="eyebrow">{escape(job.normalized_job.company_name)}</p>
          <h3>{escape(job.normalized_job.title)}</h3>
        </div>
        <div class="score-pill">{job.ranking.fit_score}</div>
      </div>
      <p class="meta">{location} | Posted {posted} | Difficulty {job.ranking.difficulty_score} | {recommendation}</p>
      <p class="summary">{rationale}</p>
      <p class="subtle"><strong>Matching skills:</strong> {escape(matching)}</p>
      <p class="subtle"><strong>Tags:</strong> {escape(tags)}</p>
      <p><a href="{escape(job.normalized_job.apply_url)}">Open application</a></p>
    </article>
    """.strip()


def _render_html_section(title: str, jobs: list[RankedJob]) -> str:
    cards = "<p class=\"empty\">No roles in this section today.</p>" if not jobs else "".join(_render_html_job(job) for job in jobs)
    return f"""
    <section class="section">
      <h2>{escape(title)}</h2>
      {cards}
    </section>
    """.strip()


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
        job
        for job in sorted_jobs
        if job.ranking.fit_score >= high_signal_threshold and job.ranking.fit_score < top_priority_threshold
    ]
    lower_priority = [job for job in sorted_jobs if job.ranking.fit_score < high_signal_threshold]
    total_high_signal = len(top_matches) + len(reach_roles)
    subject = f"[NewGradNotifier] {run_date.date().isoformat()} - {total_high_signal} high-signal new roles"

    text_sections = [
        f"Daily New Grad SWE Digest for {run_date.date().isoformat()}",
        "",
        *_render_text_section("Section 1: Top new matches today", top_matches),
        *_render_text_section("Section 2: Reach roles worth applying to", reach_roles),
        *_render_text_section("Section 3: Lower-priority or mismatched roles", lower_priority),
        "Section 4: Summary stats by source",
        *(["(none)"] if not stats.source_counts else [f"- {source}: {count}" for source, count in sorted(stats.source_counts.items())]),
        "",
        "Section 5: Errors or failures",
        *(["(none)"] if not errors else [f"- {error.source_name} [{error.stage}]: {error.message}" for error in errors]),
    ]

    source_stats = "".join(
        f"<li><strong>{escape(source)}</strong>: {count}</li>" for source, count in sorted(stats.source_counts.items())
    ) or "<li>No source stats recorded.</li>"
    error_items = "".join(
        f"<li><strong>{escape(error.source_name)}</strong> [{escape(error.stage)}]: {escape(error.message)}</li>"
        for error in errors
    ) or "<li>No collection failures were reported.</li>"

    html_body = f"""
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{escape(subject)}</title>
        <style>
          body {{
            margin: 0;
            padding: 0;
            background: #0a0a0a;
            color: #fafafa;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
          }}
          .shell {{
            max-width: 760px;
            margin: 0 auto;
            padding: 32px 20px 48px;
          }}
          .hero {{
            background: linear-gradient(180deg, #111111 0%, #171717 100%);
            color: #fafafa;
            padding: 28px;
            border-radius: 18px;
            border: 1px solid #27272a;
            box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45);
          }}
          .hero h1 {{
            margin: 0 0 10px;
            font-size: 30px;
            font-weight: 700;
            letter-spacing: -0.03em;
            line-height: 1.1;
          }}
          .hero p {{
            margin: 8px 0 0;
            font-size: 15px;
            line-height: 1.5;
            color: #a1a1aa;
          }}
          .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 12px;
            margin: 20px 0 0;
          }}
          .stat {{
            background: #18181b;
            border: 1px solid #27272a;
            border-radius: 14px;
            padding: 14px 16px;
          }}
          .stat strong {{
            display: block;
            font-size: 24px;
            color: #fafafa;
            margin-bottom: 4px;
          }}
          .stat span {{
            color: #a1a1aa;
            font-size: 13px;
          }}
          .section {{
            margin-top: 26px;
          }}
          .section h2 {{
            font-size: 18px;
            margin: 0 0 14px;
            color: #fafafa;
            font-weight: 600;
            letter-spacing: -0.02em;
          }}
          .job-card {{
            background: #18181b;
            border: 1px solid #27272a;
            border-radius: 16px;
            padding: 18px 18px 14px;
            margin-bottom: 14px;
            box-shadow: 0 10px 24px rgba(0, 0, 0, 0.22);
          }}
          .job-card__header {{
            display: flex;
            justify-content: space-between;
            gap: 16px;
            align-items: start;
          }}
          .job-card h3 {{
            margin: 4px 0 0;
            font-size: 20px;
            color: #fafafa;
            font-weight: 600;
            letter-spacing: -0.02em;
            line-height: 1.2;
          }}
          .eyebrow {{
            margin: 0;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-size: 11px;
            color: #a1a1aa;
          }}
          .score-pill {{
            min-width: 48px;
            height: 48px;
            border-radius: 12px;
            background: #111111;
            border: 1px solid #3f3f46;
            color: #fafafa;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 18px;
          }}
          .meta, .subtle {{
            color: #a1a1aa;
            font-size: 14px;
            line-height: 1.5;
          }}
          .summary {{
            font-size: 15px;
            line-height: 1.6;
            margin: 12px 0;
            color: #d4d4d8;
          }}
          .empty {{
            background: #18181b;
            border: 1px dashed #3f3f46;
            border-radius: 14px;
            padding: 16px;
            color: #a1a1aa;
          }}
          .footer-card {{
            background: #18181b;
            border-radius: 16px;
            padding: 18px;
            border: 1px solid #27272a;
            color: #d4d4d8;
          }}
          ul {{
            margin: 0;
            padding-left: 18px;
          }}
          li {{
            margin: 0 0 8px;
            color: #d4d4d8;
          }}
          a {{
            color: #fafafa;
            text-decoration: none;
            font-weight: 600;
          }}
          a:hover {{
            text-decoration: underline;
          }}
        </style>
      </head>
      <body>
        <div class="shell">
          <section class="hero">
            <h1>Daily New Grad SWE Digest</h1>
            <p>{escape(run_date.date().isoformat())}</p>
            <div class="stats">
              <div class="stat"><strong>{total_high_signal}</strong><span>High-signal roles</span></div>
              <div class="stat"><strong>{stats.total_new}</strong><span>New roles</span></div>
              <div class="stat"><strong>{stats.total_errors}</strong><span>Collection errors</span></div>
            </div>
          </section>

          {_render_html_section("Top new matches today", top_matches)}
          {_render_html_section("Reach roles worth applying to", reach_roles)}
          {_render_html_section("Lower-priority or mismatched roles", lower_priority)}

          <section class="section">
            <h2>Summary stats by source</h2>
            <div class="footer-card"><ul>{source_stats}</ul></div>
          </section>

          <section class="section">
            <h2>Errors or failures</h2>
            <div class="footer-card"><ul>{error_items}</ul></div>
          </section>
        </div>
      </body>
    </html>
    """.strip()

    return RenderedEmail(subject=subject, text_body="\n".join(text_sections), html_body=html_body)


def should_send_immediate_alert(job: RankedJob, threshold: int) -> bool:
    """Return True when a job qualifies for immediate alerting."""

    return job.ranking.fit_score >= threshold and job.ranking.recommendation in {
        Recommendation.APPLY_NOW,
        Recommendation.APPLY_IF_INTERESTED,
    }
