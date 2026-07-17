"""
Shared data models for SHIELD.

Every connector (Defender, Datto RMM, Graph) normalizes its own vendor-specific
response shape into these plain, simple objects. The rest of the agent only
ever works with these — this is what keeps the orchestrator connector-agnostic,
so adding Intune or Entra ID risk signals later is a new connector, not a
rewrite of the core logic.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ExposedDevice:
    """A single device Microsoft Defender for Endpoint has flagged."""
    device_id: str
    device_name: str
    user_upn: Optional[str] = None  # Filled in later by the Graph connector


@dataclass
class Recommendation:
    """A single security recommendation for a single device."""
    recommendation_id: str
    device_id: str
    title: str                 # e.g. "Update Google Chrome to version 141.0"
    category: str              # "browser_restart" | "windows_update" | "app_update" | "config" | "unknown"
    severity: str               # "Low" | "Medium" | "High" | "Critical"
    cve_ids: list[str] = field(default_factory=list)
    affected_software: str = ""


@dataclass
class Finding:
    """
    The state-tracked combination of (device, recommendation) — this is what
    the state store actually persists. One row per finding, tracked over its
    entire lifecycle: detected -> notified -> reminded (N times) -> resolved / escalated.
    """
    device_id: str
    recommendation_id: str
    device_name: str
    user_upn: Optional[str]
    title: str
    category: str
    severity: str

    status: str = "detected"          # detected | notified | reminded | resolved | escalated | on_hold_no_fix
    first_detected_at: Optional[datetime] = None
    last_notified_at: Optional[datetime] = None
    reminder_count: int = 0
    resolved_at: Optional[datetime] = None
    escalated_at: Optional[datetime] = None
    ticket_id: Optional[str] = None
