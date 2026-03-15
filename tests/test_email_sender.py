from pathlib import Path

from newgrad_notifier.config.settings import EmailSettings
from newgrad_notifier.notifications.sender import FileEmailSender, ResendEmailSender, SMTPEmailSender, build_email_sender


def test_build_email_sender_prefers_resend():
    sender = build_email_sender(
        EmailSettings(
            provider="resend",
            recipient="dzmchenry@gmail.com",
            sender="NewGrad Notifier <onboarding@resend.dev>",
            resend_api_key="re_test_123",
        )
    )

    assert isinstance(sender, ResendEmailSender)


def test_build_email_sender_supports_smtp_fallback():
    sender = build_email_sender(
        EmailSettings(
            provider="smtp",
            recipient="dzmchenry@gmail.com",
            sender="dzmchenry@gmail.com",
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            smtp_username="dzmchenry@gmail.com",
            smtp_password="app-password",
        )
    )

    assert isinstance(sender, SMTPEmailSender)


def test_file_email_sender_writes_html_variant(tmp_path):
    sender = FileEmailSender(Path(tmp_path))

    sender.send(
        "Daily Digest",
        "plain body",
        "dzmchenry@gmail.com",
        body_html="<html><body><strong>html body</strong></body></html>",
    )

    assert (tmp_path / "Daily_Digest.txt").read_text(encoding="utf-8").endswith("plain body")
    assert "html body" in (tmp_path / "Daily_Digest.html").read_text(encoding="utf-8")
