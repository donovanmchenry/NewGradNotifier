"""Workday ATS collector."""

from __future__ import annotations

from typing import Any

from newgrad_notifier.collectors.ats.base import ATSBoardCollector
from newgrad_notifier.collectors.base import CollectorContext
from newgrad_notifier.config.settings import ATSBoardConfig
from newgrad_notifier.contracts import CollectedJob


class WorkdayCollector(ATSBoardCollector):
    platform = "workday"

    def collect_board(self, board: ATSBoardConfig, context: CollectorContext) -> list[CollectedJob]:
        if not board.api_url:
            self.last_total_available = 0
            return []
        payload = context.http_client.get_json(board.api_url)
        jobs_payload = self._extract_jobs(payload)
        self.last_total_available = len(jobs_payload)
        jobs: list[CollectedJob] = []
        for item in jobs_payload:
            title = item.get("title") or item.get("bulletFields", [None])[0] or ""
            location = item.get("locationsText") or item.get("location") or None
            job = self.build_job(
                board=board,
                source_url=board.api_url,
                apply_url=item.get("externalPath") or item.get("applyUrl") or board.careers_url or board.api_url,
                company_name=board.company_name,
                title=title,
                external_job_id=str(item.get("bulletFields", [None, None])[1] or item.get("id", "")) or None,
                location_text=location,
                posted_at=item.get("postedOn") or item.get("postedDate"),
                description_text=item.get("description", ""),
                metadata={"ats_platform": self.platform},
                context=context,
            )
            if job:
                jobs.append(job)
        return jobs

    def _extract_jobs(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        if "jobPostings" in payload:
            return payload["jobPostings"]
        if "jobs" in payload:
            return payload["jobs"]
        return payload.get("data", [])
