"""Email delivery abstractions."""

from __future__ import annotations

import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage
from pathlib import Path

import requests

from newgrad_notifier.config.settings import EmailSettings


class EmailSender(ABC):
    """Email delivery contract."""

    @abstractmethod
    def send(self, subject: str, body_text: str, recipient: str, body_html: str | None = None) -> str | None:
        """Send a message and return a provider delivery identifier when available."""


class ConsoleEmailSender(EmailSender):
    """Print digests to stdout for local development."""

    def send(self, subject: str, body_text: str, recipient: str, body_html: str | None = None) -> str | None:
        print(f"To: {recipient}")
        print(f"Subject: {subject}")
        print()
        print(body_text)
        if body_html:
            print("\n--- HTML ---\n")
            print(body_html)
        return None


class FileEmailSender(EmailSender):
    """Write digests to an outbox directory."""

    def __init__(self, outbox_dir: Path) -> None:
        self.outbox_dir = outbox_dir
        self.outbox_dir.mkdir(parents=True, exist_ok=True)

    def send(self, subject: str, body_text: str, recipient: str, body_html: str | None = None) -> str | None:
        safe_subject = subject.replace("/", "-").replace(" ", "_")
        file_path = self.outbox_dir / f"{safe_subject}.txt"
        file_path.write_text(f"To: {recipient}\nSubject: {subject}\n\n{body_text}", encoding="utf-8")
        if body_html:
            html_path = self.outbox_dir / f"{safe_subject}.html"
            html_path.write_text(body_html, encoding="utf-8")
        return str(file_path)


class SMTPEmailSender(EmailSender):
    """SMTP sender for production delivery."""

    def __init__(self, settings: EmailSettings) -> None:
        self.settings = settings

    def send(self, subject: str, body_text: str, recipient: str, body_html: str | None = None) -> str | None:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.settings.sender
        message["To"] = recipient
        message.set_content(body_text)
        if body_html:
            message.add_alternative(body_html, subtype="html")
        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port) as client:
            if self.settings.smtp_use_tls:
                client.starttls()
            if self.settings.smtp_username:
                client.login(self.settings.smtp_username, self.settings.smtp_password)
            client.send_message(message)
        return message.get("Message-ID")


class ResendEmailSender(EmailSender):
    """Resend API sender for transactional notifications."""

    def __init__(self, settings: EmailSettings) -> None:
        self.settings = settings

    def send(self, subject: str, body_text: str, recipient: str, body_html: str | None = None) -> str | None:
        payload = {
            "from": self.settings.sender,
            "to": [recipient],
            "subject": subject,
            "text": body_text,
        }
        if body_html:
            payload["html"] = body_html
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {self.settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        try:
            return response.json().get("id")
        except ValueError:
            return None


def build_email_sender(settings: EmailSettings) -> EmailSender:
    """Construct the configured email sender."""

    if settings.provider == "resend":
        return ResendEmailSender(settings)
    if settings.provider == "smtp":
        return SMTPEmailSender(settings)
    if settings.provider == "file":
        return FileEmailSender(Path(settings.outbox_dir))
    return ConsoleEmailSender()
