"""Load default or user-supplied target company definitions."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any


def load_company_list(path: str | None = None) -> list[dict[str, Any]]:
    """Load company coverage configuration from JSON."""

    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    default_resource = resources.files("newgrad_notifier.config").joinpath("default_companies.json")
    with resources.as_file(default_resource) as default_path:
        return json.loads(default_path.read_text(encoding="utf-8"))


def load_default_ats_boards() -> list[dict[str, Any]]:
    """Load the curated ATS board seed list bundled with the app."""

    default_resource = resources.files("newgrad_notifier.config").joinpath("default_ats_boards.json")
    with resources.as_file(default_resource) as default_path:
        return json.loads(default_path.read_text(encoding="utf-8"))
