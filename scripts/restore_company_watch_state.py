"""Restore dedicated company notification history; fail closed on restore errors."""
from __future__ import annotations

import io
import json
import os
import zipfile
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode

from newgrad_notifier.company_watch import validate_state
from restore_sqlite_from_artifact import _request_json, _download_artifact_archive, _database_member


def _restore_state(raw_archive: bytes, target: Path, source_url: str) -> None:
    with zipfile.ZipFile(io.BytesIO(raw_archive)) as archive:
        raw = archive.read(_database_member(archive, target))
    validate_state(json.loads(raw), source_url)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".restore")
    temporary.write_bytes(raw)
    temporary.replace(target)


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    name = os.environ.get("COMPANY_STATE_ARTIFACT_NAME", "delinea-watch-state-v1")
    target = Path(os.environ.get("COMPANY_WATCH_STATE_PATH", "./data/delinea-watch-state.json"))
    source_url = os.environ.get("COMPANY_WATCH_SOURCE_URL", "https://api.ashbyhq.com/posting-api/job-board/delinea")
    if not token or not repository:
        print("GitHub credentials are missing; refusing to discard notification history.")
        return 1
    try:
        artifacts = []
        page = 1
        while True:
            query = urlencode({"name": name, "per_page": 100, "page": page})
            payload = _request_json(f"https://api.github.com/repos/{repository}/actions/artifacts?{query}", token)
            batch = payload["artifacts"]
            artifacts.extend(a for a in batch if a.get("name") == name and not a.get("expired", False))
            if len(batch) < 100:
                break
            page += 1
        if not artifacts:
            print("No retained company watch state; current eligible listings will be checked.")
            return 0
        latest = max(artifacts, key=lambda a: (a.get("created_at", ""), a["id"]))
        url = latest.get("archive_download_url") or f"https://api.github.com/repos/{repository}/actions/artifacts/{latest['id']}/zip"
        _restore_state(_download_artifact_archive(url, token), target, source_url)
    except (URLError, OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        print(f"Company state restore failed; refusing to scan without history: {exc}")
        return 1
    print(f"Restored {name} to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
