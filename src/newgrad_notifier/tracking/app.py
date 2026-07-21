"""Small dependency-free WSGI dashboard for tracking applications."""

from __future__ import annotations

import base64
import hmac
from html import escape
from http import HTTPStatus
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

from newgrad_notifier.config.settings import AppSettings, load_settings
from newgrad_notifier.contracts import JobLifecycleState
from newgrad_notifier.db.repository import Repository
from newgrad_notifier.db.session import create_session_factory, init_db
from newgrad_notifier.tracking.security import build_tracking_url, verify_job_token

_ALLOWED_ACTIONS = {
    JobLifecycleState.SAVED.value: "Saved",
    JobLifecycleState.APPLIED.value: "Applied",
    JobLifecycleState.IGNORED.value: "Not interested",
}

_CSS = """
body{margin:0;background:#09090b;color:#e4e4e7;font:15px/1.5 Arial,sans-serif}
main{max-width:900px;margin:0 auto;padding:32px 20px 64px}h1,h2{color:#fafafa}a{color:#fafafa}
.muted{color:#a1a1aa}.card{background:#18181b;border:1px solid #27272a;border-radius:8px;padding:18px;margin:12px 0}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}.button,button{background:#fafafa;color:#18181b;border:1px solid #fafafa;border-radius:6px;padding:9px 13px;font-weight:700;text-decoration:none;cursor:pointer}
.secondary{background:#18181b;color:#fafafa;border-color:#3f3f46}textarea{width:100%;box-sizing:border-box;background:#09090b;color:#fafafa;border:1px solid #3f3f46;border-radius:6px;padding:10px;margin:10px 0}
""".strip()


def _page(title: str, body: str) -> bytes:
    return (
        "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{escape(title)}</title><style>{_CSS}</style></head><body><main>{body}</main></body></html>"
    ).encode("utf-8")


class TrackingApplication:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.session_factory = create_session_factory(settings)

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "/").rstrip("/") or "/"
        method = environ.get("REQUEST_METHOD", "GET").upper()
        if path == "/healthz":
            return self._respond(start_response, HTTPStatus.OK, b"ok", "text/plain; charset=utf-8")
        if path == "/":
            if not self._dashboard_authorized(environ):
                return self._unauthorized(start_response)
            return self._dashboard(start_response)
        if path.startswith("/jobs/"):
            canonical_key = path.removeprefix("/jobs/")
            query = parse_qs(environ.get("QUERY_STRING", ""))
            token = query.get("token", [""])[0]
            if not verify_job_token(canonical_key, token, self.settings.tracking.secret):
                return self._respond(start_response, HTTPStatus.FORBIDDEN, _page("Forbidden", "<h1>Invalid tracking link</h1>"))
            if method == "POST":
                return self._update_status(environ, start_response, canonical_key, token)
            return self._job_page(start_response, canonical_key, token, query.get("action", [""])[0])
        return self._respond(start_response, HTTPStatus.NOT_FOUND, _page("Not found", "<h1>Not found</h1>"))

    def _dashboard_authorized(self, environ) -> bool:
        header = environ.get("HTTP_AUTHORIZATION", "")
        if not header.startswith("Basic "):
            return False
        try:
            username, password = base64.b64decode(header.removeprefix("Basic ")).decode("utf-8").split(":", 1)
        except (ValueError, UnicodeDecodeError):
            return False
        expected_password = self.settings.tracking.dashboard_password or self.settings.tracking.secret
        return hmac.compare_digest(username, self.settings.tracking.dashboard_username) and hmac.compare_digest(
            password, expected_password
        )

    def _dashboard(self, start_response):
        with self.session_factory() as session:
            repository = Repository(session)
            jobs = repository.list_tracked_jobs(limit=100)
            recent_runs = repository.fetch_recent_completed_runs(limit=1)
        cards = []
        for job in jobs:
            url = build_tracking_url(
                self.settings.tracking.base_url,
                job.canonical_key,
                self.settings.tracking.secret,
            )
            cards.append(
                f"<div class='card'><strong>{escape(job.company_name)}</strong><br>{escape(job.title)}"
                f"<p class='muted'>{escape(job.location_text or 'Location not listed')} · Status: {escape(job.current_status)}</p>"
                f"<a class='button secondary' href='{escape(url)}'>Review</a></div>"
            )
        health_html = "<div class='card'><strong>No completed source-health run yet.</strong></div>"
        if recent_runs:
            health = recent_runs[0].stats_json.get("source_health", {})
            problem_sources = [
                name for name, item in health.items() if item.get("status") in {"failed", "stale", "unsupported"}
            ]
            health_html = (
                f"<div class='card'><strong>{len(health)} sources checked</strong>"
                f"<p class='muted'>{len(problem_sources)} need attention"
                f"{': ' + escape(', '.join(problem_sources)) if problem_sources else ''}</p></div>"
            )
        body = (
            "<h1>Application tracker</h1><p class='muted'>Your 100 most recently seen jobs.</p>"
            f"<h2>Source health</h2>{health_html}<h2>Jobs</h2>{''.join(cards)}"
        )
        return self._respond(start_response, HTTPStatus.OK, _page("Application tracker", body))

    def _job_page(self, start_response, canonical_key: str, token: str, requested_action: str):
        with self.session_factory() as session:
            job = Repository(session).find_normalized_job(canonical_key)
        if job is None:
            return self._respond(start_response, HTTPStatus.NOT_FOUND, _page("Not found", "<h1>Job not found</h1>"))
        details = job.metadata_json.get("job_details", {})
        detail_lines = [
            f"Work mode: {details.get('work_mode') or 'Not listed'}",
            f"Salary: {details.get('salary') or 'Not listed'}",
            f"Sponsorship: {details.get('sponsorship') or 'Not listed'}",
            f"Clearance: {details.get('clearance') or 'Not listed'}",
        ]
        forms = []
        for action, label in _ALLOWED_ACTIONS.items():
            selected = " class='button'" if action == requested_action else " class='button secondary'"
            forms.append(
                f"<form method='post' style='display:inline'><input type='hidden' name='token' value='{escape(token)}'>"
                f"<input type='hidden' name='status' value='{action}'><button{selected} type='submit'>{label}</button></form>"
            )
        body = (
            f"<h1>{escape(job.company_name)}</h1><h2>{escape(job.title)}</h2>"
            f"<p class='muted'>{escape(job.location_text or 'Location not listed')} · Current status: {escape(job.current_status)}</p>"
            f"<div class='card'>{'<br>'.join(escape(line) for line in detail_lines)}</div>"
            f"<p><a href='{escape(job.apply_url)}'>Open application</a></p>"
            f"<div class='row'>{''.join(forms)}</div>"
        )
        return self._respond(start_response, HTTPStatus.OK, _page(job.title, body))

    def _update_status(self, environ, start_response, canonical_key: str, token: str):
        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = 0
        form = parse_qs(environ["wsgi.input"].read(length).decode("utf-8"))
        status = form.get("status", [""])[0]
        notes = form.get("notes", [None])[0]
        if status not in _ALLOWED_ACTIONS:
            return self._respond(start_response, HTTPStatus.BAD_REQUEST, _page("Invalid status", "<h1>Invalid status</h1>"))
        with self.session_factory() as session:
            record = Repository(session).mark_user_status_by_key(canonical_key, JobLifecycleState(status), notes)
        if record is None:
            return self._respond(start_response, HTTPStatus.NOT_FOUND, _page("Not found", "<h1>Job not found</h1>"))
        return self._respond(
            start_response,
            HTTPStatus.OK,
            _page(
                "Status updated",
                f"<h1>Marked as {_ALLOWED_ACTIONS[status]}</h1><p>{escape(record.company_name)} - {escape(record.title)}</p>"
                f"<p><a class='button' href='{escape(record.apply_url)}'>Open application</a></p>",
            ),
        )

    @staticmethod
    def _respond(start_response, status: HTTPStatus, body: bytes, content_type: str = "text/html; charset=utf-8"):
        start_response(f"{status.value} {status.phrase}", [("Content-Type", content_type), ("Content-Length", str(len(body)))])
        return [body]

    @staticmethod
    def _unauthorized(start_response):
        body = _page("Sign in", "<h1>Authentication required</h1>")
        start_response(
            "401 Unauthorized",
            [
                ("Content-Type", "text/html; charset=utf-8"),
                ("Content-Length", str(len(body))),
                ("WWW-Authenticate", 'Basic realm="NewGradNotifier"'),
            ],
        )
        return [body]


def run_tracking_server(config_path: str | None = None) -> None:
    settings = load_settings(config_path)
    init_db(settings)
    app = TrackingApplication(settings)
    with make_server(settings.tracking.host, settings.tracking.port, app) as server:
        print(f"Tracking dashboard listening on http://{settings.tracking.host}:{settings.tracking.port}")
        server.serve_forever()
