from pathlib import Path

from newgrad_notifier.collectors.base import CollectorContext
from newgrad_notifier.collectors.simplify import SimplifyCollector
from newgrad_notifier.config.settings import load_settings
from newgrad_notifier.utils.http import CachedHttpClient


def test_simplify_collector_filters_relevant_jobs(tmp_path):
    settings = load_settings("config/local_dev.toml")
    collector = SimplifyCollector(settings.structured_feeds)
    http_client = CachedHttpClient(cache_dir=tmp_path / "cache")
    context = CollectorContext(settings=settings, http_client=http_client, logger=__import__("logging").getLogger(__name__))

    jobs = collector.collect(context)

    titles = {job.title for job in jobs}
    assert "Software Engineer, New Grad 2027" in titles
    assert "Frontend Software Engineer I" in titles
    assert "Site Reliability Engineer, New Grad" not in titles
    http_client.close()

