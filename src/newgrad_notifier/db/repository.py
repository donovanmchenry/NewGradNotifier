"""Repository helpers for raw jobs, normalized jobs, runs, scoring, and digests."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from newgrad_notifier.contracts import (
    CollectedJob,
    DigestStats,
    JobLifecycleState,
    NormalizedJob,
    PipelineError,
    RankedJob,
    RankingResult,
    RunStatus,
)
from newgrad_notifier.db.models import (
    Company,
    DailyRun,
    EmailDigestRecord,
    JobStatusTrackingRecord,
    NormalizedJobRecord,
    RawJobRecord,
    ScoringResultRecord,
)
from newgrad_notifier.utils.hashing import sha256_text
from newgrad_notifier.utils.time import utc_now


class Repository:
    """Encapsulates database access for the daily pipeline."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_run(self) -> DailyRun:
        run = DailyRun(
            run_date=utc_now(),
            started_at=utc_now(),
            status=RunStatus.STARTED.value,
            stats_json={},
            errors_json=[],
        )
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def fetch_recent_completed_runs(self, limit: int = 14) -> list[DailyRun]:
        statement = (
            select(DailyRun)
            .where(DailyRun.status == RunStatus.COMPLETED.value)
            .order_by(DailyRun.started_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def complete_run(self, run: DailyRun, stats: DigestStats, errors: Sequence[PipelineError]) -> None:
        run.completed_at = utc_now()
        run.status = RunStatus.COMPLETED.value
        run.stats_json = stats.model_dump()
        run.errors_json = [error.model_dump() for error in errors]
        self.session.add(run)
        self.session.commit()

    def fail_run(self, run: DailyRun, error: PipelineError) -> None:
        """Mark a run as fatally failed while preserving diagnostic context."""

        run.completed_at = utc_now()
        run.status = RunStatus.FAILED.value
        run.errors_json = [error.model_dump()]
        self.session.add(run)
        self.session.commit()

    def persist_raw_job(self, job: CollectedJob) -> RawJobRecord:
        raw_job = RawJobRecord(
            source_name=job.source_name,
            source_type=job.source_type.value,
            source_url=job.source_url,
            apply_url=job.apply_url,
            external_job_id=job.external_job_id,
            company_name_raw=job.company_name,
            title_raw=job.title,
            location_raw=job.location_text,
            posted_at=job.posted_at,
            description_hash=sha256_text((job.description_text or job.title).strip()),
            payload_json=job.model_dump(mode="json"),
            fetched_at=job.fetched_at,
        )
        self.session.add(raw_job)
        self.session.commit()
        self.session.refresh(raw_job)
        return raw_job

    def find_normalized_job(self, canonical_key: str) -> NormalizedJobRecord | None:
        statement = select(NormalizedJobRecord).where(NormalizedJobRecord.canonical_key == canonical_key)
        return self.session.scalar(statement)

    def list_tracked_jobs(self, limit: int = 100) -> list[NormalizedJobRecord]:
        statement = select(NormalizedJobRecord).order_by(NormalizedJobRecord.last_seen_at.desc()).limit(limit)
        return list(self.session.scalars(statement))

    def build_feedback_signals(self):
        from newgrad_notifier.ranking.feedback import FeedbackSignals

        signals = FeedbackSignals()
        user_states = [
            JobLifecycleState.SAVED.value,
            JobLifecycleState.APPLIED.value,
            JobLifecycleState.IGNORED.value,
        ]
        records = self.session.scalars(
            select(NormalizedJobRecord).where(NormalizedJobRecord.current_status.in_(user_states))
        )
        for record in records:
            score = self.session.scalar(
                select(ScoringResultRecord)
                .where(ScoringResultRecord.normalized_job_id == record.id)
                .order_by(ScoringResultRecord.created_at.desc())
                .limit(1)
            )
            signals.observe(
                positive=record.current_status in {JobLifecycleState.SAVED.value, JobLifecycleState.APPLIED.value},
                company_name=record.company_name,
                tags=score.tags_json if score else [],
                skills=score.top_matching_skills_json if score else [],
                work_mode=record.metadata_json.get("job_details", {}).get("work_mode"),
            )
        return signals

    def upsert_normalized_job(
        self,
        normalized_job: NormalizedJob,
        raw_job_id: int | None,
    ) -> tuple[NormalizedJobRecord, JobLifecycleState]:
        existing = self.find_normalized_job(normalized_job.canonical_key)
        now = utc_now()
        if existing is None:
            company = self._find_company_by_name(normalized_job.company_name)
            record = NormalizedJobRecord(
                company_id=company.id if company else None,
                raw_job_id=raw_job_id,
                canonical_key=normalized_job.canonical_key,
                source_name=normalized_job.source_name,
                source_type=normalized_job.source_type.value,
                source_url=normalized_job.source_url,
                apply_url=normalized_job.apply_url,
                company_name=normalized_job.company_name,
                title=normalized_job.title,
                title_normalized=normalized_job.title_normalized,
                external_job_id=normalized_job.external_job_id,
                job_family=normalized_job.job_family,
                location_text=normalized_job.location_text,
                location_normalized=normalized_job.location_normalized,
                is_remote=normalized_job.is_remote,
                posted_at=normalized_job.posted_at,
                description_text=normalized_job.description_text,
                description_hash=normalized_job.description_hash,
                content_hash=normalized_job.content_hash,
                confidence=normalized_job.confidence,
                current_status=JobLifecycleState.NEW.value,
                reopened_count=0,
                first_seen_at=now,
                last_seen_at=now,
                metadata_json=normalized_job.metadata,
            )
            self.session.add(record)
            self.session.flush()
            self._track_status(record, JobLifecycleState.NEW)
            self.session.commit()
            self.session.refresh(record)
            return record, JobLifecycleState.NEW

        user_managed_states = {
            JobLifecycleState.SAVED.value,
            JobLifecycleState.APPLIED.value,
            JobLifecycleState.IGNORED.value,
        }
        user_managed = existing.current_status in user_managed_states
        lifecycle_state = JobLifecycleState.SEEN
        last_seen = existing.last_seen_at
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=UTC)
        was_stale = (now - last_seen) >= timedelta(days=7)
        content_changed = existing.content_hash != normalized_job.content_hash
        if not user_managed and was_stale and content_changed:
            lifecycle_state = JobLifecycleState.REOPENED
            existing.reopened_count += 1

        existing.raw_job_id = raw_job_id
        company = self._find_company_by_name(normalized_job.company_name)
        existing.company_id = company.id if company else existing.company_id
        existing.source_name = normalized_job.source_name
        existing.source_type = normalized_job.source_type.value
        existing.source_url = normalized_job.source_url
        existing.apply_url = normalized_job.apply_url
        existing.company_name = normalized_job.company_name
        existing.title = normalized_job.title
        existing.title_normalized = normalized_job.title_normalized
        existing.external_job_id = normalized_job.external_job_id
        existing.job_family = normalized_job.job_family
        existing.location_text = normalized_job.location_text
        existing.location_normalized = normalized_job.location_normalized
        existing.is_remote = normalized_job.is_remote
        existing.posted_at = normalized_job.posted_at
        existing.description_text = normalized_job.description_text
        existing.description_hash = normalized_job.description_hash
        existing.content_hash = normalized_job.content_hash
        existing.confidence = normalized_job.confidence
        if not user_managed:
            existing.current_status = lifecycle_state.value
        existing.last_seen_at = now
        existing.metadata_json = normalized_job.metadata
        if lifecycle_state == JobLifecycleState.REOPENED:
            self._track_status(existing, lifecycle_state)
        self.session.add(existing)
        self.session.commit()
        self.session.refresh(existing)
        return existing, lifecycle_state

    def _find_company_by_name(self, company_name: str) -> Company | None:
        statement = select(Company).where(Company.name.ilike(company_name))
        return self.session.scalar(statement)

    def _track_status(self, record: NormalizedJobRecord, state: JobLifecycleState) -> None:
        tracking_record = JobStatusTrackingRecord(
            normalized_job_id=record.id,
            status=state.value,
            changed_at=utc_now(),
            notes=None,
        )
        self.session.add(tracking_record)
        self.session.flush()

    def persist_scoring(self, run_id: int, job_id: int, ranking: RankingResult) -> ScoringResultRecord:
        record = ScoringResultRecord(
            normalized_job_id=job_id,
            run_id=run_id,
            fit_score=ranking.fit_score,
            difficulty_score=ranking.difficulty_score,
            recommendation=ranking.recommendation.value,
            fit_summary=ranking.fit_summary,
            difficulty_summary=ranking.difficulty_summary,
            top_matching_skills_json=ranking.top_matching_skills,
            missing_or_weaker_skills_json=ranking.missing_or_weaker_skills,
            tags_json=ranking.tags,
            scorer=ranking.scorer,
            confidence=ranking.confidence,
            created_at=utc_now(),
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def persist_digest(
        self,
        run_id: int,
        recipient: str,
        subject: str,
        body_text: str,
        stats: DigestStats,
        body_html: str | None = None,
        delivery_id: str | None = None,
    ) -> EmailDigestRecord:
        stats_payload = stats.model_dump()
        if delivery_id:
            stats_payload["delivery_id"] = delivery_id
        record = EmailDigestRecord(
            run_id=run_id,
            recipient=recipient,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            sent_at=utc_now(),
            stats_json=stats_payload,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def fetch_previous_best_scoring(self, normalized_job_id: int, exclude_run_id: int) -> ScoringResultRecord | None:
        statement = (
            select(ScoringResultRecord)
            .where(ScoringResultRecord.normalized_job_id == normalized_job_id)
            .where(ScoringResultRecord.run_id != exclude_run_id)
            .order_by(ScoringResultRecord.created_at.desc())
            .limit(1)
        )
        return self.session.scalar(statement)

    def mark_user_status(self, job_id: int, state: JobLifecycleState, notes: str | None = None) -> None:
        record = self.session.get(NormalizedJobRecord, job_id)
        if record is None:
            return
        self._set_user_status(record, state, notes)

    def mark_user_status_by_key(
        self,
        canonical_key: str,
        state: JobLifecycleState,
        notes: str | None = None,
    ) -> NormalizedJobRecord | None:
        record = self.find_normalized_job(canonical_key)
        if record is None:
            return None
        self._set_user_status(record, state, notes)
        return record

    def _set_user_status(
        self,
        record: NormalizedJobRecord,
        state: JobLifecycleState,
        notes: str | None,
    ) -> None:
        if state not in {JobLifecycleState.SAVED, JobLifecycleState.APPLIED, JobLifecycleState.IGNORED}:
            raise ValueError(f"Unsupported user-managed status: {state.value}")
        now = utc_now()
        record.current_status = state.value
        record.application_status = state.value
        record.application_notes = notes or record.application_notes
        if state == JobLifecycleState.APPLIED:
            record.applied_at = now
            record.application_url = record.apply_url
        self.session.add(record)
        self.session.add(
            JobStatusTrackingRecord(
                normalized_job_id=record.id,
                status=state.value,
                changed_at=now,
                notes=notes,
            )
        )
        self.session.commit()

    def fetch_ranked_jobs_for_digest(self, run_id: int) -> list[RankedJob]:
        statement = (
            select(NormalizedJobRecord, ScoringResultRecord)
            .join(ScoringResultRecord, ScoringResultRecord.normalized_job_id == NormalizedJobRecord.id)
            .where(ScoringResultRecord.run_id == run_id)
        )
        rows = self.session.execute(statement).all()
        ranked_jobs: list[RankedJob] = []
        for job_record, score_record in rows:
            normalized = NormalizedJob(
                canonical_key=job_record.canonical_key,
                source_name=job_record.source_name,
                source_type=job_record.source_type,
                source_url=job_record.source_url,
                apply_url=job_record.apply_url,
                company_name=job_record.company_name,
                title=job_record.title,
                title_normalized=job_record.title_normalized,
                external_job_id=job_record.external_job_id,
                job_family=job_record.job_family,
                location_text=job_record.location_text,
                location_normalized=job_record.location_normalized,
                is_remote=job_record.is_remote,
                posted_at=job_record.posted_at,
                description_text=job_record.description_text,
                description_hash=job_record.description_hash,
                first_seen_at=job_record.first_seen_at,
                last_seen_at=job_record.last_seen_at,
                content_hash=job_record.content_hash,
                confidence=job_record.confidence,
                metadata=job_record.metadata_json,
            )
            ranking = RankingResult(
                fit_score=score_record.fit_score,
                difficulty_score=score_record.difficulty_score,
                recommendation=score_record.recommendation,
                fit_summary=score_record.fit_summary,
                difficulty_summary=score_record.difficulty_summary,
                top_matching_skills=score_record.top_matching_skills_json,
                missing_or_weaker_skills=score_record.missing_or_weaker_skills_json,
                tags=score_record.tags_json,
                scorer=score_record.scorer,
                confidence=score_record.confidence,
            )
            ranked_jobs.append(
                RankedJob(
                    normalized_job=normalized,
                    ranking=ranking,
                    lifecycle_state=job_record.current_status,
                )
            )
        return ranked_jobs
