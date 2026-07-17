"""
Claude integration — this is the "reasoning" layer, not a data-mover.

Given a finding (device + recommendation), this turns it into a clear,
friendly, non-technical email a regular employee will actually understand
and act on. It does NOT call any of the other APIs itself — the
orchestrator hands it plain data and gets back plain text.
"""

from anthropic import Anthropic

from config import settings
from core.models import Finding

_SYSTEM_PROMPT = """\
You write short, friendly, non-technical emails for SHIELD, an internal \
IT security assistant. The reader is a regular employee, not an IT \
professional — never use jargon like CVE, CVSS, exposure score, or \
recommendation ID. Never mention Microsoft Defender, Datto RMM, or any \
internal system by name; the email should read as if it's simply from \
the IT/Security team.

Keep it to 3-4 short sentences. Always explain, in plain language, why \
this matters (briefly, no fear-mongering) and exactly one clear action \
the reader needs to take. If a reminder_count is greater than 0, \
acknowledge gently that this is a follow-up, without sounding annoyed.

Output only the email body as clean HTML (a couple of <p> tags is enough) \
— no subject line, no preamble, no markdown fences.
"""

_ACTION_HINTS = {
    "browser_restart": "restarting your browser (Chrome or Edge) to finish applying an update",
    "windows_update": "restarting your laptop to finish installing pending updates",
    "app_update": "updating an application that has a pending security update",
    "config": "a small security setting on your device that needs to be adjusted",
    "unknown": "a security item on your device that needs attention",
}


class ClaudeClient:
    def __init__(self):
        self._client = Anthropic(api_key=settings.anthropic_api_key)

    def draft_notification(self, user_display_name: str, finding: Finding) -> tuple[str, str]:
        """Returns (subject, html_body)."""
        action_hint = _ACTION_HINTS.get(finding.category, _ACTION_HINTS["unknown"])

        if settings.dry_run and not settings.anthropic_api_key:
            # Allows a fully offline dry run with zero API keys configured at all.
            return _offline_fallback(user_display_name, finding, action_hint)

        user_prompt = f"""\
Recipient's first name: {user_display_name}
Device name: {finding.device_name}
What needs to happen: {action_hint}
Severity: {finding.severity}
Reminder count so far: {finding.reminder_count}
"""

        response = self._client.messages.create(
            model=settings.claude_model,
            max_tokens=400,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        body_html = "".join(block.text for block in response.content if block.type == "text")

        subject = (
            f"Quick follow-up: your laptop still needs attention"
            if finding.reminder_count > 0
            else f"Action needed: your laptop needs a quick fix"
        )
        return subject, body_html


def _offline_fallback(name: str, finding: Finding, action_hint: str) -> tuple[str, str]:
    """Used only when there's no Anthropic API key at all yet, so dry runs work out of the box."""
    prefix = "Just a quick follow-up — " if finding.reminder_count > 0 else "Hi " + name.split()[0] + ", "
    body = (
        f"<p>{prefix}your device ({finding.device_name}) needs {action_hint}. "
        f"It only takes a minute and helps keep your laptop secure.</p>"
        f"<p>Thanks for taking care of this!</p>"
    )
    subject = (
        "Quick follow-up: your laptop still needs attention"
        if finding.reminder_count > 0
        else "Action needed: your laptop needs a quick fix"
    )
    return subject, body
