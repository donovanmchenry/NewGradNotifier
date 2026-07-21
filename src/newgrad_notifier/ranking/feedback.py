"""Learn lightweight ranking preferences from application decisions."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from newgrad_notifier.contracts import NormalizedJob, RankingResult


@dataclass(slots=True)
class FeedbackSignals:
    sample_count: int = 0
    company_weights: Counter[str] = field(default_factory=Counter)
    tag_weights: Counter[str] = field(default_factory=Counter)
    skill_weights: Counter[str] = field(default_factory=Counter)
    work_mode_weights: Counter[str] = field(default_factory=Counter)

    def observe(
        self,
        *,
        positive: bool,
        company_name: str,
        tags: list[str],
        skills: list[str],
        work_mode: str | None,
    ) -> None:
        weight = 1 if positive else -1
        self.sample_count += 1
        self.company_weights[company_name.lower()] += weight
        self.tag_weights.update({tag: weight for tag in tags})
        self.skill_weights.update({skill: weight for skill in skills})
        if work_mode and work_mode != "Not specified":
            self.work_mode_weights[work_mode] += weight

    def adjustment(self, job: NormalizedJob, ranking: RankingResult) -> int:
        if self.sample_count < 3:
            return 0
        details = job.metadata.get("job_details", {})
        raw = self.company_weights[job.company_name.lower()] * 2
        raw += sum(self.tag_weights[tag] for tag in ranking.tags)
        raw += sum(self.skill_weights[skill] for skill in ranking.top_matching_skills)
        work_mode = details.get("work_mode")
        if work_mode:
            raw += self.work_mode_weights[work_mode]
        return max(-10, min(10, raw))
