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
└── pyproject.toml
```

## What This Repo Does

- Collects jobs from:
  - the ApplyGuy 2027 and Simplify machine-readable feeds
  - the SpeedyApply 2027 U.S. new-grad list
  - 46 curated Greenhouse, Lever, and Ashby boards
  - tracked company careers pages
  - optional general web search
- Filters toward US and remote early-career SWE roles
- Avoids internships, co-ops, IT/support, analyst, hardware, embedded, firmware, QA, and infra-heavy mismatch roles
- Deduplicates across runs and sources by normalized application URL and ATS requisition ID
- Stores raw jobs, normalized jobs, scoring, status history, and email digests in SQLite by default
- Uses personalized, no-cost heuristic ranking in production; OpenAI refinement remains an opt-in local feature
- Sends:
  - a daily digest capped to the best 8 new or reopened matches
  - immediate alerts for very high-fit new roles at `fit_score >= 92`
- Enriches a bounded set of sparse listings from their direct application pages
- Avoids rescoring or re-emailing jobs that were already seen
- Extracts salary, work mode, sponsorship, citizenship/clearance, graduation year, and application deadlines
- Tracks per-source health, including failed and repeatedly empty ATS boards
- Includes an optional local tracking dashboard and feedback learner, disabled in the free production deployment
- Suppresses empty digests and sends an independent failure alert when a run breaks

## Local Setup

1. Create a virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies.

```bash
pip install -r requirements.lock
pip install -e . --no-deps
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

7. Run the local application tracker when tracking is configured.

```bash
newgrad-notifier --config config/production.toml serve-tracker
```

## Environment Variables

These are the environment variable names supported by the app. The free GitHub workflow uses the email, scheduling, and SQLite values; OpenAI, PostgreSQL, and tracking remain optional and disabled.

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
- `OPENAI_ENABLED` (`false` provides a no-cost heuristic-only kill switch)
- `OPENAI_MODEL`
- `OPENAI_FALLBACK_MODELS`
- `RUN_TIME_LOCAL`
- `TIME_ZONE`
- `SEND_EMPTY_DIGEST` (defaults to `false`)
- `FAILURE_ALERTS_ENABLED`
- `TRACKING_ENABLED`
- `TRACKING_BASE_URL`
- `TRACKING_SECRET`
- `TRACKING_DASHBOARD_USERNAME`
- `TRACKING_DASHBOARD_PASSWORD`
- `TRACKING_HOST`
- `TRACKING_PORT`

The free production workflow pins SQLite and disables hosted tracking so it cannot provision or depend on paid infrastructure.

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

- Production runs in no-cost heuristic mode by default (`OPENAI_ENABLED=false`).
- OpenAI ranking is opt-in for local experimentation; if enabled, unavailable models retry through `OPENAI_FALLBACK_MODELS` before falling back to heuristics.
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
- restores persisted state before deciding whether the local day already ran
- tolerates delayed cron delivery and runs only once after `08:00` in `America/New_York`
- skips scheduled runs entirely until `2026-07-01`
- restores the last SQLite state artifact if one exists
- fails closed instead of running with empty state when restoration fails
- runs a production configuration and SQLite preflight
- runs the production pipeline
- uploads the updated SQLite DB as a GitHub Actions artifact for the next run
- sends an independent Resend failure alert if the workflow fails
- uses only GitHub Actions and its persisted SQLite artifact; no Render services are provisioned

The separate CI workflow runs the complete test suite on every push and pull request using the locked dependency set in `requirements.lock`.

### GitHub Actions secrets to add

- `RESEND_API_KEY`
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
- `OPENAI_MODEL`
- `OPENAI_ENABLED`
- `RUN_TIME_LOCAL`
- `TIME_ZONE`
- `SCHEDULE_ENABLED` (`false` disables scheduled runs but keeps manual dispatch available)
- `SEND_EMPTY_DIGEST`
- `FAILURE_ALERTS_ENABLED`

## SQLite Default and Schema Setup

SQLite is the default working backend:

- default path: `./data/newgradnotifier.db`
- created automatically if missing
- schema created via `newgrad-notifier --config config/production.toml init-db`

The production workflow deliberately locks this to SQLite and restores the latest database artifact on every run. PostgreSQL support remains in the application for a possible future migration, but it is not enabled or provisioned.

## Optional Local Application Tracking

Tracking links are disabled in the free production workflow. The dashboard can still be tested locally without purchasing hosting.

Required settings:

```text
TRACKING_ENABLED=true
TRACKING_BASE_URL=https://your-tracker.example.com
TRACKING_SECRET=<random secret shared by the tracker and daily runner>
TRACKING_DASHBOARD_USERNAME=donovan
TRACKING_DASHBOARD_PASSWORD=<strong password>
```

When deliberately enabled against a reachable deployment, email includes Save, Mark applied, and Not interested links. Links open a confirmation page instead of changing state immediately, which protects against automated email link scanners.

After at least three decisions, ranking receives a bounded adjustment of at most ten points based on companies, role tags, matching skills, and work mode. The original heuristic and OpenAI scoring remain the primary signals.

The dashboard root uses HTTP Basic authentication. Individual email links use an HMAC signature and expose only the referenced job. No hosted dashboard, database, or cron service is included in the free deployment.

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
