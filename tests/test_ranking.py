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


def test_sparse_explicit_new_grad_role_reaches_digest_threshold():
    settings = load_settings("config/local_dev.toml")
    service = RankingService(settings)
    job = normalize_job(
        CollectedJob(
            source_name="speedyapply_2027",
            source_type=SourceType.STRUCTURED,
            source_url="https://github.com/speedyapply/2027-SWE-College-Jobs",
            apply_url="https://jobs.ashbyhq.com/nooks/311d6e70-5cfa-4e80-89f6-fe00ac1f9f53",
            company_name="Nooks",
            title="Software Engineer - New Grad",
            location_text="San Francisco, CA",
            description_text="",
        )
    )

    result = service.rank(job)

    assert result.fit_score >= 60
    assert result.recommendation.value == "apply_if_interested"
    assert result.scorer == "heuristic"


def test_entry_level_role_is_not_penalized_for_working_with_senior_engineers():
    settings = load_settings("config/local_dev.toml")
    service = RankingService(settings)
    job_with_senior_teammates = normalize_job(
        CollectedJob(
            source_name="fixture",
            source_type=SourceType.STRUCTURED,
            source_url="fixture.json",
            apply_url="https://example.com/software-engineer-i",
            company_name="Example",
            title="Software Engineer I",
            location_text="New York, NY",
            description_text=(
                "Build backend APIs with Python and React while collaborating with experienced teammates "
                "under the guidance of senior engineers."
            ),
        )
    )
    comparison_job = normalize_job(
        CollectedJob(
            source_name="fixture",
            source_type=SourceType.STRUCTURED,
            source_url="fixture.json",
            apply_url="https://example.com/software-engineer-i-comparison",
            company_name="Example",
            title="Software Engineer I",
            location_text="New York, NY",
            description_text=(
                "Build backend APIs with Python and React while collaborating with experienced teammates "
                "under the guidance of experienced engineers."
            ),
        )
    )

    result = service.rank(job_with_senior_teammates)
    comparison_result = service.rank(comparison_job)

    assert result.fit_score == comparison_result.fit_score


def test_entry_level_title_is_penalized_for_explicit_experience_requirement():
    settings = load_settings("config/local_dev.toml")
    service = RankingService(settings)
    job = normalize_job(
        CollectedJob(
            source_name="fixture",
            source_type=SourceType.STRUCTURED,
            source_url="fixture.json",
            apply_url="https://example.com/experienced-software-engineer-i",
            company_name="Example",
            title="Software Engineer I",
            location_text="New York, NY",
            description_text="Build backend APIs with Python. Requires 5+ years of professional experience.",
        )
    )

    result = service.rank(job)

    assert result.fit_score < 60
