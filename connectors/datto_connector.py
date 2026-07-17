"""
Connector for Datto RMM.

Two jobs, matching the design we settled on:
  1. Verify: pull the *live* installed version / patch status for a device,
     independent of Defender's own (slower) refresh cycle.
  2. Remediate: trigger a Quick Job to run a remediation script directly,
     for the things that are safe to fix silently (e.g. relaunching a
     browser process) without needing the user to do anything.

Requires API access enabled on the Datto RMM account (Setup > Global
Settings > Access Control) and an API Key/Secret generated for a user.
"""

import time

import requests

from config import settings
from core import fixtures


class DattoConnector:
    def __init__(self):
        self._token = None
        self._token_expires_at = 0

    # ------------------------------------------------------------------ #
    # Auth — Datto RMM uses OAuth 2.0, tokens last 100 hours
    # ------------------------------------------------------------------ #
    def _get_access_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 300:
            return self._token

        resp = requests.post(
            f"{settings.datto_api_url}/auth/oauth/token",
            data={
                "grant_type": "password",
                "username": settings.datto_api_key,
                "password": settings.datto_api_secret,
            },
            auth=("public-client", "public"),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        # Datto tokens are valid for 100 hours; refresh a bit early regardless.
        self._token_expires_at = time.time() + data.get("expires_in", 360000)
        return self._token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._get_access_token()}"}

    # ------------------------------------------------------------------ #
    # Device matching
    # ------------------------------------------------------------------ #
    def find_device_uid_by_hostname(self, hostname: str) -> str | None:
        """
        Defender's device ID and Datto RMM's device UID are different values
        from different systems — hostname is the one thing both track, so
        that's what we match on. Returns None if the device isn't onboarded
        to Datto RMM yet (expected during a partial migration — not an error).
        """
        if settings.dry_run:
            return fixtures.fake_datto_device_uid(hostname)

        resp = requests.get(
            f"{settings.datto_api_url}/api/v2/account/devices",
            headers=self._headers(),
            params={"hostname": hostname},
            timeout=30,
        )
        resp.raise_for_status()
        devices = resp.json().get("devices", [])
        for d in devices:
            if d.get("hostname", "").lower() == hostname.lower():
                return d.get("uid")
        return None  # Not migrated to Datto RMM yet — caller must handle this.

    # ------------------------------------------------------------------ #
    # Verification
    # ------------------------------------------------------------------ #
    def get_installed_version(self, hostname: str, software_name: str) -> str | None:
        """
        Returns the currently installed version of a given piece of software
        on a device, straight from Datto RMM's live audit data — this is
        the fast, independent check that doesn't wait on Defender's own
        24-48 hour catch-up. Returns None if the device isn't in Datto RMM
        yet — the orchestrator falls back to Defender's own next poll for
        those, rather than treating this as an error.
        """
        device_uid = self.find_device_uid_by_hostname(hostname)
        if device_uid is None:
            return None

        if settings.dry_run:
            return fixtures.fake_installed_version(device_uid, software_name)

        resp = requests.get(
            f"{settings.datto_api_url}/api/v2/audit/device/{device_uid}/software",
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        for item in resp.json().get("softwareEntries", []):
            if software_name.lower() in item.get("name", "").lower():
                return item.get("version")
        return None

    def get_patch_status(self, hostname: str) -> dict | None:
        """Returns the device's current Windows patch status, or None if
        the device isn't in Datto RMM yet."""
        device_uid = self.find_device_uid_by_hostname(hostname)
        if device_uid is None:
            return None

        if settings.dry_run:
            return fixtures.fake_patch_status(device_uid)

        resp = requests.get(
            f"{settings.datto_api_url}/api/v2/audit/device/{device_uid}",
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("patchManagement", {})

    # ------------------------------------------------------------------ #
    # Remediation
    # ------------------------------------------------------------------ #
    def run_quick_job(self, device_uid: str, component_uid: str, variables: dict | None = None) -> str:
        """
        Triggers an immediate Quick Job on a device.

        Reminder from the architecture doc: Quick Jobs always run as
        NT AUTHORITY\\SYSTEM — fully silent, no way to prompt the user.
        Never use this for anything that requires a forced reboot; those
        should notify the user instead and let them choose the timing.
        Expect 10-30 minutes of real-world latency before it executes.
        """
        if settings.dry_run:
            return fixtures.fake_job_id()

        resp = requests.post(
            f"{settings.datto_api_url}/api/v2/device/{device_uid}/quickjob",
            headers=self._headers(),
            json={
                "componentUid": component_uid,
                "variables": variables or {},
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("jobUid", "")
