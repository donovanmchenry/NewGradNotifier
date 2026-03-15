from newgrad_notifier.contracts import CollectedJob, SourceType
from newgrad_notifier.dedupe.service import BatchDeduper
from newgrad_notifier.normalization.normalizer import normalize_job


def test_batch_deduper_merges_duplicate_jobs():
    job_a = normalize_job(
        CollectedJob(
            source_name="simplify_fixture",
            source_type=SourceType.STRUCTURED,
            source_url="examples/local_sources/simplify_jobs.json",
            apply_url="https://boards.greenhouse.io/figma/jobs/12345",
            company_name="Figma",
            title="Software Engineer, New Grad 2027",
            external_job_id="figma-ng-2027",
            location_text="Remote, United States",
            description_text="Build with React and TypeScript.",
        )
    )
    job_b = normalize_job(
        CollectedJob(
            source_name="greenhouse:Figma",
            source_type=SourceType.ATS,
            source_url="examples/local_sources/greenhouse_board.json",
            apply_url="https://boards.greenhouse.io/figma/jobs/12345",
            company_name="Figma",
            title="Software Engineer, New Grad 2027",
            external_job_id="figma-ng-2027",
            location_text="Remote, United States",
            description_text="Build collaborative product experiences with React and TypeScript.",
        )
    )

    result = BatchDeduper().dedupe([job_a, job_b])

    assert result.duplicate_count == 1
    assert len(result.unique_jobs) == 1
    assert "greenhouse:Figma" in result.unique_jobs[0].metadata["seen_in_sources"]

