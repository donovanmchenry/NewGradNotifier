"""Gate GitHub Actions schedule triggers to 8:00 AM in the configured local timezone."""

from __future__ import annotations

import os
from datetime import date, datetime
from zoneinfo import ZoneInfo


def main() -> int:
    timezone_name = os.getenv("TIME_ZONE", "America/New_York")
    run_time_local = os.getenv("RUN_TIME_LOCAL", "08:00")
    start_date_text = os.getenv("SCHEDULE_START_DATE", "")
    target_hour, target_minute = [int(part) for part in run_time_local.split(":", maxsplit=1)]
    now = datetime.now(ZoneInfo(timezone_name))
    if start_date_text:
        start_date = date.fromisoformat(start_date_text)
        if now.date() < start_date:
            print(f"Scheduled automation starts on {start_date.isoformat()}; skipping this trigger.")
            return 1
    minute_delta = abs((now.hour * 60 + now.minute) - (target_hour * 60 + target_minute))
    print(f"Current local time in {timezone_name}: {now.isoformat()}")
    if minute_delta <= 20:
        print("Within the scheduled execution window.")
        return 0
    print("Outside the scheduled execution window; skipping this trigger.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
