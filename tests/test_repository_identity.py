from sqlalchemy import func, select

from newgrad_notifier.config.settings import load_settings
from newgrad_notifier.contracts import CollectedJob, JobLifecycleState, SourceType
from newgrad_notifier.db.models import NormalizedJobRecord
from newgrad_notifier.db.repository import Repository
from newgrad_notifier.db.session import create_session_factory, init_db
from newgrad_notifier.normalization.normalizer import normalize_job


def test_repository_matches_legacy_record_by_durable_url_alias(monkeypatch, tmp_path):
    monkeypatch.setenv("EMAIL_PROVIDER", "console")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "identity.db"))
    settings = load_settings("config/local_dev.toml")
    init_db(settings)
    session_factory = create_session_factory(settings)

    historical = normalize_job(
        CollectedJob(
            source_name="simplify_new_grad",
            source_type=SourceType.STRUCTURED,
            source_url="simplify.json",
            apply_url="https://jobs.ashbyhq.com/faros-ai/622e1f1e-4a39-4e7c-8526-1189ca588066/application?embed=true",
            company_name="Faros AI",
            title="Software Engineer New Grad",
            external_job_id="source-specific-id",
            location_text="San Mateo, CA",
        )
    ).model_copy(update={"canonical_key": "legacy-source-specific-key"})

    with session_factory() as session:
        first_record, first_state = Repository(session).upsert_normalized_job(historical, None)
        first_id = first_record.id
    assert first_state == JobLifecycleState.NEW

    current = normalize_job(
        CollectedJob(
            source_name="speedyapply_2027",
            source_type=SourceType.STRUCTURED,
            source_url="jobs.md",
            apply_url="https://jobs.ashbyhq.com/faros-ai/622e1f1e-4a39-4e7c-8526-1189ca588066",
            company_name="Faros",
            title="Software Engineer - New Grad",
            external_job_id="different-source-id",
            location_text="San Mateo, CA",
        )
    )

    with session_factory() as session:
        repository = Repository(session)
        second_record, second_state = repository.upsert_normalized_job(current, None)
        record_count = session.scalar(select(func.count()).select_from(NormalizedJobRecord))

    assert second_state == JobLifecycleState.SEEN
    assert second_record.id == first_id
    assert record_count == 1
    assert second_record.metadata_json["seen_in_sources"] == ["simplify_new_grad", "speedyapply_2027"]
