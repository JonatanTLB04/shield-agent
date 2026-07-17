"""
Connector for Microsoft Graph — used for two things only:
  1. Resolving a device's logged-on user into a full profile (name, email).
  2. Sending the notification email.

Requires application permissions User.Read.All and Mail.Send, granted with
admin consent. Uses the same certificate credential as the Defender
connector (same app registration is fine, or a separate one — see the
architecture doc's note on keeping blast radius separated).
"""

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
        """Returns displayName, mail, and department for a user."""
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
