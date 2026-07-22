"""
One-off diagnostic: print the full raw device record from Datto RMM's
/api/v2/account/devices endpoint, so we can see exactly what user/contact/
email fields actually exist before building a lookup on top of an
assumption — same approach used to fix the Defender recommendation parsing.
"""

import json
import os

os.environ["SHIELD_DRY_RUN"] = "false"

import requests
from config import settings
from connectors.datto_connector import DattoConnector

connector = DattoConnector()
token = connector._get_access_token()

hostname = input("Hostname to inspect (e.g. kenzie or trestons_laptop): ").strip()

resp = requests.get(
    f"{settings.datto_api_url}/api/v2/account/devices",
    headers={"Authorization": f"Bearer {token}"},
    params={"hostname": hostname},
    timeout=30,
)
resp.raise_for_status()
devices = resp.json().get("devices", [])

match = next((d for d in devices if d.get("hostname", "").lower() == hostname.lower()), None)

if not match:
    print(f"No exact match for '{hostname}'. Raw hostnames returned:")
    for d in devices:
        print(" -", d.get("hostname"))
else:
    print(f"\nFull raw record for {hostname}:\n")
    print(json.dumps(match, indent=2))
