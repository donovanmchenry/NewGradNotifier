"""Ranking orchestration with heuristic fallback and optional LLM enrichment."""

from __future__ import annotations

import logging

from newgrad_notifier.config.company_loader import load_company_list
from newgrad_notifier.config.settings import AppSettings
from newgrad_notifier.contracts import NormalizedJob, RankingResult
from newgrad_notifier.ranking.heuristics import build_heuristic_ranking

from newgrad_notifier.llm.base import LLMRanker


class RankingService:
    """Combine deterministic heuristics with optional LLM scoring."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.logger = logging.getLogger(__name__)
        companies = load_company_list(settings.company_coverage.list_path or None)
        self.company_priority = {company["name"].lower(): company.get("priority_tier", 3) for company in companies}
        for company_name in settings.filters.priority_companies:
            self.company_priority[company_name.lower()] = 1
        self.llm_ranker = self._build_llm_ranker(settings)

    def _build_llm_ranker(self, settings: AppSettings) -> LLMRanker | None:
        if not settings.llm.enabled or settings.llm.provider != "openai" or not settings.llm.openai_api_key:
            return None
        from newgrad_notifier.llm.openai_ranker import OpenAIRanker

        return OpenAIRanker(
            api_key=settings.llm.openai_api_key,
            model=settings.llm.model,
            fallback_models=settings.llm.fallback_models,
        )

    def rank(self, job: NormalizedJob) -> RankingResult:
        company_priority = self.company_priority.get(job.company_name.lower(), 3)
        heuristic = build_heuristic_ranking(
            job=job,
            profile=self.settings.candidate_profile,
            company_priority=company_priority,
        )
        if self.llm_ranker is None:
            return heuristic
        try:
            ranking = self.llm_ranker.rank(self.settings.candidate_profile, job, heuristic)
            ranking.scorer = "llm_openai"
            return ranking
        except Exception as exc:  # pragma: no cover - network/provider failures
            self.logger.warning(
                "Falling back to heuristic ranking",
                extra={"context": {"company": job.company_name, "title": job.title, "error": str(exc)}},
            )
            return heuristic
