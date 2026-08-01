"""Application settings loaded from TOML plus environment variables."""

from __future__ import annotations

import os
import tomllib
from importlib import resources
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from newgrad_notifier.utils.dicts import deep_merge


class SettingsValidationError(ValueError):
    """Raised when the runtime configuration is incomplete or inconsistent."""


class DatabaseSettings(BaseModel):
    backend: str = "sqlite"
    url: str = "sqlite:///./data/newgradnotifier.db"
    sqlite_path: str = "./data/newgradnotifier.db"
    echo: bool = False


class EmailSettings(BaseModel):
    provider: str = "console"
    recipient: str
    sender: str
    resend_api_key: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    outbox_dir: str = "outbox"
    send_empty_digest: bool = False
    failure_alerts_enabled: bool = True


class TrackingSettings(BaseModel):
    enabled: bool = False
    base_url: str = ""
    secret: str = ""
    dashboard_username: str = "donovan"
    dashboard_password: str = ""
    host: str = "127.0.0.1"
    port: int = 8765


class LLMSettings(BaseModel):
    provider: str = "openai"
    model: str = "gpt-5-mini"
    fallback_models: list[str] = Field(default_factory=lambda: ["gpt-4.1-mini"])
    openai_api_key: str = ""
    enabled: bool = True


class ScheduleSettings(BaseModel):
    run_time_local: str = "08:00"
    cron: str = "0 8 * * *"
    timezone: str = "America/New_York"
    immediate_alerts_enabled: bool = True
    immediate_alert_threshold: int = 92


class ThresholdSettings(BaseModel):
    digest_min_fit: int = 65
    top_priority_fit: int = 80
    high_signal_fit: int = 65
    max_digest_jobs: int = 10


class CollectionSettings(BaseModel):
    max_jobs_per_source: int = 500
    max_company_pages_per_run: int = 75
    max_description_fetches_per_run: int = 30
    min_description_characters: int = 160
    max_job_age_days: int = 45
    digest_max_job_age_days: int = 7
    min_domain_interval_seconds: float = 1.0
    request_timeout_seconds: int = 20
    cache_ttl_seconds: int = 60 * 60 * 6
    use_playwright_for_js: bool = False
    retry_attempts: int = 3


class FilterSettings(BaseModel):
    remote_preference: str = "mixed"
    allowed_locations: list[str] = Field(default_factory=lambda: ["United States", "Remote"])
    excluded_locations: list[str] = Field(default_factory=list)
    excluded_companies: list[str] = Field(default_factory=list)
    excluded_job_families: list[str] = Field(default_factory=list)
    priority_companies: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class CandidateProfile(BaseModel):
    graduation_month: str
    graduation_year: int
    headline: str
    internships: list[str] = Field(default_factory=list)
    preferred_roles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    project_signals: list[str] = Field(default_factory=list)


class SourceSettings(BaseModel):
    simplify_enabled: bool = True
    ats_enabled: bool = True
    company_pages_enabled: bool = True
    web_search_enabled: bool = True


class StructuredFeedConfig(BaseModel):
    name: str
    url: str
    format: str = "json"
    job_path: str = ""
    company_key: str = "company"
    title_key: str = "title"
    url_key: str = "url"
    location_key: str = "location"
    posted_at_key: str = "posted_at"
    description_key: str = "description"
    job_id_key: str | None = "job_id"
    closed_key: str = ""


class MarkdownFeedConfig(BaseModel):
    name: str
    url: str
    max_age_days: int = 45


class ATSBoardConfig(BaseModel):
    company_name: str
    platform: str
    identifier: str = ""
    api_url: str = ""
    careers_url: str = ""
    priority_tier: int = 3
    enabled: bool = True


class CompanyCoverageSettings(BaseModel):
    list_path: str = ""


class WebSearchSettings(BaseModel):
    provider: str = "duckduckgo_html"
    max_results_per_query: int = 10
    queries: list[str] = Field(default_factory=list)
    fixture_path: str = ""


class AppSettings(BaseModel):
    app_name: str = "newgrad-notifier"
    environment: str = "development"
    log_level: str = "INFO"
    cache_dir: str = ".cache/newgrad-notifier"
    database: DatabaseSettings
    email: EmailSettings
    tracking: TrackingSettings = Field(default_factory=TrackingSettings)
    llm: LLMSettings
    schedule: ScheduleSettings
    thresholds: ThresholdSettings
    collection: CollectionSettings
    filters: FilterSettings
    candidate_profile: CandidateProfile
    sources: SourceSettings
    company_coverage: CompanyCoverageSettings = Field(default_factory=CompanyCoverageSettings)
    web_search: WebSearchSettings = Field(default_factory=WebSearchSettings)
    structured_feeds: list[StructuredFeedConfig] = Field(default_factory=list)
    markdown_feeds: list[MarkdownFeedConfig] = Field(default_factory=list)
    ats_boards: list[ATSBoardConfig] = Field(default_factory=list)
    runtime_warnings: list[str] = Field(default_factory=list)


def _load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as file_handle:
        return tomllib.load(file_handle)


def _apply_environment_overrides(payload: dict[str, Any]) -> dict[str, Any]:
    env_mapping = {
        "DB_BACKEND": ("database", "backend"),
        "DATABASE_URL": ("database", "url"),
        "SQLITE_PATH": ("database", "sqlite_path"),
        "OPENAI_API_KEY": ("llm", "openai_api_key"),
        "OPENAI_ENABLED": ("llm", "enabled"),
        "OPENAI_MODEL": ("llm", "model"),
        "OPENAI_FALLBACK_MODELS": ("llm", "fallback_models"),
        "RESEND_API_KEY": ("email", "resend_api_key"),
        "SMTP_TLS": ("email", "smtp_use_tls"),
        "SMTP_HOST": ("email", "smtp_host"),
        "SMTP_PORT": ("email", "smtp_port"),
        "SMTP_USERNAME": ("email", "smtp_username"),
        "SMTP_PASSWORD": ("email", "smtp_password"),
        "SMTP_USE_TLS": ("email", "smtp_use_tls"),
        "EMAIL_RECIPIENT": ("email", "recipient"),
        "EMAIL_TO": ("email", "recipient"),
        "EMAIL_SENDER": ("email", "sender"),
        "EMAIL_FROM": ("email", "sender"),
        "EMAIL_PROVIDER": ("email", "provider"),
        "EMAIL_MODE": ("email", "provider"),
        "SEND_EMPTY_DIGEST": ("email", "send_empty_digest"),
        "FAILURE_ALERTS_ENABLED": ("email", "failure_alerts_enabled"),
        "TRACKING_ENABLED": ("tracking", "enabled"),
        "TRACKING_BASE_URL": ("tracking", "base_url"),
        "TRACKING_SECRET": ("tracking", "secret"),
        "TRACKING_DASHBOARD_USERNAME": ("tracking", "dashboard_username"),
        "TRACKING_DASHBOARD_PASSWORD": ("tracking", "dashboard_password"),
        "TRACKING_HOST": ("tracking", "host"),
        "TRACKING_PORT": ("tracking", "port"),
        "IMMEDIATE_ALERTS_ENABLED": ("schedule", "immediate_alerts_enabled"),
        "IMMEDIATE_ALERT_THRESHOLD": ("schedule", "immediate_alert_threshold"),
        "RUN_TIME_LOCAL": ("schedule", "run_time_local"),
        "TIME_ZONE": ("schedule", "timezone"),
    }
    merged = dict(payload)
    for env_key, path_parts in env_mapping.items():
        value = os.getenv(env_key)
        if value is None or value == "":
            continue
        cursor: dict[str, Any] = merged
        for part in path_parts[:-1]:
            cursor = cursor.setdefault(part, {})
        if path_parts[-1] in {"smtp_port", "immediate_alert_threshold", "port"}:
            cursor[path_parts[-1]] = int(value)
        elif path_parts[-1] in {
            "smtp_use_tls",
            "immediate_alerts_enabled",
            "enabled",
            "send_empty_digest",
            "failure_alerts_enabled",
        }:
            cursor[path_parts[-1]] = value.lower() in {"1", "true", "yes"}
        elif path_parts[-1] == "fallback_models":
            cursor[path_parts[-1]] = [item.strip() for item in value.split(",") if item.strip()]
        else:
            cursor[path_parts[-1]] = value
    return merged


def _derive_database_url(settings: AppSettings) -> None:
    sqlite_path_override = os.getenv("SQLITE_PATH")
    database_url = settings.database.url.strip()
    if database_url.startswith(("postgresql://", "postgresql+psycopg://", "postgres://")):
        settings.database.backend = "postgres"
        return

    if settings.database.backend == "postgres":
        raise SettingsValidationError(
            "PostgreSQL is selected but DATABASE_URL is missing or invalid. "
            "Set DATABASE_URL to a postgres:// or postgresql:// connection string."
        )

    if settings.database.backend != "sqlite":
        raise SettingsValidationError("DB_BACKEND must be either 'sqlite' or 'postgres'.")

    sqlite_path = (sqlite_path_override or settings.database.sqlite_path).strip() or "./data/newgradnotifier.db"
    settings.database.sqlite_path = sqlite_path
    settings.database.url = f"sqlite:///{sqlite_path}"


def _derive_schedule(settings: AppSettings) -> None:
    try:
        hour_text, minute_text = settings.schedule.run_time_local.split(":", maxsplit=1)
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError as exc:
        raise SettingsValidationError("RUN_TIME_LOCAL must use HH:MM 24-hour format, for example 08:00.") from exc
    if hour not in range(24) or minute not in range(60):
        raise SettingsValidationError("RUN_TIME_LOCAL must use a valid 24-hour time.")
    settings.schedule.cron = f"{minute} {hour} * * *"


def _derive_tracking(settings: AppSettings) -> None:
    if os.getenv("PORT"):
        settings.tracking.port = int(os.environ["PORT"])
    if os.getenv("RENDER"):
        settings.tracking.host = "0.0.0.0"
    if settings.tracking.enabled and not settings.tracking.base_url:
        settings.tracking.base_url = os.getenv("RENDER_EXTERNAL_HOSTNAME", "")


def _validate_required_settings(settings: AppSettings) -> None:
    missing: list[str] = []
    if settings.email.provider == "resend":
        if not settings.email.recipient:
            missing.append("EMAIL_RECIPIENT")
        if not settings.email.sender:
            missing.append("EMAIL_SENDER")
        if not settings.email.resend_api_key:
            missing.append("RESEND_API_KEY")
    elif settings.email.provider == "smtp":
        if not settings.email.recipient:
            missing.append("EMAIL_RECIPIENT")
        if not settings.email.sender:
            missing.append("EMAIL_SENDER")
        if not settings.email.smtp_host:
            missing.append("SMTP_HOST")
        if not settings.email.smtp_port:
            missing.append("SMTP_PORT")
        if not settings.email.smtp_username:
            missing.append("SMTP_USERNAME")
        if not settings.email.smtp_password:
            missing.append("SMTP_PASSWORD")
    if missing:
        missing_csv = ", ".join(missing)
        if settings.email.provider == "resend":
            raise SettingsValidationError(
                f"Missing required email settings for Resend delivery: {missing_csv}. "
                "Set RESEND_API_KEY and use a valid from address. For sending beyond your own address, "
                "verify a custom domain in Resend."
            )
        raise SettingsValidationError(
            f"Missing required email settings for SMTP delivery: {missing_csv}. "
            "For Gmail, use a Google App Password in SMTP_PASSWORD."
        )

    if settings.llm.provider == "openai" and settings.llm.enabled and not settings.llm.openai_api_key:
        settings.runtime_warnings.append(
            "OPENAI_API_KEY is missing. OpenAI ranking is disabled and the pipeline will use heuristic scoring only."
        )
        settings.llm.enabled = False

    if settings.tracking.enabled and (not settings.tracking.base_url or not settings.tracking.secret):
        raise SettingsValidationError(
            "Tracking is enabled but TRACKING_BASE_URL or TRACKING_SECRET is missing. "
            "Set both values before enabling email tracking actions."
        )


def load_settings(config_path: str | Path | None = None) -> AppSettings:
    """Load packaged defaults, merge optional overrides, and apply env secrets."""

    default_resource = resources.files("newgrad_notifier.config").joinpath("default_settings.toml")
    with resources.as_file(default_resource) as default_path:
        base_settings = _load_toml(default_path)
    if config_path is not None:
        override_settings = _load_toml(Path(config_path))
        base_settings = deep_merge(base_settings, override_settings)
    merged = _apply_environment_overrides(base_settings)
    settings = AppSettings.model_validate(merged)
    _derive_database_url(settings)
    _derive_schedule(settings)
    _derive_tracking(settings)
    _validate_required_settings(settings)
    return settings
