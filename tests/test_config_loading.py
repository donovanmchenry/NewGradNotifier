import os

import pytest

from newgrad_notifier.config.settings import SettingsValidationError, load_settings


def test_config_loading_uses_production_env_names(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")
    monkeypatch.setenv("EMAIL_RECIPIENT", "dzmchenry@gmail.com")
    monkeypatch.setenv("EMAIL_SENDER", "dzmchenry@gmail.com")
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "dzmchenry@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setenv("SMTP_TLS", "true")
    monkeypatch.setenv("DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_PATH", "./data/test-config.db")
    monkeypatch.setenv("RUN_TIME_LOCAL", "08:00")
    monkeypatch.setenv("TIME_ZONE", "America/New_York")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    settings = load_settings("config/production.toml")

    assert settings.email.provider == "smtp"
    assert settings.email.smtp_password == "app-password"
    assert settings.database.sqlite_path == "./data/test-config.db"
    assert settings.database.url == "sqlite:///./data/test-config.db"
    assert settings.schedule.cron == "0 8 * * *"
    assert settings.llm.enabled is False
    assert settings.runtime_warnings


def test_smtp_validation_fails_without_password(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")
    monkeypatch.setenv("EMAIL_RECIPIENT", "dzmchenry@gmail.com")
    monkeypatch.setenv("EMAIL_SENDER", "dzmchenry@gmail.com")
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "dzmchenry@gmail.com")
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)

    with pytest.raises(SettingsValidationError):
        load_settings("config/production.toml")

