from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "production_preflight.py"
    spec = importlib.util.spec_from_file_location("production_preflight", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preflight_accepts_valid_restored_state(monkeypatch, tmp_path):
    module = _load_module()
    database_path = tmp_path / "state.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE daily_runs (id INTEGER PRIMARY KEY)")

    monkeypatch.setenv("NEWGRAD_CONFIG_PATH", "config/local_dev.toml")
    monkeypatch.setenv("EMAIL_PROVIDER", "console")
    monkeypatch.setenv("SQLITE_PATH", str(database_path))

    assert module.main() == 0


def test_preflight_rejects_missing_restored_state(monkeypatch, tmp_path):
    module = _load_module()
    monkeypatch.setenv("NEWGRAD_CONFIG_PATH", "config/local_dev.toml")
    monkeypatch.setenv("EMAIL_PROVIDER", "console")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "missing.db"))

    assert module.main() == 1
