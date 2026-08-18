"""
The orchestrator — runs the entire SHIELD lifecycle once. Meant to be
triggered on a schedule (a daily timer, whether that's an Azure Function,
a cron job, or Windows Task Scheduler while you're piloting this).

The cycle, matching the architecture doc exactly:

  1. Poll Defender for exposed devices + recommendations.
  2. Gate out anything with no vendor fix available yet (e.g. OpenSSL).
  3. Gate out anything that isn't a restart-type fix (see NOTIFIABLE_CATEGORIES) —
     a regular employee can't act on a policy/hardening setting, only on
     "restart your browser" or "restart your laptop."
  4. Map each device to its user — try Defender's own lookup first, then
     fall back to Datto RMM's lastLoggedInUser + a Graph search if that
     comes back empty (this happens often in practice).
  5. For brand-new findings: draft ONE combined message with Claude covering
     every actionable finding on that device, send it, record it.
  6. For findings due for a recheck: verify via Datto RMM's live data.
       - Fixed?     -> mark resolved, done.
       - Not fixed? -> send a reminder, or escalate if the limit is reached.
"""

from dataclasses import replace

from config import settings
from connectors.defender_connector import DefenderConnector
from connectors.datto_connector import DattoConnector
from connectors.graph_connector import GraphConnector
from connectors.escalation_connector import EscalationConnector
from connectors.remediation_connector import RemediationConnector
from core.claude_client import ClaudeClient
from core.state_store import StateStore
from core.models import Finding, Recommendation

# Only these categories are things a regular employee can actually act on
# by restarting something. Everything else (app_update, config, unknown)
# gets tracked but never emailed — there's no message template for "go
# change this registry policy yourself," and there shouldn't be one.
NOTIFIABLE_CATEGORIES = {"windows_update", "browser_restart"}


class Orchestrator:
    def __init__(self, tenant=None):
        self.defender = DefenderConnector(tenant=tenant)
        self._tenant = tenant
        self.datto = DattoConnector()
        self.graph = GraphConnector()
        self.claude = ClaudeClient()
        if tenant:
            self.claude._tenant_name = tenant.name
        self.escalation = EscalationConnector(self.graph)
        self.remediation = RemediationConnector(self.datto, self.claude)
        self.store = StateStore(db_path=tenant.state_db_path if tenant else None)

    # ------------------------------------------------------------------ #
    def run_daily_cycle(self) -> dict:
        """Runs everything once. Returns a small summary dict for logging."""
        summary = {
            "new_findings": 0,
            "on_hold_no_fix": 0,
            "not_actionable": 0,
            "notified": 0,
            "resolved": 0,
            "reminded": 0,
            "escalated": 0,
            "auto_remediated": 0,
        }

        exposed = self.defender.list_exposed_devices_with_recommendations()
        if settings.pilot_device_hostnames:
            exposed = [
                (device, recs) for device, recs in exposed
                if device.device_name in settings.pilot_device_hostnames
            ]
        still_exposed_keys = {
            (device.device_id, rec.recommendation_id)
            for device, recs in exposed
            for rec in recs
        }

        self._ingest_new_findings(exposed, summary)
        self._process_due_rechecks(still_exposed_keys, summary)

        return summary

    # ------------------------------------------------------------------ #
    def _resolve_user(self, device) -> str | None:
        """
        Defender's own logged-on-user lookup is often empty in practice
        (confirmed against real devices on 2026-07-17). When it is, fall
        back to Datto RMM's own audit data instead — its lastLoggedInUser
        field is more reliably populated — and resolve that bare login
        name into a real address via Graph.
        """
        user_upn = self.defender.get_logged_on_user(device.device_id)
        if user_upn:
            return user_upn
        return self._resolve_user_by_device_name(device.device_name)

    def _resolve_user_by_device_name(self, device_name: str) -> str | None:
        """
        Same Datto + Graph fallback as _resolve_user, but callable with just
        a device name -- used to retry resolution for findings stuck past
        'detected' status (already notified/reminded), which
        _ingest_new_findings no longer touches. Without this, a finding
        created back when resolution failed keeps a blank user_upn forever,
        even after resolution starts working again.
        """
        login_hint = self.datto.get_last_logged_in_user_hint(device_name)
        if not login_hint:
            return None
        profile = self.graph.find_user_by_login_hint(login_hint)
        return profile.get("userPrincipalName") if profile else None

    # ------------------------------------------------------------------ #
    # Step 1-5: detect new findings and notify (one email per device, not
    # one email per recommendation)
    # ------------------------------------------------------------------ #
    def _ingest_new_findings(self, exposed, summary: dict) -> None:
        for device, recommendations in exposed:
            if settings.pilot_device_hostnames and device.device_name not in settings.pilot_device_hostnames:
                continue  # Not an approved pilot device — SHIELD ignores it entirely.

            user_upn = self._resolve_user(device)
            actionable = []

            for rec in recommendations:
                existing = self.store.get(device.device_id, rec.recommendation_id)

                if existing:
                    # Already tracked. Normally nothing left to do — but if
                    # it's stuck at "detected" (recorded on a run where it
                    # got tracked but never actually reached notification —
                    # e.g. dry-run mode, no user resolved yet, or the device
                    # wasn't in the pilot list at the time), give it a real
                    # shot now instead of skipping it forever. Without this
                    # check, any finding that exists in the DB at all is
                    # ignored on every future run, even if it was never
                    # truly notified.
                    if existing.status != "detected":
                        continue
                    finding = replace(existing, user_upn=user_upn or existing.user_upn)
                    if user_upn and user_upn != existing.user_upn:
                        self.store.update_user(device.device_id, rec.recommendation_id, user_upn)
                else:
                    finding = Finding(
                        device_id=device.device_id,
                        recommendation_id=rec.recommendation_id,
                        device_name=device.device_name,
                        user_upn=user_upn,
                        title=rec.title,
                        category=rec.category,
                        severity=rec.severity,
                    )
                    self.store.create_if_new(finding)
                    summary["new_findings"] += 1

                if _has_no_available_fix(rec):
                    self.store.mark_on_hold_no_fix(device.device_id, rec.recommendation_id)
                    summary["on_hold_no_fix"] += 1
                    continue

                if rec.category not in NOTIFIABLE_CATEGORIES:
                    remediated = self.remediation.try_remediate(
                        device_name=device.device_name,
                        title=rec.title,
                        affected_software=getattr(rec, "affected_software", rec.title),
                    )
                    if remediated:
                        summary.setdefault("auto_remediated", 0)
                        summary["auto_remediated"] += 1
                    else:
                        summary["not_actionable"] += 1
                    continue

                if not finding.user_upn:
                    # No confident owner even after the Datto RMM fallback —
                    # leave it tracked but unnotified.
                    continue

                actionable.append(finding)

            if actionable:
                self._notify(actionable, user_upn)
                summary["notified"] += len(actionable)

    def _notify(self, findings: list[Finding], user_upn: str) -> None:
        profile = self.graph.get_user_profile(user_upn)
        subject, body = self.claude.draft_notification(profile["displayName"], findings)
        self.graph.send_mail(profile["mail"], subject, body)
        for finding in findings:
            self.store.mark_notified(finding.device_id, finding.recommendation_id)

    # ------------------------------------------------------------------ #
    # Step 6: recheck, remind, or escalate
    # ------------------------------------------------------------------ #
    def _process_due_rechecks(self, still_exposed_keys: set, summary: dict) -> None:
        # Findings due for a reminder are grouped by user first, so someone
        # with two things pending (e.g. Windows + Chrome) gets one combined
        # reminder email instead of two separate ones -- same behavior as
        # the initial notification in _ingest_new_findings.
        reminders_by_user: dict[str, list[Finding]] = {}

        for finding in self.store.get_due_for_recheck():
            key = (finding.device_id, finding.recommendation_id)

            if key not in still_exposed_keys:
                self.store.mark_resolved(finding.device_id, finding.recommendation_id)
                summary["resolved"] += 1
                continue

            if self._verify_fixed_via_datto(finding):
                self.store.mark_resolved(finding.device_id, finding.recommendation_id)
                summary["resolved"] += 1
                continue

            if finding.reminder_count >= settings.escalation_after_reminders:
                ticket_id = self.escalation.escalate(finding)
                self.store.mark_escalated(finding.device_id, finding.recommendation_id, ticket_id)
                summary["escalated"] += 1
            else:
                # Retry user resolution here too -- a finding created back
                # when resolution failed would otherwise carry a blank
                # user_upn forever, even after resolution starts working.
                resolved_upn = finding.user_upn or self._resolve_user_by_device_name(finding.device_name)
                if resolved_upn:
                    if resolved_upn != finding.user_upn:
                        self.store.update_user(finding.device_id, finding.recommendation_id, resolved_upn)
                        finding = replace(finding, user_upn=resolved_upn)
                    reminders_by_user.setdefault(resolved_upn, []).append(finding)
                else:
                    self.store.mark_reminded(finding.device_id, finding.recommendation_id)
                    summary["reminded"] += 1

        for user_upn, findings in reminders_by_user.items():
            self._notify(findings, user_upn)
            for finding in findings:
                self.store.mark_reminded(finding.device_id, finding.recommendation_id)
                summary["reminded"] += 1

    def _verify_fixed_via_datto(self, finding: Finding) -> bool:
        if finding.category == "browser_restart":
            software = "Chrome" if "chrome" in finding.title.lower() else "Edge"
            version = self.datto.get_installed_version(finding.device_name, software)
            if version is None:
                return False
            return version.startswith("141")

        if finding.category == "windows_update":
            status = self.datto.get_patch_status(finding.device_name)
            if status is None:
                return False
            return status.get("patchStatus") == "Fully Patched"

        return False


def _has_no_available_fix(rec: Recommendation) -> bool:
    """The gate we agreed on: don't notify users about things nobody can fix yet."""
    haystack = f"{rec.title} {rec.affected_software}".lower()
    return any(keyword in haystack for keyword in settings.no_fix_keywords)
