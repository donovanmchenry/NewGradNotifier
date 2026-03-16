from __future__ import annotations

import importlib.util
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
