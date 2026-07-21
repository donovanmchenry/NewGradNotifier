"""Signing helpers for tracking links."""

from __future__ import annotations

import hashlib
import hmac
from urllib.parse import urlencode


def sign_job_key(canonical_key: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), canonical_key.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_job_token(canonical_key: str, token: str, secret: str) -> bool:
    if not token or not secret:
        return False
    return hmac.compare_digest(sign_job_key(canonical_key, secret), token)


def build_tracking_url(base_url: str, canonical_key: str, secret: str, action: str | None = None) -> str:
    if base_url and "://" not in base_url:
        base_url = f"https://{base_url}"
    query = {"token": sign_job_key(canonical_key, secret)}
    if action:
        query["action"] = action
    return f"{base_url.rstrip('/')}/jobs/{canonical_key}?{urlencode(query)}"
