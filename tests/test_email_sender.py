from newgrad_notifier.config.settings import EmailSettings
from newgrad_notifier.notifications.sender import ResendEmailSender, SMTPEmailSender, build_email_sender


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
