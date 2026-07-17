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
    ats_collectors = [collector for collector in collectors if collector.name == "ats"]

    assert ats_collectors
    assert len(ats_collectors[0].boards) >= 40
    groq = next(board for board in ats_collectors[0].boards if board.company_name == "Groq")
    assert groq.platform == "ashby"
