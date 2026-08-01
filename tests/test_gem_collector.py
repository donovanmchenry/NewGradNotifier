from __future__ import annotations

import logging
from pathlib import Path

from newgrad_notifier.collectors.ats.gem import GemCollector
from newgrad_notifier.collectors.base import CollectorContext
from newgrad_notifier.config.settings import ATSBoardConfig, load_settings
from newgrad_notifier.utils.http import CachedHttpClient


def test_collects_public_gem_board_shape(tmp_path: Path, monkeypatch) -> None:
    payload = {
        "data": {
            "oatsExternalJobPostings": {
                "jobPostings": [
                    {
                        "id": "encoded-id",
                        "extId": "public-job-id",
                        "title": "Software Engineer, New Grad",
                        "locations": [
                            {
                                "name": "United States",
                                "city": "",
                                "isoCountry": None,
                                "isRemote": False,
                            }
                        ],
                        "job": {
                            "locationType": "REMOTE",
                            "employmentType": "FULL_TIME",
                        },
                    }
                ]
            }
        }
    }
    settings = load_settings("config/local_dev.toml")
    context = CollectorContext(
        settings=settings,
        http_client=CachedHttpClient(cache_dir=tmp_path / "cache"),
        logger=logging.getLogger(__name__),
    )
    monkeypatch.setattr(context.http_client, "get_json", lambda *args, **kwargs: payload)
    board = ATSBoardConfig(
        company_name="Example",
        platform="gem",
        identifier="example",
    )

    collector = GemCollector()
    jobs = collector.collect_board(board, context)

    assert collector.last_total_available == 1
    assert len(jobs) == 1
    assert jobs[0].source_name == "gem:Example"
    assert jobs[0].location_text == "Remote, United States"
    assert jobs[0].apply_url == "https://jobs.gem.com/example/public-job-id"
