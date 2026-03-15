"""Prompt builders for ranking jobs."""

from __future__ import annotations

import json

from newgrad_notifier.config.settings import CandidateProfile
from newgrad_notifier.contracts import NormalizedJob, RankingResult


def build_ranking_messages(
    profile: CandidateProfile,
    job: NormalizedJob,
    heuristic_result: RankingResult,
) -> list[dict[str, str]]:
    """Build a conservative scoring prompt that returns strict JSON."""

    system_prompt = """
You score early-career software engineering jobs for a May 2027 computer science student.
Be conservative. Do not inflate fit scores.
Prefer software engineer, full-stack, product engineering, frontend, and backend application roles.
Penalize embedded, firmware, IT support, analyst, pure ML research, or infra/SRE-only roles.
Return JSON only with this exact schema:
{
  "fit_score": int,
  "difficulty_score": int,
  "recommendation": "apply_now|apply_if_interested|low_priority|skip",
  "fit_summary": "string",
  "difficulty_summary": "string",
  "top_matching_skills": ["..."],
  "missing_or_weaker_skills": ["..."],
  "tags": ["..."],
  "scorer": "llm_openai",
  "confidence": float
}
""".strip()

    user_prompt = {
        "candidate_profile": profile.model_dump(),
        "normalized_job": job.model_dump(mode="json"),
        "heuristic_baseline": heuristic_result.model_dump(mode="json"),
        "scoring_rules": {
            "fit": [
                "graduation match",
                "role type match",
                "stack overlap",
                "internship and shipped-product signals",
                "location match",
                "entry-level appropriateness",
                "brand bonus",
            ],
            "difficulty": [
                "employer selectivity",
                "interview difficulty",
                "applicant competition",
                "role ambiguity",
                "prestige/bar",
                "niche requirements mismatch",
            ],
        },
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_prompt)},
    ]

