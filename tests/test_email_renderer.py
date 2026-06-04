from datetime import UTC, datetime

from newgrad_notifier.contracts import (
    DigestStats,
    JobLifecycleState,
    NormalizedJob,
    RankedJob,
    RankingResult,
    Recommendation,
    SourceType,
)
from newgrad_notifier.notifications.email_renderer import render_daily_digest


def test_email_renderer_outputs_required_sections():
    ranked_job = RankedJob(
        normalized_job=NormalizedJob(
            canonical_key="abc",
            source_name="simplify_fixture",
            source_type=SourceType.STRUCTURED,
            source_url="examples/local_sources/simplify_jobs.json",
            apply_url="https://example.com/job",
            company_name="Figma",
            title="Software Engineer, New Grad 2027",
            title_normalized="software engineer new grad 2027",
            location_text="Remote, United States",
            location_normalized="Remote, United States",
            is_remote=True,
            posted_at=datetime(2026, 8, 20, tzinfo=UTC),
            description_text="Build with React and TypeScript.",
            description_hash="hash1",
            content_hash="hash2",
        ),
        ranking=RankingResult(
            fit_score=88,
            difficulty_score=66,
            recommendation=Recommendation.APPLY_NOW,
            fit_summary="Strong role and stack match.",
            difficulty_summary="Competitive but aligned.",
            top_matching_skills=["React", "TypeScript"],
            missing_or_weaker_skills=[],
            tags=["new_grad", "full_stack"],
        ),
        lifecycle_state=JobLifecycleState.NEW,
    )

    rendered = render_daily_digest(
        run_date=datetime(2026, 8, 22, tzinfo=UTC),
        ranked_jobs=[ranked_job],
        stats=DigestStats(source_counts={"simplify": 1}),
        errors=[],
        high_signal_threshold=65,
        top_priority_threshold=80,
    )

    assert "2026-08-22" in rendered.subject
    assert "Section 1: Top new matches today" in rendered.text_body
    assert "Apply: https://example.com/job" in rendered.text_body
    assert "Daily New Grad SWE Digest" in rendered.html_body
    assert "Apply" in rendered.html_body
    assert "Figma" in rendered.html_body
