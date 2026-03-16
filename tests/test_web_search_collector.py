from newgrad_notifier.collectors.base import CollectorContext
from newgrad_notifier.collectors.web_search.collector import WebSearchCollector
from newgrad_notifier.config.settings import load_settings
from newgrad_notifier.contracts import SearchResult
from newgrad_notifier.utils.http import CachedHttpClient


def test_web_search_collector_builds_direct_job_from_ats_result(tmp_path):
    settings = load_settings("config/local_dev.toml")
    collector = WebSearchCollector(provider_name="fixture", queries=[], fixture_path="examples/local_sources/search_results.json")
    context = CollectorContext(settings=settings, http_client=CachedHttpClient(cache_dir=tmp_path / "cache"), logger=__import__("logging").getLogger(__name__))

    result = SearchResult(
        title="Software Engineer, Fullstack, Early Career San Francisco, California; New York, New York",
        url="https://jobs.ashbyhq.com/notion/f7399542-9122-481a-bf64-43bf8093748b",
        snippet="Early career fullstack product engineer role.",
        source_name="duckduckgo_html",
    )

    job = collector._job_from_search_result(result, "early career software engineer", context)

    assert job is not None
    assert job.company_name == "Notion"
    assert job.title == "Software Engineer, Fullstack, Early Career"
    assert job.source_type.value == "web_search"
    context.http_client.close()
