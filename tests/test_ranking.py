from newgrad_notifier.config.settings import load_settings
from newgrad_notifier.contracts import CollectedJob, SourceType
from newgrad_notifier.normalization.normalizer import normalize_job
from newgrad_notifier.ranking.service import RankingService


def test_ranking_service_scores_high_fit_role():
    settings = load_settings("config/local_dev.toml")
    service = RankingService(settings)
    job = normalize_job(
        CollectedJob(
            source_name="simplify_fixture",
            source_type=SourceType.STRUCTURED,
            source_url="examples/local_sources/simplify_jobs.json",
            apply_url="https://boards.greenhouse.io/figma/jobs/12345",
            company_name="Figma",
            title="Software Engineer, New Grad 2027",
            location_text="Remote, United States",
            description_text="Class of 2027 software engineer role building React, TypeScript, Node.js, Python, and APIs for a product team.",
        )
    )

    result = service.rank(job)

    assert result.fit_score >= 80
    assert result.recommendation.value == "apply_now"
    assert "React" in result.top_matching_skills


def test_ranking_service_skips_mismatch_role():
    settings = load_settings("config/local_dev.toml")
    service = RankingService(settings)
    job = normalize_job(
        CollectedJob(
            source_name="simplify_fixture",
            source_type=SourceType.STRUCTURED,
            source_url="examples/local_sources/simplify_jobs.json",
            apply_url="https://example.com/sre-role",
            company_name="Datadog",
            title="Site Reliability Engineer, New Grad",
            location_text="New York, NY",
            description_text="Own infrastructure, incidents, on-call, and SRE automation.",
        )
    )

    result = service.rank(job)

    assert result.recommendation.value == "skip"
    assert result.fit_score < 50

