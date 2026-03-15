"""OpenAI-backed ranker with strict Pydantic validation."""

from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from newgrad_notifier.config.settings import CandidateProfile
from newgrad_notifier.contracts import NormalizedJob, RankingResult
from newgrad_notifier.llm.base import LLMRanker
from newgrad_notifier.llm.prompts import build_ranking_messages
from newgrad_notifier.llm.schemas import RankingLLMResponse


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
                    temperature=0.2,
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
