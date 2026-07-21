from newgrad_notifier.config.settings import load_settings
from newgrad_notifier.contracts import CollectedJob, SourceType
from newgrad_notifier.normalization.normalizer import normalize_job
from newgrad_notifier.ranking.feedback import FeedbackSignals
from newgrad_notifier.ranking.service import RankingService


def test_feedback_signals_adjust_rankings_after_three_decisions():
    settings = load_settings("config/local_dev.toml")
    service = RankingService(settings)
    signals = FeedbackSignals()
    for _ in range(3):
        signals.observe(
            positive=True,
            company_name="Example",
            tags=["full_stack"],
            skills=["Python"],
            work_mode="Remote",
        )
    service.set_feedback_signals(signals)
    job = normalize_job(
        CollectedJob(
            source_name="fixture",
            source_type=SourceType.STRUCTURED,
            source_url="fixture.json",
            apply_url="https://example.com/job",
            company_name="Example",
            title="Full-Stack Software Engineer, New Grad 2027",
            location_text="Remote, United States",
            description_text="Build a full-stack Python product for customers.",
        )
    )

    baseline_service = RankingService(settings)
    assert service.rank(job).fit_score > baseline_service.rank(job).fit_score
