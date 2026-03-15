"""Greenhouse ATS collector."""

from __future__ import annotations

from newgrad_notifier.collectors.ats.base import ATSBoardCollector
from newgrad_notifier.collectors.base import CollectorContext
from newgrad_notifier.config.settings import ATSBoardConfig
from newgrad_notifier.contracts import CollectedJob


class GreenhouseCollector(ATSBoardCollector):
    platform = "greenhouse"

    def collect_board(self, board: ATSBoardConfig, context: CollectorContext) -> list[CollectedJob]:
        api_url = board.api_url or f"https://boards-api.greenhouse.io/v1/boards/{board.identifier}/jobs?content=true"
        payload = context.http_client.get_json(api_url)
        jobs: list[CollectedJob] = []
        for item in payload.get("jobs", []):
            job = self.build_job(
                board=board,
                source_url=api_url,
                apply_url=item.get("absolute_url") or item.get("url") or board.careers_url or api_url,
                company_name=board.company_name,
                title=item.get("title", ""),
                external_job_id=str(item.get("id", "")) or None,
                location_text=(item.get("location") or {}).get("name") if isinstance(item.get("location"), dict) else None,
                posted_at=item.get("updated_at"),
                description_text=item.get("content"),
                metadata={"ats_platform": self.platform},
                context=context,
            )
            if job:
                jobs.append(job)
        return jobs

