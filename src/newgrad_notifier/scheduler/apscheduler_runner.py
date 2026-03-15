"""APScheduler bootstrap for long-running local or server execution."""

from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from newgrad_notifier.config.settings import load_settings
from newgrad_notifier.scheduler.jobs import run_daily_job


def run_scheduler(config_path: str | None = None) -> None:
    """Run a blocking scheduler using the configured cron expression."""

    settings = load_settings(config_path)
    scheduler = BlockingScheduler(timezone=settings.schedule.timezone)
    scheduler.add_job(
        run_daily_job,
        CronTrigger.from_crontab(settings.schedule.cron, timezone=settings.schedule.timezone),
        kwargs={"config_path": config_path},
    )
    scheduler.start()

