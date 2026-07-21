"""ATS collection orchestration."""

from __future__ import annotations

import logging

from newgrad_notifier.collectors.ats.ashby import AshbyCollector
from newgrad_notifier.collectors.ats.base import ATSBoardCollector
from newgrad_notifier.collectors.ats.greenhouse import GreenhouseCollector
from newgrad_notifier.collectors.ats.lever import LeverCollector
from newgrad_notifier.collectors.ats.smartrecruiters import SmartRecruitersCollector
from newgrad_notifier.collectors.ats.workday import WorkdayCollector
from newgrad_notifier.collectors.base import Collector, CollectorContext
from newgrad_notifier.config.settings import ATSBoardConfig
from newgrad_notifier.contracts import CollectedJob, PipelineError


class ATSCollectorService(Collector):
    """Collect from configured ATS boards."""

    name = "ats"

    def __init__(self, boards: list[ATSBoardConfig]) -> None:
        self.boards = [board for board in boards if board.enabled]
        self.platform_collectors: dict[str, ATSBoardCollector] = {
            "ashby": AshbyCollector(),
            "greenhouse": GreenhouseCollector(),
            "lever": LeverCollector(),
            "smartrecruiters": SmartRecruitersCollector(),
            "workday": WorkdayCollector(),
        }
        self.logger = logging.getLogger(__name__)
        self.errors: list[PipelineError] = []
        self.source_health: dict[str, dict[str, object]] = {}

    def collect(self, context: CollectorContext) -> list[CollectedJob]:
        jobs: list[CollectedJob] = []
        self.errors = []
        self.source_health = {}
        for board in self.boards:
            source_name = f"{board.platform}:{board.company_name}"
            collector = self.platform_collectors.get(board.platform.lower())
            if collector is None:
                context.logger.warning("Skipping unsupported ATS platform", extra={"context": {"platform": board.platform}})
                self.source_health[source_name] = {
                    "status": "unsupported",
                    "total_available": None,
                    "relevant_jobs": 0,
                }
                continue
            try:
                board_jobs = collector.collect_board(board, context)
                jobs.extend(board_jobs)
                self.source_health[source_name] = {
                    "status": "healthy",
                    "total_available": collector.last_total_available,
                    "relevant_jobs": len(board_jobs),
                }
            except Exception as exc:
                self.source_health[source_name] = {
                    "status": "failed",
                    "total_available": None,
                    "relevant_jobs": 0,
                    "error": str(exc),
                }
                self.errors.append(
                    PipelineError(
                        source_name=source_name,
                        stage="collect",
                        message="ATS board failed",
                        detail=str(exc),
                    )
                )
                self.logger.warning(
                    "Discovered ATS board failed",
                    extra={"context": {"company": board.company_name, "platform": board.platform, "identifier": board.identifier, "error": str(exc)}},
                )
        return jobs[: context.settings.collection.max_jobs_per_source]
