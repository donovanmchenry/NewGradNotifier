"""Structured output schemas for LLM ranking."""

from __future__ import annotations

from pydantic import BaseModel

from newgrad_notifier.contracts import RankingResult


class RankingLLMResponse(RankingResult):
    """Structured output contract for a single job ranking."""


class BatchRankingItem(RankingLLMResponse):
    """Single item within a batch ranking response; index maps back to the input array."""

    index: int


class BatchRankingResponse(BaseModel):
    """Wrapper returned by the LLM when scoring a batch of jobs."""

    results: list[BatchRankingItem]
