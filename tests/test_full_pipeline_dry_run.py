"""
Full pipeline test against a real device (Kenzie) — exercises every fix
from today together: real Defender parsing, real categorization, the
not_actionable gate, the Datto RMM + Graph user-resolution fallback, and
a real combined Claude draft covering all of her actionable findings.

SAFETY: this script never calls graph.send_mail() anywhere — not gated by
a flag, simply not present in this file. The drafted email is only
printed. Uses a separate, disposable state database so it doesn't touch
your real production tracking data.

Run with:  python -m tests.test_full_pipeline_dry_run
"""

import os

os.environ["SHIELD_DRY_RUN"] = "false"              # real Defender/Datto/Graph reads
os.environ["PILOT_DEVICE_HOSTNAMES"] = ""            # search the full fleet, not just karlaoros
os.environ["STATE_DB_PATH"] = "test_pilot_run.db"    # disposable, not the real one

from config import settings  # noqa: E402
from core.orchestrator import Orchestrator, NOTIFIABLE_CATEGORIES, _has_no_available_fix  # noqa: E402
from core.models import Finding  # noqa: E402

TARGET_HOSTNAME = "kenzie"


def main():
    if os.path.exists(settings.state_db_path):
        os.remove(settings.state_db_path)

    orch = Orchestrator()

    print(f"Pulling real recommendations for '{TARGET_HOSTNAME}' from Defender...")
    exposed = orch.defender.list_exposed_devices_with_recommendations()
    match = next((dr for dr in exposed if TARGET_HOSTNAME.lower() in dr[0].device_name.lower()), None)

    if not match:
        print(f"'{TARGET_HOSTNAME}' not found among exposed devices.")
        return

    device, recommendations = match
    print(f"Found {device.device_name}: {len(recommendations)} total recommendations.\n")

    print("Resolving the device's user (Defender first, then Datto RMM + Graph fallback)...")
    user_upn = orch._resolve_user(device)
    print(f"Resolved user: {user_upn or 'NONE FOUND'}\n")

    if not user_upn:
        print("No user resolved — stopping here, nothing further to test.")
        return

    on_hold = 0
    not_actionable = 0
    actionable = []

    for rec in recommendations:
        if _has_no_available_fix(rec):
            on_hold += 1
            continue
        if rec.category not in NOTIFIABLE_CATEGORIES:
            not_actionable += 1
            continue
        actionable.append(
            Finding(
                device_id=device.device_id,
                recommendation_id=rec.recommendation_id,
                device_name=device.device_name,
                user_upn=user_upn,
                title=rec.title,
                category=rec.category,
                severity=rec.severity,
            )
        )

    print(f"Gate results out of {len(recommendations)} total:")
    print(f"  {on_hold} on-hold (no fix available yet)")
    print(f"  {not_actionable} not actionable (policy/config settings, no restart involved)")
    print(f"  {len(actionable)} actionable — these are what would go into the email\n")

    if not actionable:
        print("Nothing actionable — no email would be drafted.")
        return

    print(f"Drafting ONE combined email for {len(actionable)} actionable finding(s)...\n")
    profile = orch.graph.get_user_profile(user_upn)
    subject, body = orch.claude.draft_notification(profile["displayName"], actionable)

    print("=" * 70)
    print(f"WOULD SEND TO: {profile.get('mail')}")
    print(f"SUBJECT: {subject}")
    print("BODY:")
    print(body)
    print("=" * 70)
    print("\nNothing was actually sent — send_mail() does not appear anywhere in this script.")

    if os.path.exists(settings.state_db_path):
        os.remove(settings.state_db_path)


if __name__ == "__main__":
    main()
