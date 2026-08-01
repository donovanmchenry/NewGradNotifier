from datetime import UTC, datetime, timedelta

from newgrad_notifier.contracts import CollectedJob, SourceType
from newgrad_notifier.normalization.normalizer import normalize_job
from newgrad_notifier.pipeline import is_fresh_listing, run_pipeline_once


def test_two_pipeline_runs_only_digest_jobs_once(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("EMAIL_PROVIDER", "console")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "pipeline.db"))

    run_pipeline_once("config/local_dev.toml")
    first_output = capsys.readouterr().out
    run_pipeline_once("config/local_dev.toml")
    second_output = capsys.readouterr().out

    assert "jobs worth a look" in first_output
    assert second_output == ""
    assert "Apply: https://boards.greenhouse.io/figma/jobs/12345" not in second_output


def test_old_backfilled_listing_is_not_email_fresh():
    reference_time = datetime(2026, 8, 1, 12, tzinfo=UTC)
    job = normalize_job(
        CollectedJob(
            source_name="speedyapply_2027",
            source_type=SourceType.STRUCTURED,
            source_url="https://github.com/speedyapply/2027-SWE-College-Jobs",
            apply_url="https://jobs.ashbyhq.com/example/job-id",
            company_name="Example",
            title="Software Engineer - New Grad",
            location_text="Remote, United States",
            posted_at=reference_time - timedelta(days=20),
        )
    )

    assert is_fresh_listing(job, reference_time, max_age_days=7) is False
    assert is_fresh_listing(job, reference_time, max_age_days=30) is True
