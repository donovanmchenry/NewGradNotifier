"""Email delivery abstractions."""

from __future__ import annotations

import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage
from pathlib import Path

from newgrad_notifier.config.settings import EmailSettings


class EmailSender(ABC):
    """Email delivery contract."""

    @abstractmethod
    def send(self, subject: str, body_text: str, recipient: str) -> None:
        """Send a plaintext message."""


class ConsoleEmailSender(EmailSender):
    """Print digests to stdout for local development."""

    def send(self, subject: str, body_text: str, recipient: str) -> None:
        print(f"To: {recipient}")
        print(f"Subject: {subject}")
        print()
        print(body_text)


class FileEmailSender(EmailSender):
    """Write digests to an outbox directory."""

    def __init__(self, outbox_dir: Path) -> None:
        self.outbox_dir = outbox_dir
        self.outbox_dir.mkdir(parents=True, exist_ok=True)

    def send(self, subject: str, body_text: str, recipient: str) -> None:
        safe_subject = subject.replace("/", "-").replace(" ", "_")
        file_path = self.outbox_dir / f"{safe_subject}.txt"
        file_path.write_text(f"To: {recipient}\nSubject: {subject}\n\n{body_text}", encoding="utf-8")


class SMTPEmailSender(EmailSender):
    """SMTP sender for production delivery."""

    def __init__(self, settings: EmailSettings) -> None:
        self.settings = settings

    def send(self, subject: str, body_text: str, recipient: str) -> None:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.settings.sender
        message["To"] = recipient
        message.set_content(body_text)
        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port) as client:
            if self.settings.smtp_use_tls:
                client.starttls()
            if self.settings.smtp_username:
                client.login(self.settings.smtp_username, self.settings.smtp_password)
            client.send_message(message)


def build_email_sender(settings: EmailSettings) -> EmailSender:
    """Construct the configured email sender."""

    if settings.provider == "smtp":
        return SMTPEmailSender(settings)
    if settings.provider == "file":
        return FileEmailSender(Path(settings.outbox_dir))
    return ConsoleEmailSender()
