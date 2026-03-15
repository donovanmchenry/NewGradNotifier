"""Hash helpers for job identity and content tracking."""

from __future__ import annotations

import hashlib


def sha256_text(value: str) -> str:
    """Return the SHA-256 digest for a text payload."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()

