"""SQLAlchemy models for jobs, runs, scoring, and notifications."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for the application."""


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    homepage: Mapped[str | None] = mapped_column(String(500))
    careers_url: Mapped[str | None] = mapped_column(String(500))
    priority_tier: Mapped[int] = mapped_column(Integer, default=3)
    ats_platform: Mapped[str | None] = mapped_column(String(50))
    ats_identifier: Mapped[str | None] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    normalized_jobs: Mapped[list["NormalizedJobRecord"]] = relationship(back_populates="company")


class SourceConfig(Base):
    __tablename__ = "source_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    source_type: Mapped[str] = mapped_column(String(50))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class DailyRun(Base):
    __tablename__ = "daily_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(50), index=True)
    stats_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    errors_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    scoring_results: Mapped[list["ScoringResultRecord"]] = relationship(back_populates="run")
    email_digests: Mapped[list["EmailDigestRecord"]] = relationship(back_populates="run")


class RawJobRecord(Base):
    __tablename__ = "raw_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_name: Mapped[str] = mapped_column(String(255), index=True)
    source_type: Mapped[str] = mapped_column(String(50), index=True)
    source_url: Mapped[str] = mapped_column(String(1000))
    apply_url: Mapped[str] = mapped_column(String(1000))
    external_job_id: Mapped[str | None] = mapped_column(String(255), index=True)
    company_name_raw: Mapped[str] = mapped_column(String(255), index=True)
    title_raw: Mapped[str] = mapped_column(String(255), index=True)
    location_raw: Mapped[str | None] = mapped_column(String(255))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    description_hash: Mapped[str] = mapped_column(String(64), index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class NormalizedJobRecord(Base):
    __tablename__ = "normalized_jobs"
    __table_args__ = (UniqueConstraint("canonical_key", name="uq_normalized_jobs_canonical_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))
    raw_job_id: Mapped[int | None] = mapped_column(ForeignKey("raw_jobs.id"))
    canonical_key: Mapped[str] = mapped_column(String(255), index=True)
    source_name: Mapped[str] = mapped_column(String(255), index=True)
    source_type: Mapped[str] = mapped_column(String(50), index=True)
    source_url: Mapped[str] = mapped_column(String(1000))
    apply_url: Mapped[str] = mapped_column(String(1000))
    company_name: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    title_normalized: Mapped[str] = mapped_column(String(255), index=True)
    external_job_id: Mapped[str | None] = mapped_column(String(255), index=True)
    job_family: Mapped[str | None] = mapped_column(String(255))
    location_text: Mapped[str | None] = mapped_column(String(255))
    location_normalized: Mapped[str | None] = mapped_column(String(255))
    is_remote: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    description_text: Mapped[str] = mapped_column(Text)
    description_hash: Mapped[str] = mapped_column(String(64), index=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    current_status: Mapped[str] = mapped_column(String(50), default="new", index=True)
    application_status: Mapped[str | None] = mapped_column(String(50), index=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    application_notes: Mapped[str | None] = mapped_column(Text)
    resume_variant: Mapped[str | None] = mapped_column(String(255))
    application_url: Mapped[str | None] = mapped_column(String(1000))
    application_metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reopened_count: Mapped[int] = mapped_column(Integer, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    company: Mapped[Company | None] = relationship(back_populates="normalized_jobs")
    scoring_results: Mapped[list["ScoringResultRecord"]] = relationship(back_populates="job")
    status_history: Mapped[list["JobStatusTrackingRecord"]] = relationship(back_populates="job")


class JobStatusTrackingRecord(Base):
    __tablename__ = "job_status_tracking"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    normalized_job_id: Mapped[int] = mapped_column(ForeignKey("normalized_jobs.id"), index=True)
    status: Mapped[str] = mapped_column(String(50), index=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    notes: Mapped[str | None] = mapped_column(Text)

    job: Mapped[NormalizedJobRecord] = relationship(back_populates="status_history")


class ScoringResultRecord(Base):
    __tablename__ = "scoring_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    normalized_job_id: Mapped[int] = mapped_column(ForeignKey("normalized_jobs.id"), index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("daily_runs.id"), index=True)
    fit_score: Mapped[int] = mapped_column(Integer, index=True)
    difficulty_score: Mapped[int] = mapped_column(Integer, index=True)
    recommendation: Mapped[str] = mapped_column(String(50), index=True)
    fit_summary: Mapped[str] = mapped_column(Text)
    difficulty_summary: Mapped[str] = mapped_column(Text)
    top_matching_skills_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    missing_or_weaker_skills_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    tags_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    scorer: Mapped[str] = mapped_column(String(50))
    confidence: Mapped[float] = mapped_column(Float, default=0.75)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    job: Mapped[NormalizedJobRecord] = relationship(back_populates="scoring_results")
    run: Mapped[DailyRun] = relationship(back_populates="scoring_results")


class EmailDigestRecord(Base):
    __tablename__ = "email_digests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("daily_runs.id"), index=True)
    recipient: Mapped[str] = mapped_column(String(255), index=True)
    subject: Mapped[str] = mapped_column(String(255))
    body_text: Mapped[str] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    stats_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    run: Mapped[DailyRun] = relationship(back_populates="email_digests")
