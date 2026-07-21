from io import BytesIO
from urllib.parse import urlencode

from newgrad_notifier.config.settings import load_settings
from newgrad_notifier.contracts import CollectedJob, JobLifecycleState, SourceType
from newgrad_notifier.db.repository import Repository
from newgrad_notifier.db.session import create_session_factory, init_db
from newgrad_notifier.normalization.normalizer import normalize_job
from newgrad_notifier.tracking.app import TrackingApplication
from newgrad_notifier.tracking.security import sign_job_key


def _call_app(app, path, *, method="GET", query="", body=""):
    response = {}

    def start_response(status, headers):
        response["status"] = status
        response["headers"] = headers

    payload = body.encode("utf-8")
    environ = {
        "PATH_INFO": path,
        "QUERY_STRING": query,
        "REQUEST_METHOD": method,
        "CONTENT_LENGTH": str(len(payload)),
        "wsgi.input": BytesIO(payload),
    }
    response["body"] = b"".join(app(environ, start_response)).decode("utf-8")
    return response


def test_signed_tracking_action_updates_status_and_survives_rescan(monkeypatch, tmp_path):
    monkeypatch.setenv("EMAIL_PROVIDER", "console")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "tracking.db"))
    settings = load_settings("config/local_dev.toml")
    settings.tracking.enabled = True
    settings.tracking.base_url = "https://tracker.example.com"
    settings.tracking.secret = "test-secret"
    init_db(settings)
    normalized = normalize_job(
        CollectedJob(
            source_name="fixture",
            source_type=SourceType.STRUCTURED,
            source_url="fixture.json",
            apply_url="https://example.com/apply",
            company_name="Example",
            title="Software Engineer, New Grad 2027",
            location_text="Remote",
            description_text="Remote Python product role.",
        )
    )
    factory = create_session_factory(settings)
    with factory() as session:
        repository = Repository(session)
        record, _ = repository.upsert_normalized_job(normalized, None)
        canonical_key = record.canonical_key

    token = sign_job_key(canonical_key, settings.tracking.secret)
    app = TrackingApplication(settings)
    page = _call_app(app, f"/jobs/{canonical_key}", query=urlencode({"token": token, "action": "applied"}))
    assert page["status"].startswith("200")
    assert "Applied" in page["body"]

    result = _call_app(
        app,
        f"/jobs/{canonical_key}",
        method="POST",
        query=urlencode({"token": token}),
        body=urlencode({"status": "applied", "token": token}),
    )
    assert result["status"].startswith("200")
    assert "Marked as Applied" in result["body"]

    with factory() as session:
        repository = Repository(session)
        repository.upsert_normalized_job(normalized, None)
        persisted = repository.find_normalized_job(canonical_key)
        assert persisted is not None
        assert persisted.current_status == JobLifecycleState.APPLIED.value
        assert persisted.applied_at is not None
