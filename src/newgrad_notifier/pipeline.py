"""End-to-end daily job discovery and digest pipeline."""

from __future__ import annotations

import logging
from pathlib import Path

from newgrad_notifier.collectors.base import CollectorContext
from newgrad_notifier.collectors.factory import build_collectors
from newgrad_notifier.config.settings import AppSettings, load_settings
from newgrad_notifier.contracts import DigestStats, JobLifecycleState, PipelineError, RankedJob, SourceType
from newgrad_notifier.db.repository import Repository
from newgrad_notifier.db.seeding import seed_reference_data
from newgrad_notifier.db.session import create_session_factory, init_db
from newgrad_notifier.dedupe.service import BatchDeduper
from newgrad_notifier.normalization.normalizer import normalize_job
from newgrad_notifier.notifications.email_renderer import render_daily_digest, should_send_immediate_alert
from newgrad_notifier.notifications.sender import build_email_sender
from newgrad_notifier.ranking.service import RankingService
from newgrad_notifier.utils.http import CachedHttpClient
from newgrad_notifier.utils.logging import configure_logging


def build_http_client(settings: AppSettings) -> CachedHttpClient:
    """Create a configured cached HTTP client."""

    return CachedHttpClient(
        cache_dir=Path(settings.cache_dir),
        timeout_seconds=settings.collection.request_timeout_seconds,
        min_domain_interval_seconds=settings.collection.min_domain_interval_seconds,
        cache_ttl_seconds=settings.collection.cache_ttl_seconds,
    )


def run_pipeline_once(config_path: str | None = None) -> None:
    """Run the full pipeline once."""

    settings = load_settings(config_path)
    configure_logging(settings.log_level)
    logger = logging.getLogger(__name__)
    for warning in settings.runtime_warnings:
        logger.warning(warning, extra={"context": {"event": "runtime_warning"}})

    init_db(settings)
    session_factory = create_session_factory(settings)
    email_sender = build_email_sender(settings.email)
    ranking_service = RankingService(settings)
    deduper = BatchDeduper()
    http_client = build_http_client(settings)
    errors: list[PipelineError] = []
    stats = DigestStats()
    try:
        with session_factory() as session:
            seed_reference_data(session, settings)
            repository = Repository(session)
            run = repository.create_run()
            collectors = build_collectors(settings)
            context = CollectorContext(settings=settings, http_client=http_client, logger=logger)
            collected_jobs = []
            for collector in collectors:
                try:
                    collector_jobs = collector.collect(context)
                    collected_jobs.extend(collector_jobs)
                except Exception as exc:  # pragma: no cover - network/source failures
                    logger.exception("Collector failed", extra={"context": {"collector": collector.name}})
                    errors.append(
                        PipelineError(
                            source_name=collector.name,
                            stage="collect",
                            message=f"{collector.name} collector failed",
                            detail=str(exc),
                        )
                    )
            stats.total_collected = len(collected_jobs)
            stats.source_counts = {
                source_type.value: sum(1 for job in collected_jobs if job.source_type == source_type)
                for source_type in SourceType
                if any(job.source_type == source_type for job in collected_jobs)
            }
            if stats.source_counts:
                stats.source_counts = dict(sorted(stats.source_counts.items()))

            normalized_jobs = []
            raw_job_ids: dict[str, int] = {}
            for job in collected_jobs:
                normalized = normalize_job(job)
                raw_record = repository.persist_raw_job(job)
                raw_job_ids[normalized.canonical_key] = raw_record.id
                normalized_jobs.append(normalized)

            stats.total_normalized = len(normalized_jobs)
            dedupe_result = deduper.dedupe(normalized_jobs)
            unique_jobs = dedupe_result.unique_jobs
            rankings = ranking_service.rank_all(unique_jobs)
            ranked_jobs: list[RankedJob] = []
            for normalized, ranking in zip(unique_jobs, rankings):
                record, lifecycle_state = repository.upsert_normalized_job(
                    normalized,
                    raw_job_ids.get(normalized.canonical_key),
                )
                # Overwrite default first_seen_at with the persisted DB value so cross-analysis is accurate
                normalized = normalized.model_copy(update={"first_seen_at": record.first_seen_at})
                repository.persist_scoring(run.id, record.id, ranking)
                prev_fit_score: int | None = None
                if lifecycle_state != JobLifecycleState.NEW:
                    prev_record = repository.fetch_previous_best_scoring(record.id, run.id)
                    if prev_record is not None:
                        prev_fit_score = prev_record.fit_score
                ranked_jobs.append(RankedJob(normalized_job=normalized, ranking=ranking, lifecycle_state=lifecycle_state, prev_fit_score=prev_fit_score))
                if lifecycle_state.value == "new":
                    stats.total_new += 1
                if lifecycle_state.value == "reopened":
                    stats.total_reopened += 1
                if ranking.fit_score >= settings.thresholds.high_signal_fit:
                    stats.total_high_signal += 1
                    if settings.schedule.immediate_alerts_enabled and should_send_immediate_alert(
                        RankedJob(normalized_job=normalized, ranking=ranking, lifecycle_state=lifecycle_state),
                        settings.schedule.immediate_alert_threshold,
                    ):
                        alert_subject = f"[NewGradNotifier] Immediate alert: {normalized.company_name} - {normalized.title}"
                        alert_body = (
                            f"{normalized.company_name} | {normalized.title}\n"
                            f"Location: {normalized.location_text or 'Unknown'}\n"
                            f"Fit: {ranking.fit_score}\nDifficulty: {ranking.difficulty_score}\n"
                            f"Apply: {normalized.apply_url}\n\n{ranking.fit_summary}\n{ranking.difficulty_summary}"
                        )
                        email_sender.send(alert_subject, alert_body, settings.email.recipient)

            stats.total_errors = len(errors)
            rendered_digest = render_daily_digest(
                run_date=run.started_at,
                ranked_jobs=ranked_jobs,
                stats=stats,
                errors=errors,
                high_signal_threshold=settings.thresholds.high_signal_fit,
                top_priority_threshold=settings.thresholds.top_priority_fit,
            )
            email_sender.send(
                rendered_digest.subject,
                rendered_digest.text_body,
                settings.email.recipient,
                body_html=rendered_digest.html_body,
            )
            repository.persist_digest(
                run.id,
                settings.email.recipient,
                rendered_digest.subject,
                rendered_digest.text_body,
                stats,
            )
            repository.complete_run(run, stats, errors)
    finally:
        http_client.close()
