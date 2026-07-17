"""
Central configuration for SHIELD.

Everything here is read from environment variables (see .env.example) —
nothing is ever hardcoded, and no credential is ever committed to source
control. In production, these values should come from Azure Key Vault
references, not a plain .env file.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _get_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _get_int(name: str, default: int) -> int:
    val = os.getenv(name)
    return int(val) if val else default


@dataclass(frozen=True)
class Settings:
    # --- Master switch -------------------------------------------------
    # When True, no real API calls are made anywhere. Every connector
    # returns realistic fixture data instead. Use this until stages 1-7
    # of the rollout plan (licensing, Entra ID app registration, Datto RMM
    # API keys) are actually done.
    dry_run: bool = _get_bool("SHIELD_DRY_RUN", default=True)

    # --- Microsoft Entra ID / Defender for Endpoint ---------------------
    tenant_id: str = os.getenv("AZURE_TENANT_ID", "")
    client_id: str = os.getenv("AZURE_CLIENT_ID", "")
    cert_path: str = os.getenv("AZURE_CERT_PATH", "")          # path to .pem private key
    cert_thumbprint: str = os.getenv("AZURE_CERT_THUMBPRINT", "")

    defender_base_url: str = os.getenv(
        "DEFENDER_BASE_URL", "https://api.security.microsoft.com"
    )
    # Some Defender for Endpoint endpoints still expect the legacy resource
    # audience even when called against the newer base URL — see the
    # architecture doc for why this is requested separately.
    defender_token_resource: str = os.getenv(
        "DEFENDER_TOKEN_RESOURCE", "https://api.securitycenter.microsoft.com"
    )

    graph_base_url: str = "https://graph.microsoft.com/v1.0"

    # --- Datto RMM -------------------------------------------------------
    datto_api_url: str = os.getenv("DATTO_API_URL", "")   # e.g. https://merlot-api.centrastage.net
    datto_api_key: str = os.getenv("DATTO_API_KEY", "")
    datto_api_secret: str = os.getenv("DATTO_API_SECRET", "")

    # --- Claude ------------------------------------------------------
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    claude_model: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

    # --- Notifications ---------------------------------------------------
    sender_mailbox: str = os.getenv("SENDER_MAILBOX", "shield@yourcompany.com")
    it_escalation_email: str = os.getenv("IT_ESCALATION_EMAIL", "it-team@yourcompany.com")

    # --- Timing (all configurable, per the architecture doc) --------------
    recheck_window_hours: int = _get_int("RECHECK_WINDOW_HOURS", 48)
    reminder_max_count: int = _get_int("REMINDER_MAX_COUNT", 2)
    reminder_interval_hours: int = _get_int("REMINDER_INTERVAL_HOURS", 48)
    escalation_after_reminders: int = _get_int("ESCALATION_AFTER_REMINDERS", 2)

    # --- State store -------------------------------------------------------
    state_db_path: str = os.getenv("STATE_DB_PATH", "shield_state.db")

    # --- Pilot safety switch -------------------------------------------------
    # While piloting, list the exact device hostnames SHIELD is allowed to
    # touch, comma-separated (e.g. "BTDXPS,Lia"). Every other device gets
    # ignored completely, even though Defender still reports them. Leave
    # empty ONLY once you're intentionally ready for a company-wide rollout.
    pilot_device_hostnames: tuple[str, ...] = tuple(
        h.strip() for h in os.getenv("PILOT_DEVICE_HOSTNAMES", "").split(",") if h.strip()
    )

    # --- "No fix available yet" gate ----------------------------------------
    # Software names that, if they appear in a recommendation's affected
    # software, get routed to the on-hold list instead of a user notification.
    # This is a starting point, not a permanent list — review it periodically,
    # since vendors do eventually ship fixes.
    no_fix_keywords: tuple[str, ...] = ("openssl",)


settings = Settings()
