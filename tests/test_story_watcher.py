from __future__ import annotations

import json

import pytest

from newgrad_notifier.config.settings import load_settings
from newgrad_notifier.notifications.sender import EmailAttachment, EmailSender
from newgrad_notifier.stories.watcher import StoryItem, StoryViewerError, parse_story_items, watch_stories


def _story(story_id: str, filename: str) -> StoryItem:
    return StoryItem(
        viewer_id=story_id,
        dedupe_key=f"key-{filename}",
        media_type="video",
        media_url=f"https://cdn.example.com/{story_id}",
        filename=filename,
    )


class RecordingSender(EmailSender):
    def __init__(self) -> None:
        self.messages: list[dict] = []

    def send(
        self,
        subject: str,
        body_text: str,
        recipient: str,
        body_html: str | None = None,
        *,
        attachments: list[EmailAttachment] | None = None,
        idempotency_key: str | None = None,
    ) -> str | None:
        self.messages.append(
            {
                "subject": subject,
                "body_text": body_text,
                "recipient": recipient,
                "body_html": body_html,
                "attachments": attachments or [],
                "idempotency_key": idempotency_key,
            }
        )
        return "email-story-1"


def test_parse_story_items_reads_metadata_and_deduplicates_by_filename():
    html = """
    <html><head><title>zero2sudo Stories</title></head><body>
      <span data-type="stories" data-id="viewer-a" data-slide="0" data-media-type="image"
            data-content="https://cdn.example.com/a" data-filename="stable-file.heic"></span>
      <span data-type="stories" data-id="viewer-b" data-slide="1" data-media-type="image"
            data-content="https://cdn.example.com/b" data-filename="stable-file.heic"></span>
      <span data-type="stories" data-id="viewer-c" data-slide="2" data-media-type="video"
            data-content="https://cdn.example.com/c" data-filename="other.mp4"></span>
    </body></html>
    """

    stories = parse_story_items(html, username="zero2sudo")

    assert len(stories) == 2
    assert stories[0].filename == "stable-file.heic"
    assert stories[0].slide == 0
    assert stories[1].media_type == "video"


def test_parse_story_items_accepts_valid_profile_with_no_active_stories():
    html = "<html><head><title>zero2sudo - Anonymous profile view</title></head><body></body></html>"

    assert parse_story_items(html, username="zero2sudo") == []


def test_parse_story_items_rejects_missing_metadata_when_counter_is_nonzero():
    html = """
    <html><head><title>zero2sudo - Anonymous profile view</title></head><body>
      <div class="profile__stories-counter">47</div>
    </body></html>
    """

    with pytest.raises(StoryViewerError, match="advertised 47 active Stories.*only 0"):
        parse_story_items(html, username="zero2sudo")


def test_parse_story_items_rejects_challenge_page():
    with pytest.raises(StoryViewerError, match="CAPTCHA"):
        parse_story_items("<html><title>Just a moment</title><div>captcha</div></html>", username="zero2sudo")


def test_story_watch_baselines_then_notifies_only_for_new_items(tmp_path, monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "console")
    settings = load_settings("config/local_dev.toml")
    settings.story_watcher.enabled = True
    settings.story_watcher.state_path = str(tmp_path / "story-state.json")
    settings.story_watcher.attach_images = False
    settings.story_watcher.ocr_enabled = False
    sender = RecordingSender()
    first_story = _story("viewer-1", "story-1.mp4")

    initial = watch_stories(settings, sender=sender, story_fetcher=lambda _config: [first_story])
    unchanged = watch_stories(settings, sender=sender, story_fetcher=lambda _config: [first_story])
    second_story = _story("viewer-2", "story-2.mp4")
    changed = watch_stories(
        settings,
        sender=sender,
        story_fetcher=lambda _config: [first_story, second_story],
    )

    assert initial.baseline_created is True
    assert initial.notification_sent is False
    assert unchanged.new_stories == 0
    assert changed.new_stories == 1
    assert changed.notification_sent is True
    assert len(sender.messages) == 1
    assert "@zero2sudo posted 1 new Story" in sender.messages[0]["subject"]
    assert "https://cdn.example.com/viewer-2" in sender.messages[0]["body_text"]
    assert sender.messages[0]["idempotency_key"].startswith("story-watch-")
    state = json.loads((tmp_path / "story-state.json").read_text(encoding="utf-8"))
    assert set(state["seen"]) == {"key-story-1.mp4", "key-story-2.mp4"}


def test_story_watch_does_not_mark_story_seen_when_delivery_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "console")
    settings = load_settings("config/local_dev.toml")
    settings.story_watcher.enabled = True
    settings.story_watcher.state_path = str(tmp_path / "story-state.json")
    settings.story_watcher.attach_images = False
    settings.story_watcher.ocr_enabled = False
    first_story = _story("viewer-1", "story-1.mp4")
    watch_stories(settings, sender=RecordingSender(), story_fetcher=lambda _config: [first_story])

    class FailingSender(RecordingSender):
        def send(self, *args, **kwargs):
            raise RuntimeError("delivery failed")

    second_story = _story("viewer-2", "story-2.mp4")
    with pytest.raises(RuntimeError, match="delivery failed"):
        watch_stories(
            settings,
            sender=FailingSender(),
            story_fetcher=lambda _config: [first_story, second_story],
        )

    state = json.loads((tmp_path / "story-state.json").read_text(encoding="utf-8"))
    assert set(state["seen"]) == {"key-story-1.mp4"}
