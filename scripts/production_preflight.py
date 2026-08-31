"""Validate production configuration and restored state without making network calls."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from newgrad_notifier.collectors.factory import build_collectors
from newgrad_notifier.config.settings import load_settings
from newgrad_notifier.notifications.sender import build_email_sender


def main() -> int:
    config_path = os.getenv("NEWGRAD_CONFIG_PATH", "config/production.toml")
    try:
        settings = load_settings(config_path)
        collectors = build_collectors(settings)
        build_email_sender(settings.email)
    except Exception as exc:
        print(f"Production configuration is invalid: {exc}")
        return 1

    if not collectors:
        print("Production configuration did not enable any collectors.")
        return 1

    if settings.database.backend == "sqlite":
        database_path = Path(settings.database.sqlite_path)
        if not database_path.exists():
            print(f"Restored SQLite database is missing: {database_path}")
            return 1
        try:
            with sqlite3.connect(f"file:{database_path}?mode=ro", uri=True) as connection:
                quick_check = connection.execute("PRAGMA quick_check").fetchone()
                has_run_history = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='daily_runs'"
                ).fetchone()
        except sqlite3.DatabaseError as exc:
            print(f"Restored SQLite database is unreadable: {exc}")
            return 1
        if quick_check != ("ok",):
            print(f"Restored SQLite database failed validation: {quick_check!r}")
            return 1
        if not has_run_history:
            print("Restored SQLite database does not contain run history.")
            return 1

    print(f"Production preflight passed with {len(collectors)} configured collector groups.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
