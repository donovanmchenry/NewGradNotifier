from __future__ import annotations

import importlib.util
import sqlite3
from datetime import datetime
from pathlib import Path


def _load_schedule_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "should_run_schedule.py"
    spec = importlib.util.spec_from_file_location("should_run_schedule", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_schedule_gate_respects_start_date(monkeypatch):
    module = _load_schedule_module()
    monkeypatch.setenv("TIME_ZONE", "America/New_York")
    monkeypatch.setenv("RUN_TIME_LOCAL", "08:00")
    monkeypatch.setenv("SCHEDULE_START_DATE", "2099-07-01")

    assert module.main() == 1


def test_schedule_gate_allows_delayed_trigger_when_today_has_not_run(monkeypatch, tmp_path):
    module = _load_schedule_module()

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 7, 17, 9, 51, tzinfo=tz)

    module.datetime = FixedDateTime
    monkeypatch.setenv("TIME_ZONE", "America/New_York")
    monkeypatch.setenv("RUN_TIME_LOCAL", "08:00")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "missing.db"))
    monkeypatch.delenv("SCHEDULE_START_DATE", raising=False)

    assert module.main() == 0


def test_schedule_gate_skips_when_today_already_completed(monkeypatch, tmp_path):
    module = _load_schedule_module()

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 7, 17, 10, 0, tzinfo=tz)

    database_path = tmp_path / "state.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE daily_runs (started_at TEXT, status TEXT)")
        connection.execute("INSERT INTO daily_runs VALUES (?, ?)", ("2026-07-17T12:30:00+00:00", "completed"))

    module.datetime = FixedDateTime
    monkeypatch.setenv("TIME_ZONE", "America/New_York")
    monkeypatch.setenv("RUN_TIME_LOCAL", "08:00")
    monkeypatch.setenv("SQLITE_PATH", str(database_path))
    monkeypatch.delenv("SCHEDULE_START_DATE", raising=False)

    assert module.main() == 1
