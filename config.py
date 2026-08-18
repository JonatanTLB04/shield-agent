import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _get_bool(name, default=False):
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _get_int(name, default):
    val = os.getenv(name)
    return int(val) if val else default


@dataclass(frozen=True)
class TenantConfig:
    name: str
    tenant_id: str
    client_id: str
    client_secret: str
    cert_path: str
    cert_thumbprint: str
    pilot_device_hostnames: tuple
    hostname_aliases: tuple
    state_db_path: str
    sender_mailbox: str
    it_escalation_email: str


def _load_tenant(prefix, name, fallback_tenant_id=""):
    tenant_id = os.getenv(f"{prefix}_TENANT_ID", fallback_tenant_id)
    if not tenant_id:
        return None
    return TenantConfig(
        name=name,
        tenant_id=tenant_id,
        client_id=os.getenv(f"{prefix}_CLIENT_ID", ""),
        client_secret=os.getenv(f"{prefix}_CLIENT_SECRET", ""),
        cert_path=os.getenv(f"{prefix}_CERT_PATH", ""),
        cert_thumbprint=os.getenv(f"{prefix}_CERT_THUMBPRINT", ""),
        pilot_device_hostnames=tuple(
            h.strip() for h in os.getenv(f"{prefix}_PILOT_DEVICE_HOSTNAMES", "").split(",") if h.strip()
        ),
        hostname_aliases=tuple(
            (p.split(":")[0].strip(), p.split(":")[1].strip())
            for p in os.getenv(f"{prefix}_HOSTNAME_ALIASES", "").split(",")
            if ":" in p
        ),
        state_db_path=os.getenv(f"{prefix}_STATE_DB_PATH", f"shield_{name.lower()}_state.db"),
        sender_mailbox=os.getenv(f"{prefix}_SENDER_MAILBOX", os.getenv("SENDER_MAILBOX", "")),
        it_escalation_email=os.getenv(f"{prefix}_IT_ESCALATION_EMAIL", os.getenv("IT_ESCALATION_EMAIL", "")),
    )


@dataclass(frozen=True)
class Settings:
    dry_run: bool = _get_bool("SHIELD_DRY_RUN", default=True)
    tenant_id: str = os.getenv("AZURE_TENANT_ID", "")
    client_id: str = os.getenv("AZURE_CLIENT_ID", "")
    cert_path: str = os.getenv("AZURE_CERT_PATH", "")
    cert_thumbprint: str = os.getenv("AZURE_CERT_THUMBPRINT", "")
    defender_base_url: str = os.getenv("DEFENDER_BASE_URL", "https://api.security.microsoft.com")
    defender_token_resource: str = os.getenv("DEFENDER_TOKEN_RESOURCE", "https://api.securitycenter.microsoft.com")
    graph_base_url: str = "https://graph.microsoft.com/v1.0"
    datto_api_url: str = os.getenv("DATTO_API_URL", "")
    datto_api_key: str = os.getenv("DATTO_API_KEY", "")
    datto_api_secret: str = os.getenv("DATTO_API_SECRET", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    claude_model: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
    sender_mailbox: str = os.getenv("SENDER_MAILBOX", "shield@yourcompany.com")
    it_escalation_email: str = os.getenv("IT_ESCALATION_EMAIL", "it-team@yourcompany.com")
    recheck_window_hours: int = _get_int("RECHECK_WINDOW_HOURS", 48)
    reminder_max_count: int = _get_int("REMINDER_MAX_COUNT", 2)
    reminder_interval_hours: int = _get_int("REMINDER_INTERVAL_HOURS", 48)
    escalation_after_reminders: int = _get_int("ESCALATION_AFTER_REMINDERS", 2)
    state_db_path: str = os.getenv("STATE_DB_PATH", "shield_state.db")
    pilot_device_hostnames: tuple = tuple(
        h.strip() for h in os.getenv("PILOT_DEVICE_HOSTNAMES", "").split(",") if h.strip()
    )
    hostname_aliases: tuple = tuple(
        (pair.split(":")[0].strip(), pair.split(":")[1].strip())
        for pair in os.getenv("HOSTNAME_ALIASES", "").split(",")
        if ":" in pair
    )
    no_fix_keywords: tuple = ("openssl",)
    remediation_component_uid: str = os.getenv("SHIELD_REMEDIATION_COMPONENT_UID", "")
    remediable_apps: tuple = tuple(
        a.strip() for a in os.getenv(
            "SHIELD_REMEDIABLE_APPS",
            "Microsoft Office,Microsoft 365,Zoom,Adobe Acrobat,Adobe Reader"
        ).split(",") if a.strip()
    )

    @property
    def tenants(self) -> list:
        result = []
        tlb = TenantConfig(
            name="TLB",
            tenant_id=self.tenant_id,
            client_id=self.client_id,
            client_secret="",
            cert_path=self.cert_path,
            cert_thumbprint=self.cert_thumbprint,
            pilot_device_hostnames=self.pilot_device_hostnames,
            hostname_aliases=self.hostname_aliases,
            state_db_path=self.state_db_path,
            sender_mailbox=self.sender_mailbox,
            it_escalation_email=self.it_escalation_email,
        )
        if tlb.tenant_id:
            result.append(tlb)
        for prefix, name in [("IMPROV", "Improv")]:
            t = _load_tenant(prefix, name)
            if t:
                result.append(t)
        return result


settings = Settings()
