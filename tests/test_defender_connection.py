"""
Standalone connection test for Microsoft Defender for Endpoint.

Proves the Entra ID app registration (certificate auth) works end to
end: authenticates, pulls real devices + recommendations, and looks up
one device by hostname — the same kind of proof-of-life check done for
Datto RMM.

This always hits the real API regardless of SHIELD_DRY_RUN in .env —
same behavior as test_datto_connection.py.

Run with:  python -m tests.test_defender_connection
"""

import os
import sys

os.environ["SHIELD_DRY_RUN"] = "false"

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

    print("Pulling every exposed device with active recommendations...")
    exposed = connector.list_exposed_devices_with_recommendations()
    print(f"Found {len(exposed)} device(s) with at least one recommendation.\n")

    hostname = input("Type the hostname to look up (e.g. karlaoros): ").strip().lower()

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
        print(f"  - {r.title}  (category: {r.category}, severity: {r.severity})")
        if r.cve_ids:
            print(f"    CVEs: {', '.join(r.cve_ids)}")

    print("\nLooking up the logged-on user for this device...")
    user = connector.get_logged_on_user(device.device_id)
    print(f"Logged-on user: {user or 'none found'}")

    print("\nDefender for Endpoint connection confirmed working end to end.")


if __name__ == "__main__":
    main()
