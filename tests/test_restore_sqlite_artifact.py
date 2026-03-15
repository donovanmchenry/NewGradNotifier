from __future__ import annotations

import importlib.util
import io
import zipfile
from pathlib import Path


def _load_restore_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "restore_sqlite_from_artifact.py"
    spec = importlib.util.spec_from_file_location("restore_sqlite_from_artifact", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_restore_sqlite_artifact_main_extracts_latest_artifact(monkeypatch, tmp_path):
    module = _load_restore_module()

    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("data/newgradnotifier.db", "sqlite-bytes")

    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("SQLITE_RESTORE_DIR", str(tmp_path))
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
    assert (tmp_path / "data" / "newgradnotifier.db").read_text() == "sqlite-bytes"
