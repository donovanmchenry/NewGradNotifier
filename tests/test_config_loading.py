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


def test_config_loading_supports_openai_fallback_models(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "resend")
    monkeypatch.setenv("EMAIL_RECIPIENT", "dzmchenry@gmail.com")
    monkeypatch.setenv("EMAIL_SENDER", "NewGrad Notifier <onboarding@resend.dev>")
    monkeypatch.setenv("RESEND_API_KEY", "resend-test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5-mini")
    monkeypatch.setenv("OPENAI_FALLBACK_MODELS", "gpt-4.1-mini,gpt-4o-mini")

    settings = load_settings("config/production.toml")

    assert settings.llm.model == "gpt-5-mini"
    assert settings.llm.fallback_models == ["gpt-4.1-mini", "gpt-4o-mini"]


def test_openai_can_be_explicitly_disabled_even_when_a_key_exists(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "console")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    monkeypatch.setenv("OPENAI_ENABLED", "false")

    settings = load_settings("config/production.toml")

    assert settings.llm.enabled is False


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


def test_tracking_requires_a_public_url_and_secret(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "console")
    monkeypatch.setenv("TRACKING_ENABLED", "true")
    monkeypatch.delenv("TRACKING_BASE_URL", raising=False)
    monkeypatch.delenv("TRACKING_SECRET", raising=False)

    with pytest.raises(SettingsValidationError):
        load_settings("config/production.toml")


def test_postgres_database_url_is_selected(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "console")
    monkeypatch.setenv("DB_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@example.com/jobs")

    settings = load_settings("config/production.toml")

    assert settings.database.backend == "postgres"
    assert settings.database.url.startswith("postgresql://")


def test_postgres_backend_rejects_missing_database_url(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "console")
    monkeypatch.setenv("DB_BACKEND", "postgres")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(SettingsValidationError, match="DATABASE_URL"):
        load_settings("config/production.toml")
