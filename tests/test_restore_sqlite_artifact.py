from __future__ import annotations

import importlib.util
import io
import sqlite3
import zipfile
from pathlib import Path

import pytest


def _load_restore_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "restore_sqlite_from_artifact.py"
    spec = importlib.util.spec_from_file_location("restore_sqlite_from_artifact", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sqlite_bytes(tmp_path: Path) -> bytes:
    database_path = tmp_path / "artifact-source.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE daily_runs (run_date TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO daily_runs VALUES ('2026-07-30')")
    return database_path.read_bytes()


@pytest.mark.parametrize("archive_path", ["newgradnotifier.db", "data/newgradnotifier.db"])
def test_restore_sqlite_artifact_main_restores_to_configured_path(monkeypatch, tmp_path, archive_path):
    module = _load_restore_module()

    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr(archive_path, _sqlite_bytes(tmp_path))

    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    target_path = tmp_path / "data" / "newgradnotifier.db"
    monkeypatch.setenv("SQLITE_PATH", str(target_path))
    monkeypatch.setattr(
        module,
        "_request_json",
        lambda url, token: {
            "artifacts": [
                {
                    "name": "newgradnotifier-sqlite-state",
                    "expired": False,
                    "created_at": "2026-03-15T20:59:04Z",
                    "archive_download_url": "https://api.github.com/artifacts/1/zip",
                }
            ]
        },
    )
    monkeypatch.setattr(module, "_download_artifact_archive", lambda url, token: archive_buffer.getvalue())

    exit_code = module.main()

    assert exit_code == 0
    with sqlite3.connect(target_path) as connection:
        assert connection.execute("SELECT run_date FROM daily_runs").fetchone() == ("2026-07-30",)


def test_restore_sqlite_artifact_main_rejects_archive_without_database(monkeypatch, tmp_path):
    module = _load_restore_module()

    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("unrelated.txt", "not a database")

    target_path = tmp_path / "data" / "newgradnotifier.db"
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("SQLITE_PATH", str(target_path))
    monkeypatch.setattr(
        module,
        "_request_json",
        lambda url, token: {
            "artifacts": [
                {
                    "name": "newgradnotifier-sqlite-state",
                    "expired": False,
                    "created_at": "2026-03-15T20:59:04Z",
                    "archive_download_url": "https://api.github.com/artifacts/1/zip",
                }
            ]
        },
    )
    monkeypatch.setattr(module, "_download_artifact_archive", lambda url, token: archive_buffer.getvalue())

    assert module.main() == 1
    assert not target_path.exists()


def test_required_restore_fails_closed_when_no_artifact_exists(monkeypatch, tmp_path):
    module = _load_restore_module()
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "state.db"))
    monkeypatch.setenv("SQLITE_RESTORE_REQUIRED", "true")
    monkeypatch.setattr(module, "_request_json", lambda _url, _token: {"artifacts": []})

    assert module.main() == 1


def test_optional_restore_allows_first_run_without_artifact(monkeypatch, tmp_path):
    module = _load_restore_module()
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "state.db"))
    monkeypatch.setenv("SQLITE_RESTORE_REQUIRED", "false")
    monkeypatch.setattr(module, "_request_json", lambda _url, _token: {"artifacts": []})

    assert module.main() == 0
