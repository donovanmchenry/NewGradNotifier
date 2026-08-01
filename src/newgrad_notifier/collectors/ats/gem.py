"""Gem ATS collector."""

from __future__ import annotations

from typing import Any

from newgrad_notifier.collectors.ats.base import ATSBoardCollector
from newgrad_notifier.collectors.base import CollectorContext
from newgrad_notifier.config.settings import ATSBoardConfig
from newgrad_notifier.contracts import CollectedJob


GEM_QUERY = """
query JobBoardList($boardId: String!) {
  oatsExternalJobPostings(boardId: $boardId) {
    jobPostings {
      id
      extId
      title
      locations {
        name
        city
        isoCountry
        isRemote
      }
      job {
        locationType
        employmentType
      }
    }
  }
}
"""


class GemCollector(ATSBoardCollector):
    platform = "gem"

    def collect_board(self, board: ATSBoardConfig, context: CollectorContext) -> list[CollectedJob]:
        source_url = board.careers_url or f"https://jobs.gem.com/{board.identifier}"
        api_url = board.api_url or "https://jobs.gem.com/api/public/graphql"
        payload = context.http_client.get_json(
            api_url,
            method="POST",
            json_body={
                "query": GEM_QUERY,
                "variables": {"boardId": board.identifier},
            },
        )
        if payload.get("errors"):
            raise ValueError(f"Gem returned an error for {board.identifier}: {payload['errors']}")

        postings = payload.get("data", {}).get("oatsExternalJobPostings", {}).get("jobPostings", [])
        self.last_total_available = len(postings)
        jobs: list[CollectedJob] = []
        for item in postings:
            external_id = str(item.get("extId") or item.get("id") or "")
            job_details = item.get("job") or {}
            job = self.build_job(
                board=board,
                source_url=source_url,
                apply_url=f"https://jobs.gem.com/{board.identifier}/{external_id}",
                company_name=board.company_name,
                title=item.get("title", ""),
                external_job_id=external_id or None,
                location_text=self._location_text(item),
                employment_type=job_details.get("employmentType"),
                metadata={"ats_platform": self.platform},
                context=context,
            )
            if job:
                jobs.append(job)
        return jobs

    @staticmethod
    def _location_text(item: dict[str, Any]) -> str | None:
        locations = item.get("locations") or []
        names = [
            str(location.get("name") or location.get("city") or "").strip()
            for location in locations
        ]
        names = list(dict.fromkeys(name for name in names if name))
        location_type = str((item.get("job") or {}).get("locationType") or "").upper()
        if location_type == "REMOTE" and not any("remote" in name.lower() for name in names):
            names.insert(0, "Remote")
        return ", ".join(names) or None
