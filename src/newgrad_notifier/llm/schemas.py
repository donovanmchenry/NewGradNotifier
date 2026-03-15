"""Structured output schema for LLM ranking."""

from __future__ import annotations

from newgrad_notifier.contracts import RankingResult


class RankingLLMResponse(RankingResult):
    """Structured JSON contract required from the LLM."""

