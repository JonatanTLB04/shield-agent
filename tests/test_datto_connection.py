"""
Standalone Datto RMM connection test.

Tests ONLY the Datto RMM connection — not Defender, not Graph, not the
full agent. If your API key/secret/URL are misconfigured, this tells you
immediately, without having to debug the whole pipeline at once.

This script ignores SHIELD_DRY_RUN and always makes a real API call,
since the whole point is to test the real connection.

Run with:  python -m tests.test_datto_connection
"""

import os

os.environ["SHIELD_DRY_RUN"] = "false"  # this script always tests for real

from config import settings  # noqa: E402
from connectors.datto_connector import DattoConnector  # noqa: E402


def main():
    print("=== Testing Datto RMM connection ===\n")

    if not settings.datto_api_url or not settings.datto_api_key or not settings.datto_api_secret:
        print("STOP: One or more Datto settings are empty in your .env file.")
        print(f"  DATTO_API_URL set?    {'yes' if settings.datto_api_url else 'NO - missing'}")
        print(f"  DATTO_API_KEY set?    {'yes' if settings.datto_api_key else 'NO - missing'}")
        print(f"  DATTO_API_SECRET set? {'yes' if settings.datto_api_secret else 'NO - missing'}")
        print("\nFill these in and run this script again.")
        return

    datto = DattoConnector()

    print("Step 1: Authenticating...")
    try:
        token = datto._get_access_token()
        print(f"  Success — got a token ({len(token)} characters).\n")
    except Exception as e:
        print(f"  FAILED to authenticate.\n  Error: {e}\n")
        print("  Common causes: wrong API URL, wrong key/secret, or API")
        print("  access got turned off again in Datto RMM's Access Control settings.")
        return

    print("Step 2: Looking up a device by hostname...")
    hostname = input("  Type the exact hostname of any real device in Datto RMM, then press Enter: ").strip()

    try:
        device_uid = datto.find_device_uid_by_hostname(hostname)
    except Exception as e:
        print(f"  FAILED while searching for the device.\n  Error: {e}\n")
        return

    if device_uid is None:
        print(f"  No device found with hostname '{hostname}'.")
        print("  This could mean: the hostname is slightly different than what you typed,")
        print("  or that device genuinely isn't onboarded to Datto RMM yet.")
        return

    print(f"  Found it — device UID: {device_uid}\n")

    print("Step 3: Pulling live software list for that device...")
    try:
        chrome_version = datto.get_installed_version(hostname, "Chrome")
        print(f"  Chrome version found: {chrome_version or '(not installed, or not found by that name)'}")
    except Exception as e:
        print(f"  FAILED while pulling software data.\n  Error: {e}\n")
        return

    print("\n=== All good — the real Datto RMM connection works. ===")


if __name__ == "__main__":
    main()
