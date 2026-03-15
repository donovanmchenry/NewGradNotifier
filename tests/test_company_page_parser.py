from newgrad_notifier.collectors.parsers import extract_jobs_from_html
from newgrad_notifier.collectors.company_pages.collector import CompanyPagesCollector
from newgrad_notifier.config.settings import load_settings
from newgrad_notifier.contracts import SourceType


def test_company_page_parser_skips_anchor_fallback_without_structured_job_data():
    settings = load_settings("config/local_dev.toml")
    html = """
    <html>
      <body>
        <a href="/careers/123">Software Engineer, Fullstack, Early Career San Francisco, California; New York, New York</a>
      </body>
    </html>
    """

    jobs = extract_jobs_from_html(
        html=html,
        base_url="https://example.com/careers",
        source_name="company:test",
        source_type=SourceType.COMPANY_PAGE,
        settings=settings,
        default_company_name="Example",
        allow_anchor_fallback=False,
    )

    assert jobs == []


def test_web_search_parser_can_use_anchor_fallback_for_real_job_links():
    settings = load_settings("config/local_dev.toml")
    html = """
    <html>
      <body>
        <a href="/jobs/123">Software Engineer, New Grad 2027</a>
      </body>
    </html>
    """

    jobs = extract_jobs_from_html(
        html=html,
        base_url="https://example.com/jobs",
        source_name="search:test",
        source_type=SourceType.WEB_SEARCH,
        settings=settings,
        default_company_name="Example",
    )

    assert len(jobs) == 1
    assert jobs[0].metadata["parser"] == "anchor_fallback"


def test_anchor_fallback_splits_embedded_location_from_title():
    settings = load_settings("config/local_dev.toml")
    html = """
    <html>
      <body>
        <a href="https://jobs.ashbyhq.com/notion/123">Software Engineer, Fullstack, Early Career San Francisco, California; New York, New York</a>
      </body>
    </html>
    """

    jobs = extract_jobs_from_html(
        html=html,
        base_url="https://www.notion.so/careers",
        source_name="company:notion",
        source_type=SourceType.COMPANY_PAGE,
        settings=settings,
        default_company_name="Notion",
        allow_anchor_fallback=True,
    )

    assert len(jobs) == 1
    assert jobs[0].title == "Software Engineer, Fullstack, Early Career"
    assert jobs[0].location_text == "San Francisco, California; New York, New York"


def test_company_page_collector_discovers_ats_boards_from_html():
    collector = CompanyPagesCollector()
    boards = collector._discover_ats_boards(
        {"name": "Notion", "priority_tier": 1},
        '<a href="https://jobs.ashbyhq.com/notion">Jobs</a>',
        "https://www.notion.so/careers",
    )

    assert len(boards) == 1
    assert boards[0].platform == "ashby"
    assert boards[0].identifier == "notion"
