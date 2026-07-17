"""
One-off diagnostic: print the raw shape of a single Defender recommendation
so we can fix the parsing in defender_connector.py based on what the API
actually returns, instead of guessing.
"""

import json
import os

os.environ["SHIELD_DRY_RUN"] = "false"

import requests
from config import settings
from connectors.defender_connector import DefenderConnector

connector = DefenderConnector()
token = connector._get_access_token()

resp = requests.get(
    f"{settings.defender_base_url}/api/recommendations",
    headers={"Authorization": f"Bearer {token}"},
    timeout=30,
)
resp.raise_for_status()
recs = resp.json().get("value", [])

print(f"Total recommendations: {len(recs)}\n")
print("First raw recommendation, full structure:\n")
print(json.dumps(recs[0], indent=2))
