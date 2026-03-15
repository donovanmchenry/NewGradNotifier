"""Seed reference tables for companies and source configuration."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from newgrad_notifier.config.company_loader import load_company_list
from newgrad_notifier.config.settings import AppSettings
from newgrad_notifier.db.models import Company, SourceConfig


def seed_reference_data(session: Session, settings: AppSettings) -> None:
    """Upsert company and source configuration reference data."""

    company_records = load_company_list(settings.company_coverage.list_path or None)
    for item in company_records:
        existing = session.scalar(select(Company).where(Company.slug == item["slug"]))
        if existing is None:
            existing = Company(slug=item["slug"], name=item["name"])
        existing.homepage = item.get("homepage")
        existing.careers_url = item.get("careers_url")
        existing.priority_tier = item.get("priority_tier", 3)
        existing.ats_platform = item.get("ats_platform")
        existing.ats_identifier = item.get("ats_identifier")
        existing.enabled = item.get("enabled", True)
        existing.metadata_json = {
            "seeded": True,
        }
        session.add(existing)

    source_payloads = {
        "simplify": {
            "enabled": settings.sources.simplify_enabled,
            "source_type": "structured",
            "config_json": {"feeds": [feed.model_dump() for feed in settings.structured_feeds]},
        },
        "ats": {
            "enabled": settings.sources.ats_enabled,
            "source_type": "ats",
            "config_json": {"boards": [board.model_dump() for board in settings.ats_boards]},
        },
        "company_pages": {
            "enabled": settings.sources.company_pages_enabled,
            "source_type": "company_page",
            "config_json": {"company_list_path": settings.company_coverage.list_path},
        },
        "web_search": {
            "enabled": settings.sources.web_search_enabled,
            "source_type": "web_search",
            "config_json": settings.web_search.model_dump(),
        },
    }
    for source_name, payload in source_payloads.items():
        existing = session.scalar(select(SourceConfig).where(SourceConfig.source_name == source_name))
        if existing is None:
            existing = SourceConfig(source_name=source_name, source_type=payload["source_type"])
        existing.source_type = payload["source_type"]
        existing.enabled = payload["enabled"]
        existing.config_json = payload["config_json"]
        session.add(existing)

    session.commit()
