from newgrad_notifier.config.settings import load_settings
from newgrad_notifier.contracts import CollectedJob, SourceType
from newgrad_notifier.normalization.normalizer import normalize_job
from newgrad_notifier.ranking.service import RankingService


class BrokenLLMRanker:
    def rank(self, profile, job, heuristic_result):
        raise RuntimeError("provider unavailable")


def test_ranking_falls_back_to_heuristics_when_llm_fails():
    settings = load_settings("config/local_dev.toml")
    service = RankingService(settings)
    service.llm_ranker = BrokenLLMRanker()
    job = normalize_job(
        CollectedJob(
            source_name="simplify_fixture",
            source_type=SourceType.STRUCTURED,
            source_url="examples/local_sources/simplify_jobs.json",
            apply_url="https://boards.greenhouse.io/figma/jobs/12345",
            company_name="Figma",
            title="Software Engineer, New Grad 2027",
            location_text="Remote, United States",
            description_text="Class of 2027 software engineer role building React, TypeScript, Node.js, Python, and APIs for a product team.",
        )
    )

    result = service.rank(job)

    assert result.scorer == "heuristic"
    assert result.fit_score >= 65
