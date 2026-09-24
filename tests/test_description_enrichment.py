from newgrad_notifier.collectors.enrichment import extract_description_from_html


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
