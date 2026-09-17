"""Poll a public Instagram Story viewer and alert on newly observed Stories."""

from __future__ import annotations

import json
import logging
import mimetypes
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Callable

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from newgrad_notifier.config.settings import AppSettings, StoryWatcherSettings
from newgrad_notifier.notifications.sender import EmailAttachment, EmailSender, build_email_sender
from newgrad_notifier.utils.hashing import sha256_text

LOGGER = logging.getLogger(__name__)
_STORY_SELECTOR = '[data-type="stories"][data-id][data-content]'
_URL_PATTERN = re.compile(r"(?:https?://|www\.)[^\s<>()\[\]{}]+", re.IGNORECASE)
_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_RAW_ATTACHMENTS_BYTES = 24 * 1024 * 1024


class StoryViewerError(RuntimeError):
    """Raised when the viewer page cannot be trusted or parsed."""


@dataclass(frozen=True, slots=True)
class StoryItem:
    """One Story exposed by the viewer page."""

    viewer_id: str
    dedupe_key: str
    media_type: str
    media_url: str
    filename: str
    slide: int | None = None


@dataclass(frozen=True, slots=True)
class StoryMedia:
    """Downloaded media plus best-effort OCR output."""

    story: StoryItem
    content: bytes | None = None
    content_type: str = ""
    attachment_filename: str = ""
    extracted_text: str = ""
    extracted_urls: tuple[str, ...] = ()
    error: str = ""


@dataclass(frozen=True, slots=True)
class StoryWatchResult:
    """Summary returned by one watcher execution."""

    total_stories: int
    new_stories: int
    notification_sent: bool
    baseline_created: bool = False


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _story_dedupe_key(viewer_id: str, filename: str, media_url: str) -> str:
    stable_value = filename or viewer_id or media_url
    return sha256_text(stable_value)[:32]


def parse_story_items(html: str, *, username: str) -> list[StoryItem]:
    """Extract Story metadata rendered into the viewer page."""

    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    profile_text = " ".join(
        element.get_text(" ", strip=True)
        for element in soup.select(".profile__nickname, .profile__name, h1")
    )
    page_identity = f"{title} {profile_text}".lower()
    if username.lower() not in page_identity:
        lowered = html.lower()
        if "just a moment" in lowered or "cf-chl" in lowered or "captcha" in lowered:
            raise StoryViewerError("The Story viewer returned an anti-bot or CAPTCHA page.")
        raise StoryViewerError(f"The Story viewer page did not identify the expected profile @{username}.")

    stories: list[StoryItem] = []
    seen: set[str] = set()
    for element in soup.select(_STORY_SELECTOR):
        viewer_id = str(element.get("data-id", "")).strip()
        media_url = str(element.get("data-content", "")).strip()
        media_type = str(element.get("data-media-type", "image")).strip().lower()
        filename = Path(str(element.get("data-filename", "")).strip()).name
        if not viewer_id or not media_url.startswith(("https://", "http://")):
            continue
        if media_type not in {"image", "video"}:
            media_type = "unknown"
        try:
            slide = int(str(element.get("data-slide", "")))
        except ValueError:
            slide = None
        dedupe_key = _story_dedupe_key(viewer_id, filename, media_url)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        stories.append(
            StoryItem(
                viewer_id=viewer_id,
                dedupe_key=dedupe_key,
                media_type=media_type,
                media_url=media_url,
                filename=filename,
                slide=slide,
            )
        )

    counter = soup.select_one(".profile__stories-counter")
    counter_text = counter.get_text(" ", strip=True) if counter else ""
    try:
        advertised_count = int(counter_text)
    except ValueError:
        advertised_count = 0
    if advertised_count > len(stories):
        raise StoryViewerError(
            f"The viewer advertised {advertised_count} active Stories but exposed metadata for "
            f"only {len(stories)}."
        )
    return stories


def fetch_story_items(config: StoryWatcherSettings) -> list[StoryItem]:
    """Render and parse the viewer profile in a real Google Chrome session."""

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                channel="chrome",
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(
                viewport={"width": 1440, "height": 1200},
                locale="en-US",
                timezone_id="America/New_York",
                color_scheme="light",
            )
            context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            page = context.new_page()
            response = page.goto(config.source_url, wait_until="domcontentloaded", timeout=60_000)
            if response is None:
                raise StoryViewerError("The Story viewer navigation returned no response.")
            if not response.ok:
                raise StoryViewerError(f"The Story viewer returned HTTP {response.status}.")
            page.wait_for_timeout(8_000)
            html = page.content()
            browser.close()
    except PlaywrightError as exc:
        raise StoryViewerError(f"Unable to render the Story viewer in Chrome: {exc}") from exc
    return parse_story_items(html, username=config.username)


def _read_state(path: Path, source_url: str) -> tuple[bool, dict[str, str]]:
    if not path.exists():
        return False, {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StoryViewerError(f"Unable to read Story state at {path}: {exc}") from exc
    if payload.get("version") != 1 or not isinstance(payload.get("seen"), dict):
        raise StoryViewerError(f"Story state at {path} has an unsupported format.")
    stored_source = str(payload.get("source_url", ""))
    if stored_source and stored_source != source_url:
        raise StoryViewerError("Story state belongs to a different viewer URL; refusing to mix sources.")
    return True, {str(key): str(value) for key, value in payload["seen"].items()}


def _write_state(path: Path, source_url: str, seen: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    retained = dict(sorted(seen.items(), key=lambda item: item[1], reverse=True)[:2000])
    payload = {
        "version": 1,
        "source_url": source_url,
        "updated_at": _utc_timestamp(),
        "seen": retained,
    }
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _download_media(story: StoryItem, max_bytes: int) -> tuple[bytes, str]:
    with requests.get(
        story.media_url,
        headers={"User-Agent": "newgrad-notifier/0.1.0"},
        stream=True,
        timeout=30,
    ) as response:
        response.raise_for_status()
        content_length = int(response.headers.get("Content-Length", "0") or 0)
        if content_length > max_bytes:
            raise StoryViewerError(f"media is {content_length} bytes, above the {max_bytes}-byte limit")
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                raise StoryViewerError(f"media exceeded the {max_bytes}-byte limit while downloading")
            chunks.append(chunk)
        content_type = response.headers.get("Content-Type", "application/octet-stream").split(";", 1)[0]
    return b"".join(chunks), content_type


def _attachment_filename(story: StoryItem, content_type: str, index: int) -> str:
    original = _UNSAFE_FILENAME.sub("-", story.filename).strip(".-")
    suffix = mimetypes.guess_extension(content_type) or Path(original).suffix or ".bin"
    if content_type == "image/jpeg":
        suffix = ".jpg"
    stem = Path(original).stem if original else story.viewer_id
    stem = _UNSAFE_FILENAME.sub("-", stem)[:80].strip(".-") or f"story-{index}"
    return f"zero2sudo-{index:02d}-{stem}{suffix}"


def _run_ocr(content: bytes, content_type: str) -> str:
    if not content_type.startswith("image/") or shutil.which("tesseract") is None:
        return ""
    suffix = mimetypes.guess_extension(content_type) or ".img"
    with tempfile.NamedTemporaryFile(suffix=suffix) as source:
        source.write(content)
        source.flush()
        try:
            result = subprocess.run(
                ["tesseract", source.name, "stdout", "-l", "eng", "--psm", "6"],
                capture_output=True,
                check=False,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            LOGGER.warning("Story OCR failed: %s", exc)
            return ""
    if result.returncode != 0:
        LOGGER.warning("Story OCR returned %s: %s", result.returncode, result.stderr.strip())
        return ""
    return re.sub(r"\n{3,}", "\n\n", result.stdout.strip())[:4000]


def _normalize_extracted_url(value: str) -> str:
    cleaned = value.rstrip(".,;:!?\"')]}>")
    return cleaned if cleaned.startswith(("http://", "https://")) else f"https://{cleaned}"


def _prepare_media(story: StoryItem, config: StoryWatcherSettings, index: int) -> StoryMedia:
    if story.media_type != "image" or not (config.attach_images or config.ocr_enabled):
        return StoryMedia(story=story)
    try:
        content, content_type = _download_media(story, config.max_attachment_bytes)
        if not content_type.startswith("image/"):
            raise StoryViewerError(f"expected image media but received {content_type}")
        extracted_text = _run_ocr(content, content_type) if config.ocr_enabled else ""
        urls = tuple(dict.fromkeys(_normalize_extracted_url(item) for item in _URL_PATTERN.findall(extracted_text)))
        filename = _attachment_filename(story, content_type, index)
        return StoryMedia(
            story=story,
            content=content if config.attach_images else None,
            content_type=content_type,
            attachment_filename=filename,
            extracted_text=extracted_text,
            extracted_urls=urls,
        )
    except (requests.RequestException, StoryViewerError, ValueError) as exc:
        LOGGER.warning("Unable to download Story %s: %s", story.viewer_id, exc)
        return StoryMedia(story=story, error=str(exc))


def _render_story_email(username: str, source_url: str, media: list[StoryMedia]) -> tuple[str, str, str]:
    count = len(media)
    subject = f"[NewGradNotifier] @{username} posted {count} new Stor{'y' if count == 1 else 'ies'}"
    text_lines = [
        f"@{username} posted {count} new Instagram Stor{'y' if count == 1 else 'ies'}.",
        "",
        "The anonymous viewer does not preserve Instagram link stickers. Use the attached image or media link to identify the role, then open the company's application page.",
        "",
    ]
    cards: list[str] = []
    for index, item in enumerate(media, start=1):
        story = item.story
        text_lines.extend([f"Story {index} ({story.media_type})", story.media_url])
        if item.attachment_filename:
            text_lines.append(f"Attached: {item.attachment_filename}")
        if item.extracted_text:
            text_lines.extend(["Extracted text:", item.extracted_text])
        if item.extracted_urls:
            text_lines.extend(["Possible links:", *[f"- {url}" for url in item.extracted_urls]])
        if item.error:
            text_lines.append(f"Media download note: {item.error}")
        text_lines.append("")

        extracted_html = ""
        if item.extracted_text:
            extracted_html = (
                '<p style="margin:12px 0 4px; color:#a1a1aa; font-size:12px;">OCR text</p>'
                f'<pre style="white-space:pre-wrap; margin:0; padding:12px; background:#09090b; color:#e4e4e7; border-radius:6px; font:12px/1.45 monospace;">{escape(item.extracted_text)}</pre>'
            )
        links_html = ""
        if item.extracted_urls:
            links_html = "".join(
                f'<a href="{escape(url)}" style="display:block; margin-top:8px; color:#93c5fd;">Possible application link: {escape(url)}</a>'
                for url in item.extracted_urls
            )
        note_html = (
            f'<p style="margin:10px 0 0; color:#fbbf24; font-size:12px;">Media download note: {escape(item.error)}</p>'
            if item.error
            else ""
        )
        cards.append(
            '<div style="margin:0 0 16px; padding:18px; background:#18181b; border:1px solid #27272a; border-radius:8px;">'
            f'<p style="margin:0 0 12px; color:#fafafa;"><strong>Story {index}</strong> &middot; {escape(story.media_type)}</p>'
            f'<a href="{escape(story.media_url)}" style="display:inline-block; padding:9px 14px; background:#fafafa; color:#18181b; text-decoration:none; border-radius:6px; font-weight:bold;">View or download Story</a>'
            f'{links_html}{extracted_html}{note_html}</div>'
        )

    text_lines.extend(["Viewer profile:", source_url])
    html_body = f"""<!doctype html>
<html lang="en">
<body style="margin:0; padding:0; background:#09090b; color:#e4e4e7; font-family:Arial, Helvetica, sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="#09090b">
    <tr><td align="center"><table role="presentation" width="640" cellpadding="0" cellspacing="0" style="max-width:640px; width:100%;">
      <tr><td style="padding:32px 20px 40px;">
        <h1 style="margin:0 0 8px; font-size:24px; color:#fafafa;">New Stories from @{escape(username)}</h1>
        <p style="margin:0 0 22px; color:#a1a1aa; line-height:1.5;">The viewer strips Instagram link stickers. Check the attached screenshots and any OCR links below, then apply directly on the company site.</p>
        {''.join(cards)}
        <p style="margin:24px 0 0;"><a href="{escape(source_url)}" style="color:#93c5fd;">Open the anonymous viewer profile</a></p>
      </td></tr>
    </table></td></tr>
  </table>
</body>
</html>"""
    return subject, "\n".join(text_lines), html_body


def watch_stories(
    settings: AppSettings,
    *,
    sender: EmailSender | None = None,
    story_fetcher: Callable[[StoryWatcherSettings], list[StoryItem]] = fetch_story_items,
) -> StoryWatchResult:
    """Run one idempotent Story check and send at most one notification."""

    config = settings.story_watcher
    if not config.enabled:
        LOGGER.info("Story watcher is disabled.")
        return StoryWatchResult(total_stories=0, new_stories=0, notification_sent=False)

    state_path = Path(config.state_path)
    state_exists, seen = _read_state(state_path, config.source_url)
    stories = story_fetcher(config)
    observed_at = _utc_timestamp()

    if not state_exists and not config.notify_existing_on_first_run:
        for story in stories:
            seen[story.dedupe_key] = observed_at
        _write_state(state_path, config.source_url, seen)
        LOGGER.info("Initialized Story baseline with %s active Stories.", len(stories))
        return StoryWatchResult(
            total_stories=len(stories),
            new_stories=0,
            notification_sent=False,
            baseline_created=True,
        )

    new_stories = [story for story in stories if story.dedupe_key not in seen]
    if not new_stories:
        LOGGER.info("No new Stories found among %s active Stories.", len(stories))
        return StoryWatchResult(total_stories=len(stories), new_stories=0, notification_sent=False)

    prepared = [_prepare_media(story, config, index) for index, story in enumerate(new_stories, start=1)]
    attachment_bytes = 0
    for index, item in enumerate(prepared):
        if item.content is None:
            continue
        if attachment_bytes + len(item.content) > _MAX_RAW_ATTACHMENTS_BYTES:
            note = "Attachment omitted to keep the email below the provider size limit."
            prepared[index] = replace(
                item,
                content=None,
                attachment_filename="",
                error=f"{item.error} {note}".strip(),
            )
            continue
        attachment_bytes += len(item.content)
    attachments = [
        EmailAttachment(
            filename=item.attachment_filename,
            content=item.content,
            content_type=item.content_type,
        )
        for item in prepared
        if item.content is not None and item.attachment_filename
    ]
    subject, body_text, body_html = _render_story_email(
        config.username,
        config.source_url,
        prepared,
    )
    delivery = sender or build_email_sender(settings.email)
    idempotency_key = f"story-watch-{sha256_text('|'.join(sorted(item.dedupe_key for item in new_stories)))[:32]}"
    delivery.send(
        subject,
        body_text,
        settings.email.recipient,
        body_html,
        attachments=attachments,
        idempotency_key=idempotency_key,
    )

    for story in new_stories:
        seen[story.dedupe_key] = observed_at
    _write_state(state_path, config.source_url, seen)
    LOGGER.info("Sent one Story notification for %s new Stories.", len(new_stories))
    return StoryWatchResult(
        total_stories=len(stories),
        new_stories=len(new_stories),
        notification_sent=True,
    )
