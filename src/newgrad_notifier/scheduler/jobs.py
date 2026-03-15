"""Scheduler entrypoints."""

from __future__ import annotations

from newgrad_notifier.pipeline import run_pipeline_once


def run_daily_job(config_path: str | None = None) -> None:
    """Run the pipeline one time."""

    run_pipeline_once(config_path=config_path)

