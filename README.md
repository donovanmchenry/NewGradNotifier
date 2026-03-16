# NewGrad Notifier

Production-ready daily discovery, dedupe, ranking, and email notification pipeline for May 2027 software engineering new grad roles.

## Updated Folder Structure

```text
.
├── .github/
│   └── workflows/
│       └── daily-run.yml
├── config/
│   ├── local_dev.toml
│   └── production.toml
├── examples/
│   ├── local_sources/
│   └── sample_daily_digest.txt
├── scripts/
│   ├── restore_sqlite_from_artifact.py
│   └── should_run_schedule.py
├── src/newgrad_notifier/
│   ├── collectors/
│   ├── config/
│   ├── db/
│   ├── dedupe/
│   ├── llm/
│   ├── normalization/
│   ├── notifications/
│   ├── ranking/
│   ├── resume_tailoring/
│   ├── scheduler/
│   ├── utils/
│   ├── cli.py
│   └── pipeline.py
├── tests/
├── .env.example
├── pyproject.toml
└── render.yaml
```

## What This Repo Does

- Collects jobs from:
  - structured early-career sources
  - Greenhouse, Lever, Ashby, Workday, and SmartRecruiters
  - tracked company careers pages
  - general web search
- Filters toward US and remote early-career SWE roles
- Avoids internships, co-ops, IT/support, analyst, hardware, embedded, firmware, QA, and infra-heavy mismatch roles
- Deduplicates across sources by ATS ID, URL, title/company aliases, and content hash
- Stores raw jobs, normalized jobs, scoring, status history, and email digests in SQLite by default
- Uses OpenAI ranking refinement when configured and falls back to heuristics if unavailable
- Sends:
  - a daily digest
  - immediate alerts for very high-fit new roles at `fit_score >= 92`

## Local Setup

1. Create a virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies.

```bash
pip install -e '.[dev]'
python -m playwright install chromium
```

3. Create your env file.

```bash
cp .env.example .env
```

4. Initialize the schema and seed reference data.

```bash
newgrad-notifier --config config/production.toml init-db
```

5. Run locally on demand.

```bash
newgrad-notifier --config config/production.toml run-once
```

6. Run tests.

```bash
pytest
```

## Environment Variables

These are the production env var names expected by the app:

- `EMAIL_RECIPIENT`
- `EMAIL_SENDER`
- `EMAIL_PROVIDER`
- `RESEND_API_KEY`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_TLS`
- `IMMEDIATE_ALERTS_ENABLED`
- `IMMEDIATE_ALERT_THRESHOLD`
- `DB_BACKEND`
- `SQLITE_PATH`
- `DATABASE_URL` for PostgreSQL override
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `OPENAI_FALLBACK_MODELS`
- `RUN_TIME_LOCAL`
- `TIME_ZONE`

GitHub Actions currently pins the OpenAI workflow models directly in the workflow file so stale repository variables cannot override production runs.

See [`.env.example`](.env.example) for the exact quick-start template.

## Resend Setup

This project is now configured for Resend by default.

- Set `EMAIL_PROVIDER=resend`
- Set `RESEND_API_KEY` to your Resend API key
- For initial testing, you can use `EMAIL_SENDER=NewGrad Notifier <onboarding@resend.dev>`

Important:

- Resend limits unverified accounts to sending only to your own address until you verify a custom domain.
- For real production sending, verify a domain in Resend and switch the sender to something like `NewGrad Notifier <jobs@yourdomain.com>`.

## Gmail SMTP Fallback

SMTP still works as a fallback provider.

- Use `smtp.gmail.com`
- Use port `587`
- Use TLS
- Set `SMTP_USERNAME=dzmchenry@gmail.com`
- Set `SMTP_PASSWORD` to a Google App Password

## OpenAI Ranking Behavior

- Production config defaults to `OPENAI_MODEL=gpt-5-mini`
- If the configured model is unavailable to your API key, the ranker automatically retries with `OPENAI_FALLBACK_MODELS` before falling back to heuristics
- If `OPENAI_API_KEY` is not set, the app logs a warning and automatically falls back to heuristic-only scoring
- The pipeline does not crash when OpenAI is unavailable

## Daily Scheduling

The runtime target is:

- `RUN_TIME_LOCAL=08:00`
- `TIME_ZONE=America/New_York`
- scheduled GitHub Actions automation begins on `2026-07-01`

The app derives its cron expression from those values and APScheduler uses the configured timezone directly.

## GitHub Actions Setup

The workflow is in [`.github/workflows/daily-run.yml`](.github/workflows/daily-run.yml).

What it does:

- runs on `workflow_dispatch`
- runs on a UTC schedule twice per day (`12:00` and `13:00` UTC)
- gates execution so the actual run only happens around `08:00` in `America/New_York`
- skips scheduled runs entirely until `2026-07-01`
- restores the last SQLite state artifact if one exists
- runs tests
- runs the production pipeline
- uploads the updated SQLite DB as a GitHub Actions artifact for the next run

### GitHub Actions secrets to add

- `RESEND_API_KEY`
- `OPENAI_API_KEY` (optional but recommended)
- `SMTP_PASSWORD` only if you want SMTP fallback

### GitHub Actions variables to add

You can set these as repository variables, though the workflow already includes sane defaults:

- `EMAIL_RECIPIENT`
- `EMAIL_SENDER`
- `EMAIL_PROVIDER`
- `RESEND_API_KEY` should be stored as a secret, not a variable
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_TLS`
- `IMMEDIATE_ALERTS_ENABLED`
- `IMMEDIATE_ALERT_THRESHOLD`
- `DB_BACKEND`
- `SQLITE_PATH`
- `OPENAI_MODEL`
- `RUN_TIME_LOCAL`
- `TIME_ZONE`

## SQLite Default and Schema Setup

SQLite is the default working backend:

- default path: `./data/newgradnotifier.db`
- created automatically if missing
- schema created via `newgrad-notifier --config config/production.toml init-db`

The SQLAlchemy layer is already shaped so you can switch to PostgreSQL later without changing the application architecture.

## How To Later Switch To Render Postgres

When you are ready to move off SQLite:

1. Provision a Render Postgres database.
2. Set:

```text
DB_BACKEND=postgres
DATABASE_URL=postgresql+psycopg://...
```

3. Keep the same app code and command:

```bash
python -m newgrad_notifier.cli --config config/production.toml run-once
```

No major refactor should be needed because the database access already goes through SQLAlchemy.

## How To Connect The Repo To Render Later

This repo includes a starter [render.yaml](render.yaml) blueprint.

Typical next steps:

1. Push the repo to GitHub.
2. In Render, create a new Blueprint or Cron Job from the repo.
3. Point Render at `render.yaml`.
4. Add environment variables:
   - Resend settings
   - `OPENAI_API_KEY`
   - later `DATABASE_URL` from Render Postgres
5. Deploy and verify the first run from Render logs.

For long-term production, Render Postgres is the better persistence option than SQLite-on-runner.

## Local Fixture Mode

Use the fixture config to test the full pipeline without live sources:

```bash
newgrad-notifier --config config/local_dev.toml run-once
```

Fixture inputs live in [`examples/local_sources/`](examples/local_sources/).

## Sample Output Email

See [`examples/sample_daily_digest.txt`](examples/sample_daily_digest.txt).

## Tests

The test suite covers:

- config loading and validation
- dedupe behavior
- ranking and LLM fallback behavior
- email rendering
- filtering behavior
- core collector parsing paths

Run:

```bash
pytest
```
