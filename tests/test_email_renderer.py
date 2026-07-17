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
from newgrad_notifier.notifications.email_renderer import render_daily_digest, should_send_immediate_alert


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

    assert "1 job worth a look - Aug 22" in rendered.subject
    assert "Best matches" in rendered.text_body
    assert "Why it fits: Strong role and stack match." in rendered.text_body
    assert "Competition: High (66/100)" in rendered.text_body
    assert "Apply: https://example.com/job" in rendered.text_body
    assert "Your new-grad job shortlist" in rendered.html_body
    assert "Apply now" in rendered.html_body
    assert "Figma" in rendered.html_body
    assert "simplify" not in rendered.html_body
    assert 'name="color-scheme" content="dark"' in rendered.html_body
    assert "background:#09090b" in rendered.html_body
    assert "background:#18181b" in rendered.html_body
    assert "background:#fafafa" in rendered.html_body
    assert "#3b82f6" not in rendered.html_body


def test_email_renderer_excludes_seen_jobs_and_caps_the_shortlist():
    jobs = []
    for index in range(12):
        lifecycle = JobLifecycleState.SEEN if index == 0 else JobLifecycleState.NEW
        jobs.append(
            RankedJob(
                normalized_job=NormalizedJob(
                    canonical_key=f"job-{index}",
                    source_name="fixture",
                    source_type=SourceType.STRUCTURED,
                    source_url="fixture.json",
                    apply_url=f"https://example.com/{index}",
                    company_name=f"Company {index}",
                    title="Software Engineer, New Grad 2027",
                    title_normalized="software engineer new grad 2027",
                    description_text="React and TypeScript product engineering role.",
                    description_hash=f"description-{index}",
                    content_hash=f"content-{index}",
                ),
                ranking=RankingResult(
                    fit_score=90 - index,
                    difficulty_score=50,
                    recommendation=Recommendation.APPLY_NOW,
                    fit_summary="Strong match.",
                    difficulty_summary="Reasonable reach.",
                ),
                lifecycle_state=lifecycle,
            )
        )

    rendered = render_daily_digest(
        run_date=datetime(2026, 8, 22, tzinfo=UTC),
        ranked_jobs=jobs,
        stats=DigestStats(total_new=11),
        errors=[],
        high_signal_threshold=65,
        top_priority_threshold=80,
        digest_min_fit=55,
        max_digest_jobs=5,
    )

    assert "Company 0" not in rendered.text_body
    assert rendered.text_body.count("  Apply:") == 5
    assert "5 jobs worth a look" in rendered.subject


def test_email_renderer_removes_control_characters_and_score_prefixes():
    ranked_job = RankedJob(
        normalized_job=NormalizedJob(
            canonical_key="plain-english",
            source_name="fixture",
            source_type=SourceType.STRUCTURED,
            source_url="fixture.json",
            apply_url="https://example.com/plain-english",
            company_name="Example",
            title="Software Engineer, New Grad",
            title_normalized="software engineer new grad",
            description_text="Python and React role.",
            description_hash="description",
            content_hash="content",
        ),
        ranking=RankingResult(
            fit_score=75,
            difficulty_score=45,
            recommendation=Recommendation.APPLY_IF_INTERESTED,
            fit_summary="Fit 75/100 \x021strong Python overlap; product work aligns.",
            difficulty_summary="Difficulty 45/100 \x021high applicant volume.",
            top_matching_skills=["Python", "React"],
        ),
    )

    rendered = render_daily_digest(
        run_date=datetime(2026, 8, 22, tzinfo=UTC),
        ranked_jobs=[ranked_job],
        stats=DigestStats(total_collected=20, total_new=10),
        errors=[],
        high_signal_threshold=65,
        top_priority_threshold=80,
    )

    assert "\x02" not in rendered.text_body
    assert "1strong" not in rendered.text_body
    assert "Why it fits: Strong Python overlap. Product work aligns." in rendered.text_body
    assert "Keep in mind: High applicant volume." in rendered.text_body


def test_immediate_alert_only_fires_for_actionable_lifecycle():
    ranked_job = RankedJob(
        normalized_job=NormalizedJob(
            canonical_key="alert-job",
            source_name="fixture",
            source_type=SourceType.STRUCTURED,
            source_url="fixture.json",
            apply_url="https://example.com/alert-job",
            company_name="Example",
            title="Software Engineer, New Grad 2027",
            title_normalized="software engineer new grad 2027",
            description_text="Entry-level product engineering role.",
            description_hash="description",
            content_hash="content",
        ),
        ranking=RankingResult(
            fit_score=95,
            difficulty_score=50,
            recommendation=Recommendation.APPLY_NOW,
            fit_summary="Strong match.",
            difficulty_summary="Competitive.",
        ),
        lifecycle_state=JobLifecycleState.NEW,
    )

    assert should_send_immediate_alert(ranked_job, threshold=92)
    assert not should_send_immediate_alert(
        ranked_job.model_copy(update={"lifecycle_state": JobLifecycleState.SEEN}),
        threshold=92,
    )
