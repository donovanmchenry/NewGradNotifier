import logging

from newgrad_notifier.collectors.ats.service import ATSCollectorService
from newgrad_notifier.collectors.base import CollectorContext
from newgrad_notifier.config.settings import load_settings
from newgrad_notifier.utils.http import CachedHttpClient


def test_ats_collectors_cover_major_platforms(tmp_path):
    settings = load_settings("config/local_dev.toml")
    collector = ATSCollectorService(settings.ats_boards)
    http_client = CachedHttpClient(cache_dir=tmp_path / "cache")
    context = CollectorContext(settings=settings, http_client=http_client, logger=logging.getLogger(__name__))

    jobs = collector.collect(context)

    companies = {job.company_name for job in jobs}
    assert {"Figma", "Plaid", "OpenAI", "Tesla", "Hewlett Packard Enterprise"} <= companies
    assert all("Analyst" not in job.title for job in jobs)
    assert len(collector.source_health) == len(settings.ats_boards)
    assert all(item["status"] == "healthy" for item in collector.source_health.values())
    assert all(item["total_available"] >= item["relevant_jobs"] for item in collector.source_health.values())
    http_client.close()
