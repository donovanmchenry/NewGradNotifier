from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "send_failure_alert.py"
    spec = importlib.util.spec_from_file_location("send_failure_alert", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_failure_alert_can_be_disabled_without_network(monkeypatch):
    module = _load_module()
    monkeypatch.setenv("FAILURE_ALERTS_ENABLED", "false")

    assert module.main() == 0
