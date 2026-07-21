"""Ranking orchestration with heuristic fallback and optional LLM enrichment."""

from __future__ import annotations

import logging

from newgrad_notifier.config.company_loader import load_company_list
from newgrad_notifier.config.settings import AppSettings
from newgrad_notifier.contracts import NormalizedJob, RankingResult
from newgrad_notifier.ranking.feedback import FeedbackSignals
from newgrad_notifier.ranking.heuristics import build_heuristic_ranking, recommend

from newgrad_notifier.llm.base import LLMRanker

# Only send jobs above this heuristic score to the LLM — skips obvious mismatches
LLM_PREFILTER_SCORE = 50


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
        self.feedback_signals = FeedbackSignals()

    def set_feedback_signals(self, signals: FeedbackSignals) -> None:
        self.feedback_signals = signals

    def _build_llm_ranker(self, settings: AppSettings) -> LLMRanker | None:
        if not settings.llm.enabled or settings.llm.provider != "openai" or not settings.llm.openai_api_key:
            return None
        from newgrad_notifier.llm.openai_ranker import OpenAIRanker

        return OpenAIRanker(
            api_key=settings.llm.openai_api_key,
            model=settings.llm.model,
            fallback_models=settings.llm.fallback_models,
        )

    def _heuristic(self, job: NormalizedJob) -> RankingResult:
        company_priority = self.company_priority.get(job.company_name.lower(), 3)
        ranking = build_heuristic_ranking(
            job=job,
            profile=self.settings.candidate_profile,
            company_priority=company_priority,
        )
        return self._apply_feedback(job, ranking)

    def _apply_feedback(self, job: NormalizedJob, ranking: RankingResult) -> RankingResult:
        adjustment = self.feedback_signals.adjustment(job, ranking)
        if adjustment == 0:
            return ranking
        fit_score = max(0, min(100, ranking.fit_score + adjustment))
        tags = sorted(set([*ranking.tags, "feedback_adjusted"]))
        return ranking.model_copy(
            update={
                "fit_score": fit_score,
                "recommendation": recommend(
                    fit_score,
                    ranking.difficulty_score,
                    f"{job.title} {job.description_text}".lower(),
                ),
                "tags": tags,
            }
        )

    def rank(self, job: NormalizedJob) -> RankingResult:
        heuristic = self._heuristic(job)
        if self.llm_ranker is None or heuristic.fit_score < LLM_PREFILTER_SCORE:
            return heuristic
        try:
            ranking = self.llm_ranker.rank(self.settings.candidate_profile, job, heuristic)
            ranking.scorer = "llm_openai"
            return self._apply_feedback(job, ranking)
        except Exception as exc:  # pragma: no cover - network/provider failures
            self.logger.warning(
                "Falling back to heuristic ranking",
                extra={"context": {"company": job.company_name, "title": job.title, "error": str(exc)}},
            )
            return heuristic

    def rank_all(self, jobs: list[NormalizedJob]) -> list[RankingResult]:
        """Rank all jobs, using batched LLM calls only for jobs above the heuristic threshold."""
        heuristics = [self._heuristic(job) for job in jobs]
        if self.llm_ranker is None:
            return heuristics

        # Identify jobs that warrant LLM scoring
        llm_indices = [i for i, h in enumerate(heuristics) if h.fit_score >= LLM_PREFILTER_SCORE]
        if not llm_indices:
            return heuristics

        llm_inputs = [(jobs[i], heuristics[i]) for i in llm_indices]
        self.logger.info(
            "Batch LLM ranking",
            extra={"context": {"total_jobs": len(jobs), "llm_candidates": len(llm_inputs)}},
        )
        try:
            llm_results = self.llm_ranker.rank_batch(self.settings.candidate_profile, llm_inputs)
            for idx, result in zip(llm_indices, llm_results):
                result.scorer = "llm_openai"
                heuristics[idx] = self._apply_feedback(jobs[idx], result)
        except Exception as exc:  # pragma: no cover - network/provider failures
            self.logger.warning(
                "Batch LLM ranking failed, using heuristics for all",
                extra={"context": {"error": str(exc)}},
            )
        return heuristics
