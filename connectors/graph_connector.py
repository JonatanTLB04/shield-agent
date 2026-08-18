"""
Connector for Microsoft Graph — used for three things:
  1. Resolving a device's logged-on user into a full profile (name, email).
  2. Fallback: resolving a bare Windows login name (from Datto RMM, when
     Defender's own lookup is empty) into that same full profile, by
     display-name search rather than guessing a UPN format.
  3. Sending the notification email.

Requires application permissions User.Read.All and Mail.Send, granted with
admin consent. Uses the same certificate credential as the Defender
connector (same app registration is fine, or a separate one — see the
architecture doc's note on keeping blast radius separated).
"""

import re
import time

import requests
import msal

from config import settings
from core import fixtures


class GraphConnector:
    def __init__(self):
        self._token = None
        self._token_expires_at = 0

    def _get_access_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        authority = f"https://login.microsoftonline.com/{settings.tenant_id}"
        app = msal.ConfidentialClientApplication(
            client_id=settings.client_id,
            authority=authority,
            client_credential={
                "private_key": open(settings.cert_path).read(),
                "thumbprint": settings.cert_thumbprint,
            },
        )
        result = app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )
        if "access_token" not in result:
            raise RuntimeError(f"Failed to get Graph token: {result.get('error_description')}")

        self._token = result["access_token"]
        self._token_expires_at = time.time() + result.get("expires_in", 3600)
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json",
        }

    def get_user_profile(self, user_upn: str) -> dict:
        """Returns displayName, mail, and department for a user. Needs an
        exact, full UPN or email — this does not search or guess."""
        if settings.dry_run:
            return fixtures.fake_user_profile(user_upn)

        resp = requests.get(
            f"{settings.graph_base_url}/users/{user_upn}"
            f"?$select=displayName,mail,department",
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def find_user_by_login_hint(self, login_hint: str) -> dict | None:
        """
        Fallback resolution for a bare Windows login name (e.g.
        "KenzieNasser", from Datto RMM's lastLoggedInUser) into a real
        Graph profile.

        Confirmed against a real account on 2026-07-17: the local Windows
        login name does not reliably match the real userPrincipalName
        format ("KenzieNasser" locally vs. the real UPN
        "kenzie.nasser@thelaunchbox.com", dot-separated). So instead of
        guessing a UPN/mailNickname pattern, this splits the PascalCase
        login hint into separate words ("Kenzie", "Nasser") and searches
        by display name instead — confirmed to work via a live test.

        Known limitation: this word-split heuristic can misfire on names
        that don't split cleanly into two simple capitalized words (e.g.
        a last name like "McDonald", or names with three or more parts).
        Good enough as a fallback, not perfect — if it ever returns the
        wrong person or no one, that's worth a manual look rather than
        assuming it always works.
        """
        if settings.dry_run:
            return fixtures.fake_user_profile(login_hint)

        # "KenzieNasser" -> "Kenzie Nasser"
        name_guess = re.sub(r'(?<!^)(?=[A-Z])', ' ', login_hint).strip()

        resp = requests.get(
            f"{settings.graph_base_url}/users"
            f'?$search="displayName:{name_guess}"'
            f"&$select=displayName,mail,department,userPrincipalName",
            headers={**self._headers(), "ConsistencyLevel": "eventual"},
            timeout=30,
        )
        resp.raise_for_status()
        matches = resp.json().get("value", [])
        return matches[0] if matches else None


    def find_user_by_device_hostname(self, hostname: str) -> dict | None:
        """
        Resolves a device hostname to a user via Intune (Microsoft Graph).
        Used when Defender and Datto RMM both fail to identify the owner.
        Queries /deviceManagement/managedDevices and returns the primaryUser.
        """
        if settings.dry_run:
            return None
        import urllib.parse
        filter_q = urllib.parse.quote(f"deviceName eq '{hostname}'")
        resp = requests.get(
            f"{settings.graph_base_url}/deviceManagement/managedDevices"
            f"?$filter=deviceName eq '{hostname}'"
            f"&$select=deviceName,userPrincipalName,userDisplayName,emailAddress",
            headers=self._headers(),
            timeout=30,
        )
        if not resp.ok:
            return None
        devices = resp.json().get("value", [])
        if not devices:
            return None
        device = devices[0]
        upn = device.get("userPrincipalName") or device.get("emailAddress")
        if not upn:
            return None
        return {
            "userPrincipalName": upn,
            "displayName": device.get("userDisplayName", upn.split("@")[0]),
            "mail": upn,
        }
    def send_mail(self, to_address: str, subject: str, body_html: str) -> None:
        if settings.dry_run:
            print(f"\n[DRY RUN] Would send email")
            print(f"  To:      {to_address}")
            print(f"  Subject: {subject}")
            print(f"  Body:\n{body_html}\n")
            return

        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "HTML", "content": body_html},
                "toRecipients": [{"emailAddress": {"address": to_address}}],
            },
            "saveToSentItems": "true",
        }
        resp = requests.post(
            f"{settings.graph_base_url}/users/{settings.sender_mailbox}/sendMail",
            headers=self._headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
