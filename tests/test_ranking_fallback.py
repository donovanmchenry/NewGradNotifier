from newgrad_notifier.config.settings import load_settings
from newgrad_notifier.contracts import CollectedJob, Recommendation, SourceType
from newgrad_notifier.llm.openai_ranker import OpenAIRanker
from newgrad_notifier.llm.schemas import RankingLLMResponse
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


class _FakeOpenAIClient:
    def __init__(self) -> None:
        self.attempted_models: list[str] = []
        self.beta = self
        self.chat = self
        self.completions = self

    def parse(self, *, model, response_format, messages):
        self.attempted_models.append(model)
        if model == "gpt-5-mini":
            raise RuntimeError("The model 'gpt-5-mini' does not exist or you do not have access to it.")

        class _Message:
            parsed = RankingLLMResponse(
                fit_score=78,
                difficulty_score=63,
                recommendation=Recommendation.APPLY_IF_INTERESTED,
                fit_summary="Strong stack overlap.",
                difficulty_summary="Competitive but reasonable.",
                top_matching_skills=["React", "TypeScript"],
                missing_or_weaker_skills=["Java"],
                tags=["frontend", "new_grad"],
            )

        class _Choice:
            message = _Message()

        class _Response:
            choices = [_Choice()]

        return _Response()


def test_openai_ranker_retries_with_fallback_model():
    settings = load_settings("config/local_dev.toml")
    job = normalize_job(
        CollectedJob(
            source_name="simplify_fixture",
            source_type=SourceType.STRUCTURED,
            source_url="examples/local_sources/simplify_jobs.json",
            apply_url="https://boards.greenhouse.io/figma/jobs/12345",
            company_name="Figma",
            title="Software Engineer, New Grad 2027",
            location_text="Remote, United States",
            description_text="Class of 2027 software engineer role building React, TypeScript, Node.js, Python, and APIs.",
        )
    )
    heuristic = RankingService(settings).rank(job)
    client = _FakeOpenAIClient()
    ranker = OpenAIRanker(
        api_key="test-key",
        model="gpt-5-mini",
        fallback_models=["gpt-4.1-mini"],
        client=client,
    )

    result = ranker.rank(settings.candidate_profile, job, heuristic)

    assert client.attempted_models == ["gpt-5-mini", "gpt-4.1-mini"]
    assert result.fit_score == 78
