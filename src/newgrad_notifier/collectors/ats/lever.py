"""Lever ATS collector."""

from __future__ import annotations

from newgrad_notifier.collectors.ats.base import ATSBoardCollector
from newgrad_notifier.collectors.base import CollectorContext
from newgrad_notifier.config.settings import ATSBoardConfig
from newgrad_notifier.contracts import CollectedJob


class LeverCollector(ATSBoardCollector):
    platform = "lever"

    def collect_board(self, board: ATSBoardConfig, context: CollectorContext) -> list[CollectedJob]:
        api_url = board.api_url or f"https://api.lever.co/v0/postings/{board.identifier}?mode=json"
        payload = context.http_client.get_json(api_url)
        jobs: list[CollectedJob] = []
        for item in payload:
            categories = item.get("categories", {})
            location = categories.get("location") if isinstance(categories, dict) else None
            description = item.get("descriptionPlain") or item.get("description") or ""
            job = self.build_job(
                board=board,
                source_url=api_url,
                apply_url=item.get("hostedUrl") or item.get("applyUrl") or board.careers_url or api_url,
                company_name=board.company_name,
                title=item.get("text", ""),
                external_job_id=str(item.get("id", "")) or None,
                location_text=location,
                posted_at=item.get("createdAt"),
                description_text=description,
                metadata={"ats_platform": self.platform},
                context=context,
            )
            if job:
                jobs.append(job)
        return jobs

