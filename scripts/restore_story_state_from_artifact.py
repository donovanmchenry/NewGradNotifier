"""Restore the latest JSON Story state artifact from GitHub Actions."""

from __future__ import annotations

import io
import json
import os
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


def _request_json(url: str, token: str) -> dict:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "newgrad-notifier",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(request) as response:
        return json.load(response)


def _download_archive(url: str, token: str) -> bytes:
    opener = build_opener(_NoRedirectHandler())
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "newgrad-notifier",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with opener.open(request) as response:
            return response.read()
    except HTTPError as exc:
        if exc.code not in {302, 303, 307, 308}:
            raise
        redirect_url = exc.headers.get("Location")
        if not redirect_url:
            raise
        with urlopen(Request(redirect_url, headers={"User-Agent": "newgrad-notifier"})) as response:
            return response.read()


def _restore_json(archive_bytes: bytes, target_path: Path) -> None:
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        members = [member for member in archive.infolist() if not member.is_dir()]
        matches = [member for member in members if Path(member.filename).name == target_path.name]
        if len(matches) != 1:
            raise ValueError(f"Expected one {target_path.name} in artifact, found {len(matches)}.")
        raw_state = archive.read(matches[0])
    payload = json.loads(raw_state)
    if payload.get("version") != 1 or not isinstance(payload.get("seen"), dict):
        raise ValueError("Story state artifact has an unsupported format.")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = target_path.with_suffix(f"{target_path.suffix}.restore")
    temporary.write_bytes(raw_state)
    temporary.replace(target_path)


def main() -> int:
    token = os.getenv("GITHUB_TOKEN", "")
    repository = os.getenv("GITHUB_REPOSITORY", "")
    artifact_name = os.getenv("STORY_STATE_ARTIFACT_NAME", "zero2sudo-story-state")
    target_path = Path(os.getenv("STORY_WATCH_STATE_PATH", "./data/zero2sudo-story-state.json"))

    if not token or not repository:
        print("GitHub token or repository is missing; starting with a fresh Story baseline.")
        return 0

    artifacts_url = f"https://api.github.com/repos/{repository}/actions/artifacts?per_page=100"
    try:
        payload = _request_json(artifacts_url, token)
    except URLError as exc:
        print(f"Unable to list Story state artifacts: {exc}")
        return 1

    artifacts = [
        artifact
        for artifact in payload.get("artifacts", [])
        if artifact.get("name") == artifact_name and not artifact.get("expired", False)
    ]
    if not artifacts:
        print("No prior Story state artifact found; the watcher will create a baseline.")
        return 0
    artifacts.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    latest = artifacts[0]
    download_url = latest.get("archive_download_url")
    if not download_url and latest.get("id"):
        download_url = f"https://api.github.com/repos/{repository}/actions/artifacts/{latest['id']}/zip"
    if not download_url:
        print("Latest Story state artifact did not include a download URL.")
        return 1

    try:
        _restore_json(_download_archive(download_url, token), target_path)
    except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        print(f"Unable to restore Story state: {exc}")
        return 1
    print(f"Restored Story state artifact '{artifact_name}' to {target_path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
