"""Command line interface for initialization, runs, and scheduling."""

from __future__ import annotations

import argparse

from newgrad_notifier.config.settings import load_settings
from newgrad_notifier.db.seeding import seed_reference_data
from newgrad_notifier.db.session import init_db
from newgrad_notifier.pipeline import run_pipeline_once


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""

    parser = argparse.ArgumentParser(description="Daily new-grad job discovery and ranking pipeline.")
    parser.add_argument("--config", dest="config_path", default=None, help="Path to a TOML config override.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create the configured database schema.")
    subparsers.add_parser("run-once", help="Run discovery, ranking, and digest generation once.")
    subparsers.add_parser("schedule", help="Run the APScheduler service.")
    return parser


def main() -> None:
    """CLI entrypoint."""

    parser = build_parser()
    args = parser.parse_args()

    if args.command == "init-db":
        settings = load_settings(args.config_path)
        init_db(settings)
        from newgrad_notifier.db.session import create_session_factory

        session_factory = create_session_factory(settings)
        with session_factory() as session:
            seed_reference_data(session, settings)
        return
    if args.command == "run-once":
        run_pipeline_once(args.config_path)
        return
    if args.command == "schedule":
        from newgrad_notifier.scheduler.apscheduler_runner import run_scheduler

        run_scheduler(args.config_path)
        return


if __name__ == "__main__":
    main()
