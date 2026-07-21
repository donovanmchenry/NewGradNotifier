from newgrad_notifier.pipeline import run_pipeline_once


def test_two_pipeline_runs_only_digest_jobs_once(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("EMAIL_PROVIDER", "console")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "pipeline.db"))

    run_pipeline_once("config/local_dev.toml")
    first_output = capsys.readouterr().out
    run_pipeline_once("config/local_dev.toml")
    second_output = capsys.readouterr().out

    assert "jobs worth a look" in first_output
    assert second_output == ""
    assert "Apply: https://boards.greenhouse.io/figma/jobs/12345" not in second_output
