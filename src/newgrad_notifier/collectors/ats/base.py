"""Base helpers for ATS collectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from newgrad_notifier.collectors.base import CollectorContext
from newgrad_notifier.collectors.relevance import is_relevant_role, location_allowed
from newgrad_notifier.config.settings import ATSBoardConfig
from newgrad_notifier.contracts import CollectedJob, SourceType


class ATSBoardCollector(ABC):
    """Platform-specific ATS collector contract."""

    platform: str

    @abstractmethod
    def collect_board(self, board: ATSBoardConfig, context: CollectorContext) -> list[CollectedJob]:
        """Collect jobs from a specific ATS board."""

    def build_job(
        self,
        *,
        board: ATSBoardConfig,
        source_url: str,
        apply_url: str,
        company_name: str,
        title: str,
        external_job_id: str | None = None,
        location_text: str | None = None,
        posted_at: str | None = None,
        description_text: str | None = None,
        employment_type: str | None = None,
        metadata: dict[str, Any] | None = None,
        context: CollectorContext,
    ) -> CollectedJob | None:
        """Build a validated job only when it passes the relevance filters."""

        description = description_text or ""
        if not is_relevant_role(title, description, context.settings):
            return None
        if not location_allowed(location_text, context.settings):
            return None
        return CollectedJob(
            source_name=f"{board.platform}:{company_name}",
            source_type=SourceType.ATS,
            source_url=source_url,
            apply_url=apply_url,
            company_name=company_name,
            title=title,
            external_job_id=external_job_id,
            location_text=location_text,
            posted_at=posted_at,
            description_text=description,
            employment_type=employment_type,
            metadata=metadata or {},
        )

