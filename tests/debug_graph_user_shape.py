"""
One-off diagnostic: search Microsoft Graph by display name (not by
guessing a UPN/mailNickname format) to see a real user's actual fields,
before deciding how find_user_by_login_hint should match.
"""

import json
import os

os.environ["SHIELD_DRY_RUN"] = "false"

import requests
from config import settings
from connectors.graph_connector import GraphConnector

graph = GraphConnector()
token = graph._get_access_token()

name_fragment = input("Part of the person's real name to search (e.g. Kenzie): ").strip()

resp = requests.get(
    f"{settings.graph_base_url}/users"
    f"?$search=\"displayName:{name_fragment}\""
    f"&$select=displayName,mail,userPrincipalName,mailNickname",
    headers={
        "Authorization": f"Bearer {token}",
        "ConsistencyLevel": "eventual",
    },
    timeout=30,
)
resp.raise_for_status()
matches = resp.json().get("value", [])

print(f"\nFound {len(matches)} match(es):\n")
for m in matches:
    print(json.dumps(m, indent=2))
