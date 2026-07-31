"""Restore the latest SQLite artifact from GitHub Actions if one exists."""

from __future__ import annotations

import io
import json
import os
import shutil
import sqlite3
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
    for accept_header in ("application/vnd.github+json", ""):
        request_headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "newgrad-notifier",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if accept_header:
            request_headers["Accept"] = accept_header
        request = Request(url, headers=request_headers)
        try:
            with opener.open(request) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code in {302, 303, 307, 308}:
                redirect_url = exc.headers.get("Location")
                if not redirect_url:
                    raise
                signed_request = Request(redirect_url, headers={"User-Agent": "newgrad-notifier"})
                with urlopen(signed_request) as response:
                    return response.read()
            if exc.code != 415 or not accept_header:
                raise
    raise RuntimeError("Unable to download artifact archive after retrying request variants.")


def _database_member(archive: zipfile.ZipFile, target_path: Path) -> zipfile.ZipInfo:
    """Find the configured database in either nested or flattened artifacts."""

    files = [member for member in archive.infolist() if not member.is_dir()]
    configured_name = target_path.as_posix().removeprefix("./")
    exact_matches = [member for member in files if member.filename == configured_name]
    if len(exact_matches) == 1:
        return exact_matches[0]

    basename_matches = [member for member in files if Path(member.filename).name == target_path.name]
    if len(basename_matches) == 1:
        return basename_matches[0]
    if not basename_matches:
        raise ValueError(f"Artifact does not contain {target_path.name}.")
    raise ValueError(f"Artifact contains multiple files named {target_path.name}.")


def _restore_database(archive_bytes: bytes, target_path: Path) -> None:
    """Validate and atomically restore the archived database to its runtime path."""

    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = target_path.with_suffix(f"{target_path.suffix}.restore")
    temporary_path.unlink(missing_ok=True)

    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            member = _database_member(archive, target_path)
            with archive.open(member) as source, temporary_path.open("wb") as destination:
                shutil.copyfileobj(source, destination)

        with sqlite3.connect(temporary_path) as connection:
            result = connection.execute("PRAGMA quick_check").fetchone()
        if result != ("ok",):
            raise ValueError(f"Restored database failed SQLite validation: {result!r}")

        temporary_path.replace(target_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def main() -> int:
    token = os.getenv("GITHUB_TOKEN", "")
    repository = os.getenv("GITHUB_REPOSITORY", "")
    artifact_name = os.getenv("SQLITE_ARTIFACT_NAME", "newgradnotifier-sqlite-state")
    target_path = Path(os.getenv("SQLITE_PATH", "./data/newgradnotifier.db"))

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
        download_url = latest.get("archive_download_url")
        if not download_url and latest.get("id"):
            download_url = f"https://api.github.com/repos/{repository}/actions/artifacts/{latest['id']}/zip"
        if not download_url:
            print("Latest SQLite artifact did not include a download URL; skipping restore.")
            return 0
        archive_bytes = _download_artifact_archive(download_url, token)
    except HTTPError as exc:
        print(f"Unable to download artifact ({exc.code}); skipping restore.")
        return 0

    try:
        _restore_database(archive_bytes, target_path)
    except (OSError, sqlite3.DatabaseError, ValueError, zipfile.BadZipFile) as exc:
        print(f"Unable to restore a valid SQLite database: {exc}")
        return 1
    print(f"Restored SQLite artifact '{artifact_name}' to {target_path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
