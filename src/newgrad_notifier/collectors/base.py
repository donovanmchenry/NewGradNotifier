"""Collector interfaces and shared context."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from newgrad_notifier.config.settings import AppSettings
from newgrad_notifier.contracts import CollectedJob
from newgrad_notifier.utils.http import CachedHttpClient


@dataclass(slots=True)
class CollectorContext:
    """Runtime dependencies shared by all collectors."""

    settings: AppSettings
    http_client: CachedHttpClient
    logger: logging.Logger


class Collector(ABC):
    """Base collector contract."""

    name: str

    @abstractmethod
    def collect(self, context: CollectorContext) -> list[CollectedJob]:
        """Collect jobs from a source."""

