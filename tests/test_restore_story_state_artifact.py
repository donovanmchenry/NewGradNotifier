from __future__ import annotations

import importlib.util
import io
import json
import zipfile
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "restore_story_state_from_artifact.py"
    spec = importlib.util.spec_from_file_location("restore_story_state_from_artifact", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _archive(payload: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("data/zero2sudo-story-state.json", json.dumps(payload))
    return buffer.getvalue()


def test_restore_story_state_allows_missing_first_artifact(tmp_path, monkeypatch):
    module = _load_module()
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("STORY_WATCH_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(module, "_request_json", lambda *_args: {"artifacts": []})

    assert module.main() == 0
    assert not (tmp_path / "state.json").exists()


def test_restore_story_state_downloads_and_validates_latest_artifact(tmp_path, monkeypatch):
    module = _load_module()
    target = tmp_path / "zero2sudo-story-state.json"
    state = {
        "version": 1,
        "source_url": "https://insta-stories-viewer.com/zero2sudo/",
        "seen": {"story-1": "2026-09-16T12:00:00+00:00"},
    }
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("STORY_WATCH_STATE_PATH", str(target))
    monkeypatch.setattr(
        module,
        "_request_json",
        lambda *_args: {
            "artifacts": [
                {
                    "name": "zero2sudo-story-state",
                    "expired": False,
                    "created_at": "2026-09-16T12:01:00Z",
                    "archive_download_url": "https://api.example.com/artifact.zip",
                }
            ]
        },
    )
    monkeypatch.setattr(module, "_download_archive", lambda *_args: _archive(state))

    assert module.main() == 0
    assert json.loads(target.read_text(encoding="utf-8")) == state


def test_restore_story_state_rejects_invalid_payload(tmp_path, monkeypatch):
    module = _load_module()
    target = tmp_path / "zero2sudo-story-state.json"
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("STORY_WATCH_STATE_PATH", str(target))
    monkeypatch.setattr(
        module,
        "_request_json",
        lambda *_args: {
            "artifacts": [
                {
                    "name": "zero2sudo-story-state",
                    "expired": False,
                    "created_at": "2026-09-16T12:01:00Z",
                    "archive_download_url": "https://api.example.com/artifact.zip",
                }
            ]
        },
    )
    monkeypatch.setattr(module, "_download_archive", lambda *_args: _archive({"version": 99}))

    assert module.main() == 1
    assert not target.exists()
