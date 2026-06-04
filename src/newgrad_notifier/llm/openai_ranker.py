"""OpenAI-backed ranker with strict Pydantic validation."""

from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from newgrad_notifier.config.settings import CandidateProfile
from newgrad_notifier.contracts import NormalizedJob, RankingResult
from newgrad_notifier.llm.base import LLMRanker
from newgrad_notifier.llm.prompts import build_batch_ranking_messages, build_ranking_messages
from newgrad_notifier.llm.schemas import RankingLLMResponse

BATCH_SIZE = 20


class OpenAIRanker(LLMRanker):
    """Structured ranking using an OpenAI chat model."""

    def __init__(
        self,
        api_key: str,
        model: str,
        fallback_models: list[str] | None = None,
        client: Any | None = None,
    ) -> None:
        self.client = client or OpenAI(api_key=api_key)
        self.model = model
        self.fallback_models = [candidate for candidate in fallback_models or [] if candidate and candidate != model]

    @staticmethod
    def _is_model_availability_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return any(
            snippet in message
            for snippet in (
                "does not exist",
                "do not have access",
                "model_not_found",
                "unsupported model",
                "unknown model",
            )
        )

    def rank(self, profile: CandidateProfile, job: NormalizedJob, heuristic_result: RankingResult) -> RankingResult:
        last_error: Exception | None = None
        for candidate_model in [self.model, *self.fallback_models]:
            try:
                response = self.client.chat.completions.create(
                    model=candidate_model,
                    response_format={"type": "json_object"},
                    messages=build_ranking_messages(profile, job, heuristic_result),
                )
                content = response.choices[0].message.content or "{}"
                payload = RankingLLMResponse.model_validate(json.loads(content))
                return payload
            except Exception as exc:
                last_error = exc
                if not self._is_model_availability_error(exc):
                    raise
        if last_error is not None:
            raise last_error
        raise RuntimeError("OpenAI ranker failed before attempting any model.")

    def rank_batch(
        self,
        profile: CandidateProfile,
        jobs: list[tuple[NormalizedJob, RankingResult]],
    ) -> list[RankingResult]:
        """Rank multiple jobs in a single API call, falling back to per-job calls on parse failure."""
        results: list[RankingResult | None] = [None] * len(jobs)
        # Process in chunks of BATCH_SIZE
        for chunk_start in range(0, len(jobs), BATCH_SIZE):
            chunk = jobs[chunk_start : chunk_start + BATCH_SIZE]
            try:
                chunk_results = self._rank_chunk(profile, chunk)
                for i, result in enumerate(chunk_results):
                    results[chunk_start + i] = result
            except Exception:
                # Fall back to per-job calls for this chunk
                for i, (job, heuristic) in enumerate(chunk):
                    try:
                        results[chunk_start + i] = self.rank(profile, job, heuristic)
                    except Exception:
                        results[chunk_start + i] = heuristic
        return [r for r in results if r is not None]

    def _rank_chunk(
        self,
        profile: CandidateProfile,
        chunk: list[tuple[NormalizedJob, RankingResult]],
    ) -> list[RankingResult]:
        last_error: Exception | None = None
        for candidate_model in [self.model, *self.fallback_models]:
            try:
                response = self.client.chat.completions.create(
                    model=candidate_model,
                    response_format={"type": "json_object"},
                    messages=build_batch_ranking_messages(profile, chunk),
                )
                content = response.choices[0].message.content or "{}"
                payload = json.loads(content)
                raw_results = payload.get("results", [])
                # Sort by index to preserve order, then validate each
                raw_results.sort(key=lambda x: x.get("index", 0))
                ranked = []
                for i, item in enumerate(raw_results):
                    item.pop("index", None)
                    try:
                        ranked.append(RankingLLMResponse.model_validate(item))
                    except Exception:
                        # Fall back to heuristic for this individual item
                        ranked.append(chunk[i][1])
                # Pad with heuristics if response was short
                while len(ranked) < len(chunk):
                    ranked.append(chunk[len(ranked)][1])
                return ranked
            except Exception as exc:
                last_error = exc
                if not self._is_model_availability_error(exc):
                    raise
        if last_error is not None:
            raise last_error
        raise RuntimeError("OpenAI ranker chunk failed before attempting any model.")
