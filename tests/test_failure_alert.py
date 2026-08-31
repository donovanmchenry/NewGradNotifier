from __future__ import annotations

import importlib.util
import json
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


def test_failure_alert_sends_resend_compatible_request(monkeypatch):
    module = _load_module()
    captured = {}

    class Response:
        status = 202

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setenv("FAILURE_ALERTS_ENABLED", "true")
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("EMAIL_RECIPIENT", "donovan@example.com")
    monkeypatch.setenv("EMAIL_SENDER", "NewGrad Notifier <onboarding@resend.dev>")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setattr(module, "urlopen", fake_urlopen)

    assert module.main() == 0
    request = captured["request"]
    assert request.get_header("User-agent") == "newgrad-notifier"
    assert request.get_header("Accept") == "application/json"
    assert json.loads(request.data)["to"] == ["donovan@example.com"]
    assert captured["timeout"] == 20
