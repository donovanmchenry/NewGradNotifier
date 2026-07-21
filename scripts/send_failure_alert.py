"""Send an independent Resend alert when a GitHub Actions workflow fails."""

from __future__ import annotations

import json
import os
from urllib.error import URLError
from urllib.request import Request, urlopen


def main() -> int:
    if os.getenv("FAILURE_ALERTS_ENABLED", "true").lower() not in {"1", "true", "yes"}:
        print("Failure alerts are disabled.")
        return 0
    api_key = os.getenv("RESEND_API_KEY", "")
    recipient = os.getenv("EMAIL_RECIPIENT", "")
    sender = os.getenv("EMAIL_SENDER", "NewGrad Notifier <onboarding@resend.dev>")
    if not api_key or not recipient:
        print("Resend credentials are unavailable; rely on the GitHub Actions failure notification.")
        return 0
    run_url = (
        f"{os.getenv('GITHUB_SERVER_URL', 'https://github.com')}/"
        f"{os.getenv('GITHUB_REPOSITORY', '')}/actions/runs/{os.getenv('GITHUB_RUN_ID', '')}"
    )
    payload = json.dumps(
        {
            "from": sender,
            "to": [recipient],
            "subject": "[NewGradNotifier] Daily workflow failed",
            "text": f"The daily job workflow failed. Review the run here:\n{run_url}",
        }
    ).encode("utf-8")
    request = Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            print(f"Failure alert accepted by Resend ({response.status}).")
    except URLError as exc:
        print(f"Unable to deliver failure alert: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
