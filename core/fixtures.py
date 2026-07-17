"""
Fixture data used only in dry-run mode (SHIELD_DRY_RUN=true, the default).

This exists so you can see the entire agent working end-to-end — polling,
mapping, drafting messages, "sending" email, rechecking, escalating —
before any of the real credentials from stages 1-7 of the rollout plan
exist yet. Nothing here touches a real API.

The shapes below mirror what the real APIs actually return, so switching
off dry-run later doesn't require any changes to the orchestrator logic.
"""

import random
import uuid

from core.models import ExposedDevice, Recommendation

_FAKE_DEVICES = [
    ("device-001", "LAPTOP-JPEREZ", "jperez@yourcompany.com"),
    ("device-002", "LAPTOP-MGARCIA", "mgarcia@yourcompany.com"),
    ("device-003", "LAPTOP-ARUIZ", "aruiz@yourcompany.com"),
]

_FAKE_RECOMMENDATIONS = [
    {
        "recommendation_id": "rec-chrome-01",
        "device_id": "device-001",
        "title": "Update Google Chrome to version 141.0.7390.54",
        "category": "browser_restart",
        "severity": "High",
        "cve_ids": ["CVE-2026-31790"],
        "affected_software": "Google Chrome",
    },
    {
        "recommendation_id": "rec-windows-01",
        "device_id": "device-002",
        "title": "Restart Windows to finish installing pending updates",
        "category": "windows_update",
        "severity": "Medium",
        "cve_ids": [],
        "affected_software": "Windows 11",
    },
    {
        "recommendation_id": "rec-openssl-01",
        "device_id": "device-003",
        "title": "Update OpenSSL to a patched version",
        "category": "app_update",
        "severity": "Critical",
        "cve_ids": ["CVE-2026-31789"],
        "affected_software": "Oracle OpenSSL",
    },
]


def fake_exposed_devices_with_recommendations() -> list[tuple[ExposedDevice, list[Recommendation]]]:
    by_device: dict[str, list[Recommendation]] = {}
    for r in _FAKE_RECOMMENDATIONS:
        rec = Recommendation(
            recommendation_id=r["recommendation_id"],
            device_id=r["device_id"],
            title=r["title"],
            category=r["category"],
            severity=r["severity"],
            cve_ids=r["cve_ids"],
            affected_software=r["affected_software"],
        )
        by_device.setdefault(r["device_id"], []).append(rec)

    results = []
    for device_id, device_name, _ in _FAKE_DEVICES:
        if device_id in by_device:
            results.append(
                (ExposedDevice(device_id=device_id, device_name=device_name), by_device[device_id])
            )
    return results


def fake_logged_on_user(device_id: str) -> str | None:
    for did, _, upn in _FAKE_DEVICES:
        if did == device_id:
            return upn
    return None


def fake_user_profile(user_upn: str) -> dict:
    name = user_upn.split("@")[0].replace(".", " ").title()
    return {"displayName": name, "mail": user_upn, "department": "Operations"}


def fake_installed_version(device_uid: str, software_name: str) -> str:
    """
    Randomly simulates the device having already been fixed roughly a third
    of the time, so a dry run shows you both the "resolved" path and the
    "still pending" path without any manual setup.
    """
    if random.random() < 0.35:
        return "141.0.7390.54"  # pretend it's already patched
    return "139.0.7100.10"       # pretend it's still the old, vulnerable version


def fake_patch_status(device_uid: str) -> dict:
    return {"patchStatus": random.choice(["Fully Patched", "Pending Reboot", "Missing Patches"])}


def fake_job_id() -> str:
    return str(uuid.uuid4())
