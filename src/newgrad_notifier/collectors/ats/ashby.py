"""Ashby ATS collector."""

from __future__ import annotations

from typing import Any

from newgrad_notifier.collectors.ats.base import ATSBoardCollector
from newgrad_notifier.collectors.base import CollectorContext
from newgrad_notifier.config.settings import ATSBoardConfig
from newgrad_notifier.contracts import CollectedJob


class AshbyCollector(ATSBoardCollector):
    platform = "ashby"

    def collect_board(self, board: ATSBoardConfig, context: CollectorContext) -> list[CollectedJob]:
        source_url = board.api_url or (
            f"https://api.ashbyhq.com/posting-api/job-board/{board.identifier}"
        )
        if board.api_url:
            payload = context.http_client.get_json(board.api_url)
        else:
            payload = context.http_client.get_json(source_url)
        if payload.get("errors"):
            raise ValueError(f"Ashby returned an error for {board.identifier}: {payload['errors']}")
        jobs_payload = self._extract_jobs(payload)
        self.last_total_available = len(jobs_payload)
        jobs: list[CollectedJob] = []
        for item in jobs_payload:
            job = self.build_job(
                board=board,
                source_url=source_url,
                apply_url=item.get("applyUrl") or item.get("jobUrl") or board.careers_url or "",
                company_name=board.company_name,
                title=item.get("title", ""),
                external_job_id=str(item.get("id", "")) or None,
                location_text=item.get("locationName") or item.get("location"),
                posted_at=item.get("publishedDate") or item.get("publishedAt"),
                description_text=item.get("descriptionHtml") or "",
                employment_type=item.get("employmentType"),
                metadata={"ats_platform": self.platform},
                context=context,
            )
            if job:
                jobs.append(job)
        return jobs

    def _extract_jobs(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        if "jobs" in payload:
            return payload.get("jobs", [])
        return payload.get("data", {}).get("jobsBoard", {}).get("jobs", [])
