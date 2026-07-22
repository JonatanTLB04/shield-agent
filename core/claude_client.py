"""
Claude integration — this is the "reasoning" layer, not a data-mover.
Given one or more findings for the same person (device + recommendation),
this turns them into a single clear, friendly, non-technical email a
regular employee will actually understand and act on. It does NOT call
any of the other APIs itself — the orchestrator hands it plain data and
gets back plain text.
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

You may be given one item to fix, or several. If there is more than one, \
combine them into a single email — never write it as if there are \
several unrelated emails. A short, friendly list (one line per item) is \
fine if there's more than one action needed. If there's only one, just \
write it as plain sentences, no list needed.

Always explain, in plain language, why this matters (briefly, no \
fear-mongering) and exactly what the reader needs to do for each item. If \
any item's reminder_count is greater than 0, acknowledge gently that this \
is a follow-up, without sounding annoyed.

Output only the email body as clean HTML (a couple of <p> tags, and a \
<ul>/<li> list only if there's more than one item) — no subject line, no \
preamble, no markdown fences.
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

    def draft_notification(self, user_display_name: str, findings: list[Finding]) -> tuple[str, str]:
        """
        Returns (subject, html_body) for one or more findings on the same
        device/user, combined into a single email. Always pass a list, even
        for a single finding — e.g. draft_notification(name, [finding]).
        """
        if not findings:
            raise ValueError("draft_notification called with an empty findings list")

        is_reminder = any(f.reminder_count > 0 for f in findings)

        if settings.dry_run and not settings.anthropic_api_key:
            # Allows a fully offline dry run with zero API keys configured at all.
            return _offline_fallback(user_display_name, findings, is_reminder)

        items_block = "\n".join(
            f"- Device: {f.device_name} | What needs to happen: "
            f"{_ACTION_HINTS.get(f.category, _ACTION_HINTS['unknown'])} | "
            f"Severity: {f.severity} | Reminder count so far: {f.reminder_count}"
            for f in findings
        )
        user_prompt = f"""\
Recipient's first name: {user_display_name}
Number of items in this email: {len(findings)}

{items_block}
"""
        response = self._client.messages.create(
            model=settings.claude_model,
            max_tokens=500,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        body_html = "".join(block.text for block in response.content if block.type == "text")
        subject = (
            "Quick follow-up: your laptop still needs attention"
            if is_reminder
            else "Action needed: your laptop needs a quick fix"
        )
        return subject, body_html


def _offline_fallback(name: str, findings: list[Finding], is_reminder: bool) -> tuple[str, str]:
    """Used only when there's no Anthropic API key at all yet, so dry runs work out of the box."""
    first_name = name.split()[0]
    hints = [_ACTION_HINTS.get(f.category, _ACTION_HINTS["unknown"]) for f in findings]

    if len(findings) == 1:
        prefix = "Just a quick follow-up — " if is_reminder else f"Hi {first_name}, "
        body = (
            f"<p>{prefix}your device ({findings[0].device_name}) needs {hints[0]}. "
            f"It only takes a minute and helps keep your laptop secure.</p>"
            f"<p>Thanks for taking care of this!</p>"
        )
    else:
        intro = "Just a quick follow-up on a couple of things — " if is_reminder else f"Hi {first_name}, "
        items_html = "".join(f"<li>{hint} ({f.device_name})</li>" for f, hint in zip(findings, hints))
        body = (
            f"<p>{intro}your device needs a couple of quick fixes:</p>"
            f"<ul>{items_html}</ul>"
            f"<p>Both only take a minute and help keep your laptop secure. Thanks for taking care of this!</p>"
        )

    subject = (
        "Quick follow-up: your laptop still needs attention"
        if is_reminder
        else "Action needed: your laptop needs a quick fix"
    )
    return subject, body
