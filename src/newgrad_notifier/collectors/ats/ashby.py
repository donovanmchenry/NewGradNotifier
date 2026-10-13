"""Ashby ATS collector."""

from __future__ import annotations

from typing import Any

from newgrad_notifier.collectors.ats.base import ATSBoardCollector
from newgrad_notifier.collectors.base import CollectorContext
from newgrad_notifier.config.settings import ATSBoardConfig
from newgrad_notifier.contracts import CollectedJob
from newgrad_notifier.utils.http import CachedHttpClient


class AshbyCollector(ATSBoardCollector):
    platform = "ashby"

    def collect_board(self, board: ATSBoardConfig, context: CollectorContext) -> list[CollectedJob]:
        source_url, jobs_payload = self.fetch_board(board, context.http_client)
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

    def fetch_board(
        self, board: ATSBoardConfig, client: CachedHttpClient, *, use_cache: bool = True,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Fetch raw postings for either strict discovery or a broader company watch."""
        source_url = board.api_url or f"https://api.ashbyhq.com/posting-api/job-board/{board.identifier}"
        payload = client.get_json(source_url, use_cache=use_cache)
        if not isinstance(payload, dict):
            raise ValueError(f"Ashby returned an invalid response for {board.identifier}")
        if payload.get("errors"):
            raise ValueError(f"Ashby returned an error for {board.identifier}: {payload['errors']}")
        if "jobs" not in payload and "jobs" not in payload.get("data", {}).get("jobsBoard", {}):
            raise ValueError(f"Ashby response is missing jobs for {board.identifier}")
        jobs = self._extract_jobs(payload)
        if not isinstance(jobs, list) or any(not isinstance(job, dict) for job in jobs):
            raise ValueError("Ashby jobs must be a list of postings")
        return source_url, jobs

    def _extract_jobs(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        if "jobs" in payload:
            return payload.get("jobs", [])
        return payload.get("data", {}).get("jobsBoard", {}).get("jobs", [])
