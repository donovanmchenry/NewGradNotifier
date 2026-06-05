"""OpenAI-backed ranker using Structured Outputs."""

from __future__ import annotations

from typing import Any

from openai import OpenAI

from newgrad_notifier.config.settings import CandidateProfile
from newgrad_notifier.contracts import NormalizedJob, RankingResult
from newgrad_notifier.llm.base import LLMRanker
from newgrad_notifier.llm.prompts import build_batch_ranking_messages, build_ranking_messages
from newgrad_notifier.llm.schemas import BatchRankingResponse, RankingLLMResponse

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
        self.fallback_models = [m for m in fallback_models or [] if m and m != model]

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
                response = self.client.beta.chat.completions.parse(
                    model=candidate_model,
                    response_format=RankingLLMResponse,
                    messages=build_ranking_messages(profile, job, heuristic_result),
                )
                parsed = response.choices[0].message.parsed
                if parsed is None:
                    raise RuntimeError("Structured output returned None")
                return parsed
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
        """Rank multiple jobs in a single API call, falling back to per-job calls on chunk failure."""
        results: list[RankingResult | None] = [None] * len(jobs)
        for chunk_start in range(0, len(jobs), BATCH_SIZE):
            chunk = jobs[chunk_start : chunk_start + BATCH_SIZE]
            try:
                chunk_results = self._rank_chunk(profile, chunk)
                for i, result in enumerate(chunk_results):
                    results[chunk_start + i] = result
            except Exception:
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
                response = self.client.beta.chat.completions.parse(
                    model=candidate_model,
                    response_format=BatchRankingResponse,
                    messages=build_batch_ranking_messages(profile, chunk),
                )
                parsed = response.choices[0].message.parsed
                if parsed is None:
                    raise RuntimeError("Structured output returned None")
                result_map = {item.index: item for item in parsed.results}
                ranked: list[RankingResult] = []
                for i, (_, heuristic) in enumerate(chunk):
                    item = result_map.get(i)
                    if item is not None:
                        ranked.append(RankingLLMResponse.model_validate(item.model_dump(exclude={"index"})))
                    else:
                        ranked.append(heuristic)
                return ranked
            except Exception as exc:
                last_error = exc
                if not self._is_model_availability_error(exc):
                    raise
        if last_error is not None:
            raise last_error
        raise RuntimeError("OpenAI ranker chunk failed before attempting any model.")
