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


def test_batch_deduper_normalizes_ats_application_suffixes():
    job_a = normalize_job(
        CollectedJob(
            source_name="repo_a",
            source_type=SourceType.STRUCTURED,
            source_url="a.json",
            apply_url="https://jobs.ashbyhq.com/netic/job-123/application?embed=true",
            company_name="Cybernetic Labs",
            title="Software Engineer New Grad",
            location_text="San Francisco, CA",
        )
    )
    job_b = normalize_job(
        CollectedJob(
            source_name="repo_b",
            source_type=SourceType.STRUCTURED,
            source_url="b.md",
            apply_url="https://jobs.ashbyhq.com/netic/job-123",
            company_name="Netic",
            title="Software Engineer - New Grad",
            location_text="SF",
        )
    )

    result = BatchDeduper().dedupe([job_a, job_b])

    assert result.duplicate_count == 1
    assert len(result.unique_jobs) == 1


def test_batch_deduper_keeps_distinct_requisitions_with_same_company_and_title():
    common = {
        "source_name": "speedyapply_2027",
        "source_type": SourceType.STRUCTURED,
        "source_url": "jobs.md",
        "company_name": "IXL Learning",
        "title": "Software Engineer - New Grad",
        "description_text": "",
    }
    san_mateo = normalize_job(
        CollectedJob(
            **common,
            apply_url="https://www.ixl.com/company/jobs?gh_jid=8615710002",
            location_text="San Mateo, CA",
        )
    )
    raleigh = normalize_job(
        CollectedJob(
            **common,
            apply_url="https://www.ixl.com/company/jobs?gh_jid=8615717002",
            location_text="Raleigh, NC",
        )
    )

    result = BatchDeduper().dedupe([san_mateo, raleigh])

    assert result.duplicate_count == 0
    assert len(result.unique_jobs) == 2
