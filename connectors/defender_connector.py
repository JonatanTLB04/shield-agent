"""
Connector for Microsoft Defender for Endpoint.

Talks to the native Defender for Endpoint API (not the Graph Security API —
see the architecture document for why: several recommendation/vulnerability
endpoints still live here as of mid-2026). Requires an Entra ID app
registration with a certificate credential and the following application
permissions granted with admin consent:

    Machine.Read.All
    SecurityRecommendation.Read.All
    Vulnerability.Read.All
    Software.Read.All
    User.Read.All  (Defender-scoped, for logged-on-user lookups)
"""

import time

import requests
import msal

from config import settings
from core.models import ExposedDevice, Recommendation
from core import fixtures


class DefenderConnector:
    def __init__(self):
        self._token = None
        self._token_expires_at = 0

    # ------------------------------------------------------------------ #
    # Auth
    # ------------------------------------------------------------------ #
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
        # NOTE: token is requested against the legacy resource audience —
        # this is required by several Defender for Endpoint endpoints even
        # when calling the newer api.security.microsoft.com base URL.
        result = app.acquire_token_for_client(
            scopes=[f"{settings.defender_token_resource}/.default"]
        )
        if "access_token" not in result:
            raise RuntimeError(f"Failed to get Defender token: {result.get('error_description')}")

        self._token = result["access_token"]
        self._token_expires_at = time.time() + result.get("expires_in", 3600)
        return self._token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._get_access_token()}"}

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def list_exposed_devices_with_recommendations(self) -> list[tuple[ExposedDevice, list[Recommendation]]]:
        """
        Returns every device that has at least one active recommendation,
        paired with that device's recommendations. This is the single
        entry point the orchestrator calls once per daily cycle.

        Calls the per-device endpoint (GET /api/machines/{id}/recommendations)
        once per machine, since the bulk /api/recommendations endpoint only
        returns aggregate counts, never a per-device list.
        """
        if settings.dry_run:
            return fixtures.fake_exposed_devices_with_recommendations()

        results = []
        machines = self._list_machines()

        # One API call per machine now instead of one call total, so during
        # the pilot, skip anything outside the approved device list rather
        # than querying every machine and throwing most of it away.
        if settings.pilot_device_hostnames:
            machines = [
                m for m in machines
                if m.get("computerDnsName") in settings.pilot_device_hostnames
            ]

        for raw_machine in machines:
            device_id = raw_machine.get("id")
            if not device_id:
                continue

            raw_recs = self._list_recommendations_for_device(device_id)
            if not raw_recs:
                continue

            recs = [
                Recommendation(
                    recommendation_id=r.get("id", ""),
                    device_id=device_id,
                    title=r.get("recommendationName", "Unknown recommendation"),
                    category=_categorize(r),
                    severity=r.get("severityScore", "Medium"),
                    cve_ids=r.get("relatedCves", []) or [],
                    affected_software=r.get("productName", ""),
                )
                for r in raw_recs
            ]

            device = ExposedDevice(device_id=device_id, device_name=raw_machine.get("computerDnsName", device_id))
            results.append((device, recs))

        return results

    def get_logged_on_user(self, device_id: str) -> str | None:
        """Best-effort lookup of the primary/most-recent logged-on user."""
        if settings.dry_run:
            return fixtures.fake_logged_on_user(device_id)

        resp = requests.get(
            f"{settings.defender_base_url}/api/machines/{device_id}/logonusers",
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        users = resp.json().get("value", [])
        if not users:
            return None
        # Defender returns multiple; the most recently seen one is the best guess.
        return users[0].get("userPrincipalName") or users[0].get("accountName")

    # ------------------------------------------------------------------ #
    # Internal calls
    # ------------------------------------------------------------------ #
    def _list_machines(self) -> list[dict]:
        resp = requests.get(
            f"{settings.defender_base_url}/api/machines",
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("value", [])

    def _list_recommendations_for_device(self, device_id: str) -> list[dict]:
        resp = requests.get(
            f"{settings.defender_base_url}/api/machines/{device_id}/recommendations",
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("value", [])


def _categorize(raw_recommendation: dict) -> str:
    """
    Maps Defender's own remediation type/title into SHIELD's internal
    category, which is what picks the message template and decides
    whether a Datto RMM script exists for it. Extend this as you cover
    more recommendation types.

    FIXED 2026-07-17: matching on "chrome"/"edge" alone was too broad —
    it caught config/hardening settings that happen to mention the browser
    by name (e.g. "Disable 'Continue running background apps when Google
    Chrome is closed'"), not just genuine pending updates. Now requires an
    update/restart word alongside the browser name, same rule already used
    for Windows below.
    """
    name = (raw_recommendation.get("recommendationName") or "").lower()
    rtype = (raw_recommendation.get("remediationType") or "").lower()

    if ("chrome" in name or "edge" in name) and ("update" in name or "restart" in name):
        return "browser_restart"
    if "windows" in name and ("update" in name or "restart" in name):
        return "windows_update"
    if rtype == "software_update" or "update" in name:
        return "app_update"
    if "config" in rtype or "configuration" in name:
        return "config"
    return "unknown"
