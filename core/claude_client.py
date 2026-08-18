"""
Claude integration - this is the "reasoning" layer, not a data-mover.
Given one or more findings for the same person (device + recommendation),
this turns them into a short, friendly, non-technical description per
item, which then gets rendered into the branded HTML template (see
core/email_template.py). Claude does NOT write raw HTML directly anymore
- it returns structured JSON, and the template owns the actual visual
layout. This keeps the branding consistent no matter what Claude writes.
"""

import json

from anthropic import Anthropic

from config import settings
from core.models import Finding
from core.email_template import render_email
from core.improv_email_template import render_improv_email

_SYSTEM_PROMPT = """\
You help draft short, friendly, non-technical notifications for SHIELD, \
an internal IT security assistant. The reader is a regular employee, not \
an IT professional - never use jargon like CVE, CVSS, exposure score, or \
recommendation ID. Never mention Microsoft Defender, Datto RMM, or any \
internal system by name.

You will be given one or more items to fix for the same person. For each \
item, write ONE short line (about 15-25 words) explaining what needs to \
happen and, briefly, why it matters - no fear-mongering, just plain and \
clear. Start each line with the action in bold using <strong> tags, \
followed by a short explanation, matching this exact style:

<strong>Restart your browser (Chrome)</strong> - an update is downloaded and waiting for a restart to apply.

Also write one short intro line (a single sentence, no greeting - the \
greeting is added separately) that fits above the list of items. If any \
item's reminder_count is greater than 0, make the intro gently \
acknowledge this is a follow-up, without sounding annoyed.

Output ONLY a JSON object, nothing else, no markdown fences, no preamble, \
in exactly this shape:
{"intro": "<one sentence>", "items": ["<item 1 html>", "<item 2 html>", ...]}
"""

_ACTION_HINTS = {
    "browser_restart": "restarting your browser (Chrome or Edge) to finish applying an update",
    "windows_update": "restarting your laptop to finish installing pending updates",
    "app_update": "updating an application that has a pending security update",
    "config": "a small security setting on your device that needs to be adjusted",
    "unknown": "a security item on your device that needs attention",
}

# Fixed small-print hints appended under specific categories, always
# exactly this wording - not left up to Claude to remember every time.
_CATEGORY_SMALL_PRINT = {
    "browser_restart": "Just close all your open tabs and reopen the browser - that's all it takes.",
}


def _append_category_hints(items: list[str], findings: list[Finding]) -> list[str]:
    """Appends a small gray tip line under an item's own description, for
    categories in _CATEGORY_SMALL_PRINT above. Relies on items[i] matching
    findings[i] in order, same assumption the rest of this pipeline already
    makes about Claude's JSON output matching the input order."""
    result = []
    for item_html, finding in zip(items, findings):
        hint = _CATEGORY_SMALL_PRINT.get(finding.category)
        if hint:
            item_html += f'<br><span style="font-size:12px; color:#6B7280;">{hint}</span>'
        result.append(item_html)
    return result


class ClaudeClient:
    def __init__(self):
        self._client = Anthropic(api_key=settings.anthropic_api_key)

    def draft_notification(self, user_display_name: str, findings: list[Finding]) -> tuple[str, str]:
        """
        Returns (subject, html_body) for one or more findings on the same
        device/user, combined into a single branded email. Always pass a
        list, even for a single finding - e.g. draft_notification(name, [finding]).
        """
        if not findings:
            raise ValueError("draft_notification called with an empty findings list")

        is_reminder = any(f.reminder_count > 0 for f in findings)
        first_name = user_display_name.split()[0]

        if settings.dry_run and not settings.anthropic_api_key:
            # Allows a fully offline dry run with zero API keys configured at all.
            return _offline_fallback(first_name, findings, is_reminder)

        items_block = "\n".join(
            f"- Device: {f.device_name} | What needs to happen: "
            f"{_ACTION_HINTS.get(f.category, _ACTION_HINTS['unknown'])} | "
            f"Severity: {f.severity} | Reminder count so far: {f.reminder_count}"
            for f in findings
        )
        user_prompt = f"""\
Recipient's first name: {first_name}
Number of items in this email: {len(findings)}

{items_block}
"""
        response = self._client.messages.create(
            model=settings.claude_model,
            max_tokens=500,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw_text = "".join(block.text for block in response.content if block.type == "text").strip()

        # Defensive parsing - strip markdown fences if Claude adds them
        # despite being told not to, rather than erroring out mid-pipeline.
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`")
            if raw_text.startswith("json"):
                raw_text = raw_text[4:].strip()

        parsed = json.loads(raw_text)
        intro_text = parsed["intro"]
        items = _append_category_hints(parsed["items"], findings)

        tenant_name = getattr(self, '_tenant_name', 'TLB')
        if tenant_name == 'Improv':
            body_html = render_improv_email(first_name, intro_text, items)
        else:
            tenant_name = getattr(self, '_tenant_name', 'TLB')
        if tenant_name == 'Improv':
            body_html = render_improv_email(first_name, intro_text, items)
        else:
            body_html = render_email(first_name, intro_text, items)
        subject = (
            "Quick follow-up: your laptop still needs attention"
            if is_reminder
            else "Action needed: your laptop needs a quick fix"
        )
        return subject, body_html


def _offline_fallback(first_name: str, findings: list[Finding], is_reminder: bool) -> tuple[str, str]:
    """Used only when there's no Anthropic API key at all yet, so dry runs
    work out of the box, still using the same branded template."""
    hints = [_ACTION_HINTS.get(f.category, _ACTION_HINTS["unknown"]) for f in findings]
    items = [
        f"<strong>{f.device_name}</strong> needs {hint}."
        for f, hint in zip(findings, hints)
    ]
    items = _append_category_hints(items, findings)

    if is_reminder:
        intro_text = "Just a quick follow-up on something from before, it still needs a bit of attention."
    elif len(findings) == 1:
        intro_text = "Your laptop needs a quick thing taken care of to stay secure."
    else:
        intro_text = "Your laptop needs a couple of quick things taken care of to stay secure."

    body_html = render_email(first_name, intro_text, items)
    subject = (
        "Quick follow-up: your laptop still needs attention"
        if is_reminder
        else "Action needed: your laptop needs a quick fix"
    )
    return subject, body_html


