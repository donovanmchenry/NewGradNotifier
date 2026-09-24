import logging
from datetime import UTC, datetime

from newgrad_notifier.collectors.enrichment import enrich_sparse_jobs, extract_description_from_html
from newgrad_notifier.contracts import NormalizedJob, SourceType


def test_extract_description_from_job_posting_json_ld():
    html = """
    <script type="application/ld+json">
      {"@type":"JobPosting","description":"<p>Build customer-facing products with React, TypeScript, Python, and APIs.</p>"}
    </script>
    """

    assert extract_description_from_html(html) == (
        "Build customer-facing products with React, TypeScript, Python, and APIs."
    )


def test_extract_description_from_open_graph_fallback():
    html = """
    <html>
      <head>
        <meta property="og:description" content="Build scalable backend APIs with Python and React." />
      </head>
      <body><main>Navigation without a recognized job-description selector.</main></body>
    </html>
    """

    assert extract_description_from_html(html) == "Build scalable backend APIs with Python and React."


def test_enrichment_records_best_effort_fetch_failures():
    class FailingHttpClient:
        def get_text(self, _url: str) -> str:
            raise RuntimeError("blocked by source")

    job = NormalizedJob(
        canonical_key="example:123",
        source_name="structured:test",
        source_type=SourceType.STRUCTURED,
        source_url="https://example.com/feed",
        apply_url="https://example.com/jobs/123",
        company_name="Example",
        title="Software Engineer, New Grad",
        title_normalized="software engineer new grad",
        location_text="Remote",
        location_normalized="Remote",
        is_remote=True,
        description_text="",
        description_hash="empty",
        content_hash="content",
        first_seen_at=datetime.now(UTC),
    )
    errors = []

    result = enrich_sparse_jobs(
        [job],
        http_client=FailingHttpClient(),
        max_fetches=1,
        min_characters=160,
        logger=logging.getLogger(__name__),
        errors=errors,
    )

    assert result == [job]
    assert len(errors) == 1
    assert errors[0].source_name == "structured:test"
    assert errors[0].stage == "enrich"
    assert errors[0].message == "Description enrichment skipped"
    assert "blocked by source" in errors[0].detail
