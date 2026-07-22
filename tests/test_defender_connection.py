"""
Standalone connection test for Microsoft Defender for Endpoint.

Proves the Entra ID app registration (certificate auth) works end to
end: authenticates, pulls real devices + recommendations, and looks up
one device by hostname — the same kind of proof-of-life check done for
Datto RMM.

This always hits the real API regardless of SHIELD_DRY_RUN in .env, and
always searches your FULL device fleet regardless of PILOT_DEVICE_HOSTNAMES
in .env — this is a diagnostic tool, not the real production run, so it
shouldn't be limited by whatever pilot device happens to be configured.
Your real main.py run stays correctly restricted either way.

Run with:  python -m tests.test_defender_connection
"""

import os
import sys

os.environ["SHIELD_DRY_RUN"] = "false"
os.environ["PILOT_DEVICE_HOSTNAMES"] = ""

from config import settings  # noqa: E402
from connectors.defender_connector import DefenderConnector  # noqa: E402


def main():
    missing = [
        name for name, value in [
            ("AZURE_TENANT_ID", settings.tenant_id),
            ("AZURE_CLIENT_ID", settings.client_id),
            ("AZURE_CERT_PATH", settings.cert_path),
            ("AZURE_CERT_THUMBPRINT", settings.cert_thumbprint),
        ]
        if not value
    ]
    if missing:
        print("Missing required .env values:", ", ".join(missing))
        sys.exit(1)

    connector = DefenderConnector()

    print("Authenticating with Entra ID (certificate credential)...")
    token = connector._get_access_token()
    print(f"Got a token ({len(token)} chars). Authentication works.\n")

    print("Pulling every exposed device with active recommendations (full fleet, no pilot filter)...")
    exposed = connector.list_exposed_devices_with_recommendations()
    print(f"Found {len(exposed)} device(s) with at least one recommendation.\n")

    hostname = input("Type a hostname to look up (or leave blank to list all device names): ").strip().lower()

    if not hostname:
        print("\nAll device names with at least one recommendation:")
        for device, recs in exposed:
            actionable = [r for r in recs if r.category in ("windows_update", "browser_restart")]
            print(f"  {device.device_name}  —  {len(recs)} total, {len(actionable)} actionable")
        sys.exit(0)

    match = next(
        ((device, recs) for device, recs in exposed if hostname in device.device_name.lower()),
        None,
    )

    if not match:
        print(f"\nNo match for '{hostname}'. Devices found:")
        for device, _ in exposed:
            print(" -", device.device_name)
        sys.exit(1)

    device, recs = match
    print(f"\nFound it — {device.device_name} (device ID: {device.device_id})")
    print(f"{len(recs)} recommendation(s):\n")
    for r in recs:
        flag = " <-- actionable" if r.category in ("windows_update", "browser_restart") else ""
        print(f"  - {r.title}  (category: {r.category}, severity: {r.severity}){flag}")
        if r.cve_ids:
            print(f"    CVEs: {', '.join(r.cve_ids)}")

    print("\nLooking up the logged-on user for this device...")
    user = connector.get_logged_on_user(device.device_id)
    print(f"Logged-on user: {user or 'none found'}")

    print("\nDefender for Endpoint connection confirmed working end to end.")


if __name__ == "__main__":
    main()
