from __future__ import annotations

import json
import shutil
import subprocess

import pytest

import newgrad_notifier.stories.watcher as watcher
from newgrad_notifier.config.settings import load_settings
from newgrad_notifier.notifications.sender import EmailAttachment, EmailSender
from newgrad_notifier.stories.watcher import (
    StoryItem,
    StoryMedia,
    StoryViewerError,
    parse_story_items,
    watch_stories,
)


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
    assert sender.messages[0]["subject"].startswith("[zero2sudo ")
    assert "New video Story" in sender.messages[0]["subject"]
    assert "https://cdn.example.com/viewer-2" in sender.messages[0]["body_text"]
    assert sender.messages[0]["idempotency_key"].startswith("story-watch-")
    state = json.loads((tmp_path / "story-state.json").read_text(encoding="utf-8"))
    assert set(state["seen"]) == {"key-story-1.mp4", "key-story-2.mp4"}


def test_story_watch_suppresses_non_job_stories_but_marks_them_seen(tmp_path, monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "console")
    settings = load_settings("config/local_dev.toml")
    settings.story_watcher.enabled = True
    settings.story_watcher.state_path = str(tmp_path / "story-state.json")
    settings.story_watcher.notify_existing_on_first_run = True
    sender = RecordingSender()
    social_story = _story("viewer-social", "social.mp4")
    monkeypatch.setattr(
        watcher,
        "_prepare_media",
        lambda story, _config, _index: StoryMedia(
            story=story,
            extracted_text="Dinner was great",
            headline="Dinner was great",
            job_relevant=False,
        ),
    )

    result = watch_stories(settings, sender=sender, story_fetcher=lambda _config: [social_story])

    assert result.new_stories == 1
    assert result.notified_stories == 0
    assert result.notification_sent is False
    assert sender.messages == []
    state = json.loads((tmp_path / "story-state.json").read_text(encoding="utf-8"))
    assert set(state["seen"]) == {"key-social.mp4"}


def test_extract_urls_recognizes_bare_career_domains():
    assert watcher._extract_urls("Apply now at careers.example.com/jobs/123") == (
        "https://careers.example.com/jobs/123",
    )


@pytest.mark.parametrize(
    "text",
    [
        "Software Engineer Intern applications are open",
        "New grad SWE role",
        "Apply at the company careers site",
    ],
)
def test_job_relevance_keywords(text):
    assert watcher._is_job_relevant(text, ()) is True


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
def test_convert_image_and_video_to_jpeg_previews(tmp_path):
    image_path = tmp_path / "source.png"
    video_path = tmp_path / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x240",
            "-frames:v",
            "1",
            str(image_path),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x240:d=11",
            "-pix_fmt",
            "yuv420p",
            str(video_path),
        ],
        check=True,
    )

    image_preview = watcher._convert_to_jpeg(
        image_path.read_bytes(),
        StoryItem("image", "image", "image", "https://example.com/image", "source.png"),
    )
    video_preview = watcher._convert_to_jpeg(
        video_path.read_bytes(),
        StoryItem("video", "video", "video", "https://example.com/video", "source.mp4"),
    )

    assert image_preview.startswith(b"\xff\xd8")
    assert video_preview.startswith(b"\xff\xd8")


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
