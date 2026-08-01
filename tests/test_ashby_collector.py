from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from newgrad_notifier.collectors.ats.ashby import AshbyCollector
from newgrad_notifier.collectors.base import CollectorContext
from newgrad_notifier.config.settings import ATSBoardConfig, load_settings
from newgrad_notifier.utils.http import CachedHttpClient


def _context(tmp_path: Path) -> CollectorContext:
    return CollectorContext(
        settings=load_settings("config/local_dev.toml"),
        http_client=CachedHttpClient(cache_dir=tmp_path / "cache"),
        logger=logging.getLogger(__name__),
    )


def test_collects_current_public_posting_api_shape(tmp_path: Path) -> None:
    payload_path = tmp_path / "ashby.json"
    payload_path.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "id": "3ef57e26-3f4b-44a1-865a-bcab8eae31b3",
                        "title": "Software Engineer - New Grad 2027",
                        "location": "Remote, United States",
                        "publishedAt": "2026-08-01T12:00:00Z",
                        "jobUrl": "https://jobs.ashbyhq.com/example/3ef57e26-3f4b-44a1-865a-bcab8eae31b3",
                        "applyUrl": "https://jobs.ashbyhq.com/example/3ef57e26-3f4b-44a1-865a-bcab8eae31b3/application",
                        "descriptionHtml": "<p>Build reliable software.</p>",
                        "employmentType": "FullTime",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    board = ATSBoardConfig(
        company_name="Example",
        platform="ashby",
        identifier="example",
        api_url=str(payload_path),
    )

    collector = AshbyCollector()
    jobs = collector.collect_board(board, _context(tmp_path))

    assert collector.last_total_available == 1
    assert len(jobs) == 1
    assert jobs[0].title == "Software Engineer - New Grad 2027"
    assert jobs[0].location_text == "Remote, United States"
    assert jobs[0].posted_at.isoformat() == "2026-08-01T12:00:00+00:00"
    assert jobs[0].apply_url.endswith("/application")


def test_raises_when_ashby_returns_api_errors(tmp_path: Path) -> None:
    payload_path = tmp_path / "ashby-error.json"
    payload_path.write_text(
        json.dumps({"errors": [{"message": "Invalid board"}]}),
        encoding="utf-8",
    )
    board = ATSBoardConfig(
        company_name="Example",
        platform="ashby",
        identifier="example",
        api_url=str(payload_path),
    )

    with pytest.raises(ValueError, match="Ashby returned an error"):
        AshbyCollector().collect_board(board, _context(tmp_path))
