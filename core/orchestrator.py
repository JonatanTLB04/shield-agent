"""
The orchestrator — runs the entire SHIELD lifecycle once. Meant to be
triggered on a schedule (a daily timer, whether that's an Azure Function,
a cron job, or Windows Task Scheduler while you're piloting this).

The cycle, matching the architecture doc exactly:

  1. Poll Defender for exposed devices + recommendations.
  2. Gate out anything with no vendor fix available yet (e.g. OpenSSL).
  3. Map each device to its user.
  4. For brand-new findings: draft a message with Claude, send it, record it.
  5. For findings due for a recheck: verify via Datto RMM's live data.
       - Fixed?     -> mark resolved, done.
       - Not fixed? -> send a reminder, or escalate if the limit is reached.
"""

from dataclasses import replace

from config import settings
from connectors.defender_connector import DefenderConnector
from connectors.datto_connector import DattoConnector
from connectors.graph_connector import GraphConnector
from connectors.escalation_connector import EscalationConnector
from core.claude_client import ClaudeClient
from core.state_store import StateStore
from core.models import Finding, Recommendation


class Orchestrator:
    def __init__(self):
        self.defender = DefenderConnector()
        self.datto = DattoConnector()
        self.graph = GraphConnector()
        self.claude = ClaudeClient()
        self.escalation = EscalationConnector(self.graph)
        self.store = StateStore()

    # ------------------------------------------------------------------ #
    def run_daily_cycle(self) -> dict:
        """Runs everything once. Returns a small summary dict for logging."""
        summary = {
            "new_findings": 0,
            "on_hold_no_fix": 0,
            "notified": 0,
            "resolved": 0,
            "reminded": 0,
            "escalated": 0,
        }

        # Fetched once, used by both steps below — this is what lets us fall
        # back to "does Defender still list this?" for any device that
        # isn't in Datto RMM yet (partial migration), instead of that device
        # simply never getting rechecked.
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
    # Step 1-3: detect new findings and notify
    # ------------------------------------------------------------------ #
    def _ingest_new_findings(self, exposed, summary: dict) -> None:
        for device, recommendations in exposed:
            if settings.pilot_device_hostnames and device.device_name not in settings.pilot_device_hostnames:
                continue  # Not an approved pilot device — SHIELD ignores it entirely.
            user_upn = self.defender.get_logged_on_user(device.device_id)

            for rec in recommendations:
                existing = self.store.get(device.device_id, rec.recommendation_id)
                if existing:
                    continue  # already tracked, nothing to do here

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

                if not user_upn:
                    # No confident owner — leave it tracked but unnotified;
                    # a human should review these periodically rather than
                    # guessing who to email.
                    continue

                self._notify(finding, user_upn)
                summary["notified"] += 1

    def _notify(self, finding: Finding, user_upn: str) -> None:
        profile = self.graph.get_user_profile(user_upn)
        subject, body = self.claude.draft_notification(profile["displayName"], finding)
        self.graph.send_mail(profile["mail"], subject, body)
        self.store.mark_notified(finding.device_id, finding.recommendation_id)

    # ------------------------------------------------------------------ #
    # Step 4: recheck, remind, or escalate
    # ------------------------------------------------------------------ #
    def _process_due_rechecks(self, still_exposed_keys: set, summary: dict) -> None:
        for finding in self.store.get_due_for_recheck():
            key = (finding.device_id, finding.recommendation_id)

            if key not in still_exposed_keys:
                # Defender itself no longer lists this — resolved, whether
                # or not the device has been migrated to Datto RMM yet.
                self.store.mark_resolved(finding.device_id, finding.recommendation_id)
                summary["resolved"] += 1
                continue

            # Defender still sees it as open. Try the faster Datto RMM check
            # if this device has been migrated — if not, we simply wait for
            # Defender's own next poll instead of treating it as an error.
            if self._verify_fixed_via_datto(finding):
                self.store.mark_resolved(finding.device_id, finding.recommendation_id)
                summary["resolved"] += 1
                continue

            if finding.reminder_count >= settings.escalation_after_reminders:
                ticket_id = self.escalation.escalate(finding)
                self.store.mark_escalated(finding.device_id, finding.recommendation_id, ticket_id)
                summary["escalated"] += 1
            else:
                if finding.user_upn:
                    reminder_finding = replace(finding, reminder_count=finding.reminder_count)
                    self._notify(reminder_finding, finding.user_upn)
                self.store.mark_reminded(finding.device_id, finding.recommendation_id)
                summary["reminded"] += 1

    def _verify_fixed_via_datto(self, finding: Finding) -> bool:
        """
        The key design decision from our conversation: don't wait on
        Defender's own slow refresh where possible. Check the device's real,
        current state directly via Datto RMM instead — matched by hostname,
        since Defender and Datto RMM use different device IDs.

        Returns False (not fixed, or unknown) for devices not yet migrated
        to Datto RMM — those simply rely on the still_exposed_keys check
        above catching it on a later run once Defender itself clears it.
        """
        if finding.category == "browser_restart":
            software = "Chrome" if "chrome" in finding.title.lower() else "Edge"
            version = self.datto.get_installed_version(finding.device_name, software)
            if version is None:
                return False  # Not fixed yet, or not migrated to Datto RMM yet
            # A real implementation would compare this against the specific
            # fixed version named in the recommendation's title.
            return version.startswith("141")

        if finding.category == "windows_update":
            status = self.datto.get_patch_status(finding.device_name)
            if status is None:
                return False
            return status.get("patchStatus") == "Fully Patched"

        # For everything else, rely on the still_exposed_keys check above.
        return False


def _has_no_available_fix(rec: Recommendation) -> bool:
    """The gate we agreed on: don't notify users about things nobody can fix yet."""
    haystack = f"{rec.title} {rec.affected_software}".lower()
    return any(keyword in haystack for keyword in settings.no_fix_keywords)
