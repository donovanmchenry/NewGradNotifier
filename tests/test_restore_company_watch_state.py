from __future__ import annotations

import importlib.util
import io
import json
import zipfile
from pathlib import Path
from urllib.error import URLError

import pytest


@pytest.fixture
def module(tmp_path, monkeypatch):
    scripts = Path(__file__).resolve().parents[1] / 'scripts'
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location('restore_company', scripts / 'restore_company_watch_state.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv('GITHUB_TOKEN', 'test')
    monkeypatch.setenv('GITHUB_REPOSITORY', 'owner/repo')
    monkeypatch.setenv('COMPANY_WATCH_STATE_PATH', str(tmp_path / 'state.json'))
    return module


def archive(payload):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as z:
        z.writestr('state.json', json.dumps(payload))
    return stream.getvalue()


def test_first_run_without_artifact(module, monkeypatch):
    monkeypatch.setattr(module, '_request_json', lambda *_: {'artifacts': []})
    assert module.main() == 0


def test_restore_failure_is_not_treated_as_first_run(module, monkeypatch):
    def fail(*_):
        raise URLError('network unavailable')
    monkeypatch.setattr(module, '_request_json', fail)
    assert module.main() == 1


def test_latest_state_is_restored_across_pages(module, monkeypatch, tmp_path):
    payload = {'version': 1, 'source_url': 'https://api.ashbyhq.com/posting-api/job-board/delinea', 'seen': {'job': 'date'}}
    artifact = {'name': 'delinea-watch-state-v1', 'expired': False, 'created_at': '2026-10-12', 'id': 2}
    calls = []
    def list_artifacts(url, token):
        calls.append(url)
        if 'page=2' in url:
            return {'artifacts': [artifact]}
        return {'artifacts': [dict(artifact, id=1, expired=True)] * 100}
    monkeypatch.setattr(module, '_request_json', list_artifacts)
    monkeypatch.setattr(module, '_download_artifact_archive', lambda *_: archive(payload))
    assert module.main() == 0
    assert len(calls) == 2
    assert json.loads((tmp_path / 'state.json').read_text()) == payload


def test_bad_archive_preserves_existing_state(module, monkeypatch, tmp_path):
    target = tmp_path / 'state.json'
    target.write_text('existing')
    monkeypatch.setattr(module, '_request_json', lambda *_: {'artifacts': [{'name': 'delinea-watch-state-v1', 'id': 1}]})
    monkeypatch.setattr(module, '_download_artifact_archive', lambda *_: archive({'version': 99}))
    assert module.main() == 1
    assert target.read_text() == 'existing'
