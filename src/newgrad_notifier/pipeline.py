"""End-to-end daily job discovery and digest pipeline."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from newgrad_notifier.collectors.base import CollectorContext
from newgrad_notifier.collectors.enrichment import enrich_sparse_jobs
from newgrad_notifier.collectors.factory import build_collectors
from newgrad_notifier.config.settings import AppSettings, load_settings
from newgrad_notifier.contracts import DigestStats, JobLifecycleState, NormalizedJob, PipelineError, RankedJob
from newgrad_notifier.db.models import DailyRun, NormalizedJobRecord
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


def is_fresh_listing(job: NormalizedJob, reference_time: datetime, max_age_days: int) -> bool:
    """Return whether a newly discovered record is recent enough for an email."""

    if job.posted_at is None:
        return True
    posted_at = job.posted_at
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=UTC)
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=UTC)
    return posted_at >= reference_time - timedelta(days=max_age_days)


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
    run_id: int | None = None
    try:
        with session_factory() as session:
            seed_reference_data(session, settings)
            repository = Repository(session)
            ranking_service.set_feedback_signals(repository.build_feedback_signals())
            run = repository.create_run()
            run_id = run.id
            collectors = build_collectors(settings)
            context = CollectorContext(settings=settings, http_client=http_client, logger=logger)
            collected_jobs = []
            source_health: dict[str, dict[str, object]] = {}
            for collector in collectors:
                try:
                    collector_jobs = collector.collect(context)
                    collected_jobs.extend(collector_jobs)
                    errors.extend(getattr(collector, "errors", []))
                    source_health.update(getattr(collector, "source_health", {}))
                    if not collector_jobs and collector.name.startswith(("structured:", "markdown:")):
                        errors.append(
                            PipelineError(
                                source_name=collector.name,
                                stage="health",
                                message="Primary repository source returned zero relevant jobs",
                            )
                        )
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
                    source_health[collector.name] = {
                        "status": "failed",
                        "total_available": None,
                        "relevant_jobs": 0,
                        "error": str(exc),
                    }
            stats.total_collected = len(collected_jobs)
            stats.source_counts = {
                source_name: sum(1 for job in collected_jobs if job.source_name == source_name)
                for source_name in {job.source_name for job in collected_jobs}
            }
            if stats.source_counts:
                stats.source_counts = dict(sorted(stats.source_counts.items()))
            stats.source_health = dict(sorted(source_health.items()))

            previous_runs = repository.fetch_recent_completed_runs(limit=2)
            for source_name, health in stats.source_health.items():
                if health.get("status") != "healthy" or health.get("total_available") != 0:
                    continue
                prior_empty = all(
                    (run.stats_json.get("source_health", {}).get(source_name, {}).get("total_available") == 0)
                    for run in previous_runs
                )
                if len(previous_runs) == 2 and prior_empty:
                    health["status"] = "stale"
                    errors.append(
                        PipelineError(
                            source_name=source_name,
                            stage="health",
                            message="Source returned zero total listings for three consecutive runs",
                        )
                    )

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
            new_candidates = [job for job in unique_jobs if repository.find_normalized_job_by_identity(job) is None]
            enriched_by_key = {
                job.canonical_key: job
                for job in enrich_sparse_jobs(
                    new_candidates,
                    http_client=http_client,
                    max_fetches=settings.collection.max_description_fetches_per_run,
                    min_characters=settings.collection.min_description_characters,
                    logger=logger,
                )
            }
            unique_jobs = [enriched_by_key.get(job.canonical_key, job) for job in unique_jobs]

            persisted_jobs: list[tuple[NormalizedJob, JobLifecycleState, NormalizedJobRecord, bool]] = []
            for normalized in unique_jobs:
                record, lifecycle_state = repository.upsert_normalized_job(
                    normalized,
                    raw_job_ids.get(normalized.canonical_key),
                )
                normalized = normalized.model_copy(update={"first_seen_at": record.first_seen_at})
                fresh = is_fresh_listing(
                    normalized,
                    run.started_at,
                    settings.collection.digest_max_job_age_days,
                )
                persisted_jobs.append((normalized, lifecycle_state, record, fresh))
                if lifecycle_state == JobLifecycleState.NEW and fresh:
                    stats.total_new += 1
                if lifecycle_state == JobLifecycleState.REOPENED and fresh:
                    stats.total_reopened += 1

            actionable = [
                item
                for item in persisted_jobs
                if item[1] in {JobLifecycleState.NEW, JobLifecycleState.REOPENED} and item[3]
            ]
            rankings = ranking_service.rank_all([item[0] for item in actionable])
            ranked_jobs: list[RankedJob] = []
            for (normalized, lifecycle_state, record, _fresh), ranking in zip(actionable, rankings):
                repository.persist_scoring(run.id, record.id, ranking)
                prev_fit_score: int | None = None
                if lifecycle_state != JobLifecycleState.NEW:
                    prev_record = repository.fetch_previous_best_scoring(record.id, run.id)
                    if prev_record is not None:
                        prev_fit_score = prev_record.fit_score
                ranked_jobs.append(RankedJob(normalized_job=normalized, ranking=ranking, lifecycle_state=lifecycle_state, prev_fit_score=prev_fit_score))
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
                digest_min_fit=settings.thresholds.digest_min_fit,
                max_digest_jobs=settings.thresholds.max_digest_jobs,
                tracking_base_url=settings.tracking.base_url if settings.tracking.enabled else "",
                tracking_secret=settings.tracking.secret if settings.tracking.enabled else "",
            )
            if rendered_digest.job_count or settings.email.send_empty_digest:
                delivery_id = email_sender.send(
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
                    body_html=rendered_digest.html_body,
                    delivery_id=delivery_id,
                )
            else:
                logger.info(
                    "Digest suppressed because no jobs met the configured threshold",
                    extra={"context": {"event": "empty_digest_suppressed"}},
                )
            repository.complete_run(run, stats, errors)
    except Exception as exc:
        if run_id is not None:
            with session_factory() as failure_session:
                failed_run = failure_session.get(DailyRun, run_id)
                if failed_run is not None:
                    Repository(failure_session).fail_run(
                        failed_run,
                        PipelineError(source_name="pipeline", stage="fatal", message="Pipeline failed", detail=str(exc)),
                    )
        if settings.email.failure_alerts_enabled and not os.getenv("GITHUB_ACTIONS"):
            try:
                email_sender.send(
                    "[NewGradNotifier] Daily pipeline failed",
                    f"The daily pipeline failed before completing.\n\nError: {exc}",
                    settings.email.recipient,
                )
            except Exception:
                logger.exception("Failure alert could not be delivered")
        raise
    finally:
        http_client.close()
