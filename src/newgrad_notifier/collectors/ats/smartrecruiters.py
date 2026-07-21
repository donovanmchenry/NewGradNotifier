"""SmartRecruiters ATS collector."""

from __future__ import annotations

from newgrad_notifier.collectors.ats.base import ATSBoardCollector
from newgrad_notifier.collectors.base import CollectorContext
from newgrad_notifier.config.settings import ATSBoardConfig
from newgrad_notifier.contracts import CollectedJob


class SmartRecruitersCollector(ATSBoardCollector):
    platform = "smartrecruiters"

    def collect_board(self, board: ATSBoardConfig, context: CollectorContext) -> list[CollectedJob]:
        api_url = board.api_url or f"https://api.smartrecruiters.com/v1/companies/{board.identifier}/postings"
        payload = context.http_client.get_json(api_url)
        self.last_total_available = len(payload.get("content", []))
        jobs: list[CollectedJob] = []
        for item in payload.get("content", []):
            location = ", ".join(
                part for part in [item.get("location", {}).get("city"), item.get("location", {}).get("region")] if part
            )
            job = self.build_job(
                board=board,
                source_url=api_url,
                apply_url=item.get("ref") or board.careers_url or api_url,
                company_name=board.company_name,
                title=item.get("name", ""),
                external_job_id=str(item.get("id", "")) or None,
                location_text=location or None,
                posted_at=item.get("releasedDate"),
                description_text=item.get("jobAd", {}).get("sections", {}).get("jobDescription", {}).get("text", ""),
                metadata={"ats_platform": self.platform},
                context=context,
            )
            if job:
                jobs.append(job)
        return jobs
