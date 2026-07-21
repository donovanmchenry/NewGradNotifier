"""Run once per local day despite delayed or duplicate GitHub cron triggers."""

from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def _completed_rows_sqlite(sqlite_path: Path) -> list[tuple[str]]:
    if not sqlite_path.exists():
        return []
    with sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True) as connection:
        table_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='daily_runs'"
        ).fetchone()
        if not table_exists:
            return []
        return connection.execute(
            "SELECT started_at FROM daily_runs WHERE status = 'completed' ORDER BY started_at DESC LIMIT 5"
        ).fetchall()


def _completed_rows_postgres(database_url: str) -> list[tuple[str]]:
    from sqlalchemy import create_engine, text

    if database_url.startswith("postgres://"):
        database_url = "postgresql+psycopg://" + database_url.removeprefix("postgres://")
    elif database_url.startswith("postgresql://"):
        database_url = "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
    engine = create_engine(database_url)
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT started_at FROM daily_runs WHERE status = 'completed' ORDER BY started_at DESC LIMIT 5")
        )
        return [(row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0]),) for row in rows]


def main() -> int:
    timezone_name = os.getenv("TIME_ZONE", "America/New_York")
    run_time_local = os.getenv("RUN_TIME_LOCAL", "08:00")
    start_date_text = os.getenv("SCHEDULE_START_DATE", "")
    target_hour, target_minute = [int(part) for part in run_time_local.split(":", maxsplit=1)]
    now = datetime.now(ZoneInfo(timezone_name))
    if start_date_text:
        start_date = date.fromisoformat(start_date_text)
        if now.date() < start_date:
            print(f"Scheduled automation starts on {start_date.isoformat()}; skipping this trigger.")
            return 1
    print(f"Current local time in {timezone_name}: {now.isoformat()}")
    current_minutes = now.hour * 60 + now.minute
    target_minutes = target_hour * 60 + target_minute
    if current_minutes < target_minutes:
        print("The first UTC trigger arrived before the configured local run time; waiting for the next trigger.")
        return 1

    try:
        if os.getenv("DB_BACKEND", "sqlite").lower() == "postgres":
            database_url = os.getenv("DATABASE_URL", "")
            if not database_url:
                print("PostgreSQL is selected but DATABASE_URL is missing; allowing the pipeline to expose the error.")
                return 0
            rows = _completed_rows_postgres(database_url)
        else:
            rows = _completed_rows_sqlite(Path(os.getenv("SQLITE_PATH", "./data/newgradnotifier.db")))
    except Exception as exc:
        print(f"Unable to inspect run history ({exc}); allowing the pipeline to run.")
        return 0

    if not rows:
        print("No persisted run history exists; the pipeline should run.")
        return 0

    for (started_at_text,) in rows:
        started_at = datetime.fromisoformat(started_at_text)
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=ZoneInfo("UTC"))
        if started_at.astimezone(ZoneInfo(timezone_name)).date() == now.date():
            print("A completed run already exists for this local date; skipping the duplicate trigger.")
            return 1

    print("No completed run exists for this local date; the pipeline should run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
