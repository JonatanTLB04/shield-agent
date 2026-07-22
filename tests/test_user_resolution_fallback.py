"""
Standalone test for the Datto RMM -> Graph user-resolution fallback,
end to end, against a real device. Proves the exact chain the
orchestrator now uses: Defender lookup (expected empty) -> Datto RMM
lastLoggedInUser -> Graph search -> real profile.

Run with:  python -m tests.test_user_resolution_fallback
"""

import os

os.environ["SHIELD_DRY_RUN"] = "false"
os.environ["PILOT_DEVICE_HOSTNAMES"] = ""

from connectors.defender_connector import DefenderConnector  # noqa: E402
from connectors.datto_connector import DattoConnector  # noqa: E402
from connectors.graph_connector import GraphConnector  # noqa: E402


def main():
    hostname = input("Hostname to test (e.g. kenzie): ").strip()

    defender = DefenderConnector()
    datto = DattoConnector()
    graph = GraphConnector()

    print(f"\nFinding {hostname}'s device ID via Defender...")
    exposed = defender.list_exposed_devices_with_recommendations()
    match = next((d for d, _ in exposed if hostname.lower() in d.device_name.lower()), None)
    if not match:
        print(f"'{hostname}' not found in Defender's exposed device list.")
        return

    print(f"Found: {match.device_name} (device ID: {match.device_id})")

    print("\nStep 1 — Defender's own logged-on-user lookup:")
    defender_result = defender.get_logged_on_user(match.device_id)
    print(f"  -> {defender_result or 'None (empty, as expected)'}")

    print("\nStep 2 — Datto RMM's lastLoggedInUser (fallback source):")
    login_hint = datto.get_last_logged_in_user_hint(match.device_name)
    print(f"  -> {login_hint or 'None'}")

    if not login_hint:
        print("\nNo login hint available from Datto RMM either — chain stops here.")
        return

    print(f"\nStep 3 — Resolving '{login_hint}' against Microsoft Graph...")
    profile = graph.find_user_by_login_hint(login_hint)
    if not profile:
        print("  -> No matching Graph user found.")
        return

    print(f"  -> Match found:")
    print(f"     Display name: {profile.get('displayName')}")
    print(f"     Email:        {profile.get('mail')}")
    print(f"     UPN:          {profile.get('userPrincipalName')}")
    print(f"     Department:   {profile.get('department')}")

    print("\nFull fallback chain confirmed working end to end.")


if __name__ == "__main__":
    main()
