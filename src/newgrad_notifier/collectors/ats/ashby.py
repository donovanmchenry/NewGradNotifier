"""Ashby ATS collector."""

from __future__ import annotations

from typing import Any

from newgrad_notifier.collectors.ats.base import ATSBoardCollector
from newgrad_notifier.collectors.base import CollectorContext
from newgrad_notifier.config.settings import ATSBoardConfig
from newgrad_notifier.contracts import CollectedJob


ASHBY_QUERY = """
query ApiJobsBoardWithTeams($organizationHostedJobsPageName: String!) {
  jobsBoard: jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) {
    jobs {
      id
      title
      locationName
      publishedDate
      applyUrl
      descriptionHtml
      employmentType
    }
  }
}
"""


class AshbyCollector(ATSBoardCollector):
    platform = "ashby"

    def collect_board(self, board: ATSBoardConfig, context: CollectorContext) -> list[CollectedJob]:
        if board.api_url:
            payload = context.http_client.get_json(board.api_url)
        else:
            payload = context.http_client.get_json(
                "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobsBoardWithTeams",
                method="POST",
                json_body={
                    "operationName": "ApiJobsBoardWithTeams",
                    "query": ASHBY_QUERY,
                    "variables": {"organizationHostedJobsPageName": board.identifier},
                },
            )
        jobs_payload = self._extract_jobs(payload)
        self.last_total_available = len(jobs_payload)
        jobs: list[CollectedJob] = []
        for item in jobs_payload:
            job = self.build_job(
                board=board,
                source_url=board.api_url or "https://jobs.ashbyhq.com",
                apply_url=item.get("applyUrl") or board.careers_url or "",
                company_name=board.company_name,
                title=item.get("title", ""),
                external_job_id=str(item.get("id", "")) or None,
                location_text=item.get("locationName"),
                posted_at=item.get("publishedDate"),
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
