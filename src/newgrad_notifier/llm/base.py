"""LLM ranking interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from newgrad_notifier.config.settings import CandidateProfile
from newgrad_notifier.contracts import NormalizedJob, RankingResult


class LLMRanker(ABC):
    """Provider interface for structured ranking."""

    @abstractmethod
    def rank(self, profile: CandidateProfile, job: NormalizedJob, heuristic_result: RankingResult) -> RankingResult:
        """Return a validated structured ranking result."""

