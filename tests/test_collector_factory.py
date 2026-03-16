from newgrad_notifier.collectors.factory import build_collectors
from newgrad_notifier.config.settings import load_settings


def test_factory_uses_curated_ats_boards_when_no_enabled_boards_are_configured(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "resend")
    monkeypatch.setenv("EMAIL_RECIPIENT", "dzmchenry@gmail.com")
    monkeypatch.setenv("EMAIL_SENDER", "NewGrad Notifier <onboarding@resend.dev>")
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    settings = load_settings("config/production.toml")

    collectors = build_collectors(settings)

    assert collectors
    assert collectors[0].name == "ats"
