import logging

from newgrad_notifier.collectors.base import CollectorContext
from newgrad_notifier.collectors.github_markdown import GitHubMarkdownCollector
from newgrad_notifier.config.settings import MarkdownFeedConfig, load_settings
from newgrad_notifier.utils.http import CachedHttpClient


def test_github_markdown_collector_parses_current_table_shape(tmp_path):
    markdown_path = tmp_path / "jobs.md"
    markdown_path.write_text(
        """
| Company | Position | Location | Posting | Age |
|---|---|---|---|---|
| <a href="https://example.com"><strong>Example</strong></a> | Full-Stack Software Engineer - New Grad 2027 | Remote - USA | <a href="https://example.com/jobs/1">Apply</a> | 2d |
| <a href="https://example.com"><strong>Old</strong></a> | Software Engineer - New Grad | Seattle, WA | <a href="https://example.com/jobs/2">Apply</a> | 90d |
""",
        encoding="utf-8",
    )
    settings = load_settings("config/local_dev.toml")
    client = CachedHttpClient(cache_dir=tmp_path / "cache")
    collector = GitHubMarkdownCollector(
        MarkdownFeedConfig(name="new_grad_2027", url=str(markdown_path), max_age_days=45)
    )

    jobs = collector.collect(CollectorContext(settings=settings, http_client=client, logger=logging.getLogger(__name__)))

    assert len(jobs) == 1
    assert jobs[0].company_name == "Example"
    assert jobs[0].apply_url == "https://example.com/jobs/1"
    assert jobs[0].location_text == "Remote - USA"
    client.close()
