"""Company-specific alerts independent of daily ranking, age limits, and digest caps."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from bs4 import BeautifulSoup

from newgrad_notifier.collectors.ats.ashby import AshbyCollector
from newgrad_notifier.collectors.relevance import cohort_allowed, is_relevant_role, location_allowed
from newgrad_notifier.config.settings import AppSettings
from newgrad_notifier.normalization.job_details import extract_job_details
from newgrad_notifier.notifications.sender import EmailSender, build_email_sender
from newgrad_notifier.utils.hashing import sha256_text
from newgrad_notifier.utils.http import CachedHttpClient


@dataclass(frozen=True)
class WatchResult:
    total_jobs: int = 0
    matching_jobs: int = 0
    notified_jobs: int = 0


def validate_state(payload: object, source_url: str) -> dict[str, str]:
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("Company watch state has an unsupported format")
    if payload.get("source_url") != source_url:
        raise ValueError("Company watch state belongs to a different board")
    seen = payload.get("seen")
    if not isinstance(seen, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in seen.items()):
        raise ValueError("Company watch state has invalid notification history")
    return dict(seen)


def _save_state(path: Path, source_url: str, seen: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps({"version": 1, "source_url": source_url, "seen": seen}, indent=2))
    temporary.replace(path)


def classify_posting(item: dict, settings: AppSettings) -> tuple[str, str] | None:
    """Keep explicit junior matches and flag generic SWE roles for human review."""
    title = str(item.get("title") or "")
    description = BeautifulSoup(str(item.get("descriptionHtml") or item.get("descriptionPlain") or ""), "html.parser").get_text(" ", strip=True)
    location = str(item.get("locationName") or item.get("location") or "")
    if item.get("isListed") is False or "intern" in str(item.get("employmentType", "")).lower():
        return None
    if not location_allowed(location, settings) or not cohort_allowed(title, settings):
        return None
    # Associate/junior may not appear among NGN's strict title hints.
    if re.search(r"\b(?:intern(?:ship)?|co[- ]?op)\b", title, re.I):
        return None
    details = extract_job_details(title=title, description=description, location=location, is_remote=bool(item.get("isRemote")))
    years = details.get("graduation_years", [])
    if years and str(settings.candidate_profile.graduation_year) not in years:
        return None
    if is_relevant_role(title, description, settings):
        return "Early-career match", description
    if is_relevant_role(title, description, settings, source_context="new grad"):
        return "Eligibility unclear: review requirements", description
    return None


def watch_company(settings: AppSettings, *, client: CachedHttpClient | None = None,
                  sender: EmailSender | None = None) -> WatchResult:
    config = settings.company_watch
    if not config.enabled:
        return WatchResult()
    board = config.board
    if board.platform != "ashby" or not board.enabled:
        raise ValueError("Company watch requires an enabled Ashby board")
    source_url = board.api_url or f"https://api.ashbyhq.com/posting-api/job-board/{board.identifier}"
    path = Path(config.state_path)
    seen = validate_state(json.loads(path.read_text()), source_url) if path.exists() else {}
    owns_client = client is None
    client = client or CachedHttpClient(Path(settings.cache_dir), timeout_seconds=settings.collection.request_timeout_seconds)
    try:
        _, postings = AshbyCollector().fetch_board(board, client, use_cache=False)
    finally:
        if owns_client:
            client.close()
    # Validate all eligible postings before sending any messages.
    matches = []
    for item in postings:
        classification = classify_posting(item, settings)
        if classification:
            url = str(item.get("applyUrl") or item.get("jobUrl") or "")
            if not url.startswith("https://jobs.ashbyhq.com/"):
                raise ValueError("Matching Ashby posting has no valid application URL")
            key = str(item.get("id") or url.removesuffix("/application"))
            matches.append((key, item, url, classification))
    _save_state(path, source_url, seen)
    notified = 0
    for key, item, url, (label, description) in matches:
        if key in seen:
            continue
        sender = sender or build_email_sender(settings.email)
        body = (f"{label}\n\n{item['title']}\n"
                f"Location: {item.get('locationName') or item.get('location') or 'Not specified'}\n"
                f"Apply: {url}\n\n"
                "This dedicated watch bypasses NGN's fit score and daily digest limit. "
                "Verify graduation eligibility and experience requirements before applying.\n\n"
                f"{description[:3000]}\n")
        sender.send(f"[{board.company_name} watch] {item['title']}", body, settings.email.recipient,
                    idempotency_key="company-watch-" + sha256_text(source_url + "|" + key))
        seen[key] = datetime.now(UTC).isoformat()
        _save_state(path, source_url, seen)
        notified += 1
    return WatchResult(len(postings), len(matches), notified)
