from datetime import UTC, datetime, timedelta
from pathlib import Path

from newgrad_notifier.collectors.base import CollectorContext
from newgrad_notifier.collectors.simplify import SimplifyCollector, _is_recent
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


def test_is_recent_supports_unix_timestamps():
    recent = (datetime.now(UTC) - timedelta(days=2)).timestamp()
    stale = (datetime.now(UTC) - timedelta(days=60)).timestamp()

    assert _is_recent(recent, max_age_days=45)
    assert not _is_recent(stale, max_age_days=45)
