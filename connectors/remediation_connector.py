"""
RemediationConnector — asks Claude to generate a silent PowerShell fix
for a given vulnerability, then fires it on the device via Datto RMM
Quick Job. Runs as SYSTEM, fully silent, no user interruption.
"""

from config import settings
from core.claude_client import ClaudeClient
from connectors.datto_connector import DattoConnector


class RemediationConnector:
    def __init__(self, datto: DattoConnector, claude: ClaudeClient):
        self.datto = datto
        self.claude = claude

    def try_remediate(self, device_name: str, title: str, affected_software: str) -> bool:
        if not settings.remediation_component_uid:
            return False
        if not self._is_remediable(affected_software):
            return False
        script = self._generate_script(title, affected_software)
        if not script:
            return False
        if _requires_reboot(script):
            return False
        device_uid = self.datto.find_device_uid_by_hostname(device_name)
        if not device_uid:
            return False
        try:
            self.datto.run_quick_job(
                device_uid=device_uid,
                component_uid=settings.remediation_component_uid,
                variables={"SHIELD_SCRIPT": script},
            )
            return True
        except Exception:
            return False

    def _is_remediable(self, affected_software: str) -> bool:
        sw = affected_software.lower()
        return any(app.lower() in sw for app in settings.remediable_apps)

    def _generate_script(self, title: str, affected_software: str) -> str | None:
        prompt = (
            "You are a Windows IT automation expert. Generate a single PowerShell script "
            "that silently updates or fixes the following vulnerability on an end-user Windows device.\n\n"
            f"Vulnerability: {title}\n"
            f"Affected software: {affected_software}\n\n"
            "Rules:\n"
            "- The script must run silently with no user prompts or UI.\n"
            "- The script must NOT force a reboot. If a reboot is required, output ONLY the word REBOOT_REQUIRED.\n"
            "- The script must NOT install new software, only update existing installations.\n"
            "- Use built-in Windows mechanisms or the software own silent update CLI.\n"
            "- Output ONLY the PowerShell script, no explanation, no markdown.\n"
            "- If you cannot safely fix this silently, output ONLY the word CANNOT_REMEDIATE."
        )
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            msg = client.messages.create(
                model=settings.claude_model,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
            )
            result = msg.content[0].text.strip()
            if result in ("REBOOT_REQUIRED", "CANNOT_REMEDIATE"):
                return None
            return result
        except Exception:
            return None


def _requires_reboot(script: str) -> bool:
    keywords = ("restart-computer", "shutdown /r", "shutdown -r", "reboot")
    lower = script.lower()
    return any(k in lower for k in keywords)
