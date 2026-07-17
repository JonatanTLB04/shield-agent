"""
Entry point. Run this once per cycle.

While you're piloting, this can just be a scheduled task (Windows Task
Scheduler / cron) that runs `python main.py` once a day. Once you move to
Azure Functions, this same logic becomes the body of a timer-triggered
function — nothing here needs to change, just how it gets invoked.
"""

from datetime import datetime, timezone

from config import settings
from core.orchestrator import Orchestrator


def main():
    print(f"=== SHIELD run started at {datetime.now(timezone.utc).isoformat()} ===")
    print(f"Dry run: {settings.dry_run}")

    if not settings.dry_run:
        if settings.pilot_device_hostnames:
            print(f"Pilot mode: ON — restricted to {list(settings.pilot_device_hostnames)}")
        else:
            print("\n" + "!" * 70)
            print("WARNING: PILOT_DEVICE_HOSTNAMES is empty — SHIELD will act on")
            print("EVERY device Defender reports, not just a test device.")
            print("Set PILOT_DEVICE_HOSTNAMES in .env before running live like this")
            print("unless you've deliberately finished piloting and mean to go wide.")
            print("!" * 70 + "\n")
    print()

    orchestrator = Orchestrator()
    summary = orchestrator.run_daily_cycle()

    print("\n=== Run summary ===")
    for key, value in summary.items():
        print(f"  {key}: {value}")
    print("====================\n")


if __name__ == "__main__":
    main()
