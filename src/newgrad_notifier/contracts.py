"""Typed contracts shared across collectors, ranking, persistence, and notifications."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


class SourceType(StrEnum):
    """Supported source families."""

    STRUCTURED = "structured"
    ATS = "ats"
    COMPANY_PAGE = "company_page"
    WEB_SEARCH = "web_search"


class Recommendation(StrEnum):
    """Ranking recommendation states."""

    APPLY_NOW = "apply_now"
    APPLY_IF_INTERESTED = "apply_if_interested"
    LOW_PRIORITY = "low_priority"
    SKIP = "skip"


class JobLifecycleState(StrEnum):
    """Lifecycle states tracked by the pipeline."""

    NEW = "new"
    SEEN = "seen"
    REOPENED = "reopened"
    APPLIED = "applied"
    IGNORED = "ignored"


class RunStatus(StrEnum):
    """Execution status for a daily pipeline run."""

    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


class CollectedJob(BaseModel):
    """Raw job payload returned from a collector before normalization."""

    source_name: str
    source_type: SourceType
    source_url: str
    apply_url: str
    company_name: str
    title: str
    external_job_id: str | None = None
    location_text: str | None = None
    posted_at: datetime | None = None
    description_text: str | None = None
    job_family: str | None = None
    employment_type: str | None = None
    search_query: str | None = None
    fetched_at: datetime = Field(default_factory=utc_now)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedJob(BaseModel):
    """Normalized job record ready for dedupe and storage."""

    canonical_key: str
    source_name: str
    source_type: SourceType
    source_url: str
    apply_url: str
    company_name: str
    title: str
    title_normalized: str
    external_job_id: str | None = None
    job_family: str | None = None
    location_text: str | None = None
    location_normalized: str | None = None
    is_remote: bool = False
    posted_at: datetime | None = None
    description_text: str = ""
    description_hash: str
    first_seen_at: datetime = Field(default_factory=utc_now)
    last_seen_at: datetime = Field(default_factory=utc_now)
    content_hash: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RankingResult(BaseModel):
    """Ranking output stored for each normalized job."""

    fit_score: int = Field(ge=0, le=100)
    difficulty_score: int = Field(ge=0, le=100)
    recommendation: Recommendation
    fit_summary: str
    difficulty_summary: str
    top_matching_skills: list[str] = Field(default_factory=list)
    missing_or_weaker_skills: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    scorer: str = "heuristic"
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)


class RankedJob(BaseModel):
    """Composite object used by digest generation and persistence."""

    normalized_job: NormalizedJob
    ranking: RankingResult
    lifecycle_state: JobLifecycleState = JobLifecycleState.NEW


class SearchResult(BaseModel):
    """Generic web search result."""

    title: str
    url: HttpUrl | str
    snippet: str | None = None
    published_at: datetime | None = None
    source_name: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class PipelineError(BaseModel):
    """Structured error for collection and notification reporting."""

    source_name: str
    stage: str
    message: str
    detail: str | None = None


class DigestStats(BaseModel):
    """Aggregate counts used in emails and run metadata."""

    total_collected: int = 0
    total_normalized: int = 0
    total_new: int = 0
    total_reopened: int = 0
    total_high_signal: int = 0
    total_errors: int = 0
    source_counts: dict[str, int] = Field(default_factory=dict)

