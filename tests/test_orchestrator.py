"""
A simple smoke test — proves the full daily cycle runs cleanly end to end
using the built-in dry-run fixtures, the same way you'd test a Datto RMM
script against your own machine before pushing it to everyone else.

Run with:  python -m tests.test_orchestrator
"""

import os

os.environ["SHIELD_DRY_RUN"] = "true"
os.environ["PILOT_DEVICE_HOSTNAMES"] = ""  # this test always checks unrestricted fixture logic

from config import settings  # noqa: E402
from core.orchestrator import Orchestrator  # noqa: E402


def test_full_cycle_runs_without_errors():
    # Start from a clean slate regardless of any previous `python main.py`
    # runs in this same folder — otherwise this test would see findings
    # already tracked from earlier runs and (correctly) report 0 new ones.
    if os.path.exists(settings.state_db_path):
        os.remove(settings.state_db_path)

    orchestrator = Orchestrator()

    # First run: should pick up all fixture findings as new.
    summary_1 = orchestrator.run_daily_cycle()
    assert summary_1["new_findings"] == 3
    assert summary_1["on_hold_no_fix"] == 1  # the fake OpenSSL finding
    assert summary_1["notified"] == 2

    # Second run, same day: nothing new, nothing due for recheck yet.
    summary_2 = orchestrator.run_daily_cycle()
    assert summary_2["new_findings"] == 0
    assert summary_2["resolved"] == 0
    assert summary_2["reminded"] == 0

    print("All assertions passed.")
    print("Run 1:", summary_1)
    print("Run 2:", summary_2)


if __name__ == "__main__":
    test_full_cycle_runs_without_errors()
