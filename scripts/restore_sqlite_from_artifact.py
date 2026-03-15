"""Restore the latest SQLite artifact from GitHub Actions if one exists."""

from __future__ import annotations

import io
import json
import os
import zipfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen


class _NoRedirectHandler(HTTPRedirectHandler):
    """Preserve redirect responses so we can follow signed URLs manually."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


def _request_json(url: str, token: str) -> dict:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "newgrad-notifier",
        },
    )
    with urlopen(request) as response:
        return json.load(response)


def _download_artifact_archive(url: str, token: str) -> bytes:
    opener = build_opener(_NoRedirectHandler())
    request = Request(
        url,
        headers={
            "Accept": "application/octet-stream",
            "Authorization": f"Bearer {token}",
            "User-Agent": "newgrad-notifier",
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
        signed_request = Request(redirect_url, headers={"User-Agent": "newgrad-notifier"})
        with urlopen(signed_request) as response:
            return response.read()


def main() -> int:
    token = os.getenv("GITHUB_TOKEN", "")
    repository = os.getenv("GITHUB_REPOSITORY", "")
    artifact_name = os.getenv("SQLITE_ARTIFACT_NAME", "newgradnotifier-sqlite-state")
    output_dir = Path(os.getenv("SQLITE_RESTORE_DIR", "."))

    if not token or not repository:
        print("GitHub token or repository is missing; skipping SQLite artifact restore.")
        return 0

    artifacts_url = f"https://api.github.com/repos/{repository}/actions/artifacts?per_page=100"
    try:
        payload = _request_json(artifacts_url, token)
    except HTTPError as exc:
        print(f"Unable to list artifacts ({exc.code}); skipping restore.")
        return 0

    artifacts = [
        artifact
        for artifact in payload.get("artifacts", [])
        if artifact.get("name") == artifact_name and not artifact.get("expired", False)
    ]
    if not artifacts:
        print("No prior SQLite artifact found.")
        return 0

    artifacts.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    latest = artifacts[0]
    try:
        archive_bytes = _download_artifact_archive(latest["archive_download_url"], token)
    except HTTPError as exc:
        print(f"Unable to download artifact ({exc.code}); skipping restore.")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        archive.extractall(output_dir)
    print(f"Restored SQLite artifact '{artifact_name}' from workflow history.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
