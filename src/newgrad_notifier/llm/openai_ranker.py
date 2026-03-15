"""OpenAI-backed ranker with strict Pydantic validation."""

from __future__ import annotations

import json

from openai import OpenAI

from newgrad_notifier.config.settings import CandidateProfile
from newgrad_notifier.contracts import NormalizedJob, RankingResult
from newgrad_notifier.llm.base import LLMRanker
from newgrad_notifier.llm.prompts import build_ranking_messages
from newgrad_notifier.llm.schemas import RankingLLMResponse


class OpenAIRanker(LLMRanker):
    """Structured ranking using an OpenAI chat model."""

    def __init__(self, api_key: str, model: str) -> None:
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def rank(self, profile: CandidateProfile, job: NormalizedJob, heuristic_result: RankingResult) -> RankingResult:
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=build_ranking_messages(profile, job, heuristic_result),
        )
        content = response.choices[0].message.content or "{}"
        payload = RankingLLMResponse.model_validate(json.loads(content))
        return payload

