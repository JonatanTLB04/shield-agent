"""
Escalation connector — creates a ticket when a finding has gone unresolved
past the configured limit.

This is deliberately the thinnest connector in the codebase: it only needs
create + (later) update-status operations, so it's the easiest one to
swap out. Wire this up to whichever ticketing system you land on
(Autotask, ServiceNow, Jira, etc.) — for now it just sends a plain email
to your IT team, which works immediately with zero extra setup and can
be replaced once you've picked a system.
"""

from config import settings
from connectors.graph_connector import GraphConnector
from core.models import Finding


class EscalationConnector:
    def __init__(self, graph: GraphConnector):
        self._graph = graph

    def escalate(self, finding: Finding) -> str:
        """
        Creates an escalation. Returns a ticket ID.

        TODO: once you've picked a ticketing system, replace the body of
        this method with a real API call (e.g. Autotask's REST API) and
        return the real ticket number instead of a generated placeholder.
        """
        ticket_id = f"SHIELD-{finding.device_id}-{finding.recommendation_id}"

        subject = f"[SHIELD escalation] {finding.device_name} — {finding.title}"
        body = f"""
        <p>The following item has not been resolved after
        {finding.reminder_count} reminder(s) and needs IT follow-up:</p>
        <ul>
            <li><b>Device:</b> {finding.device_name}</li>
            <li><b>User:</b> {finding.user_upn}</li>
            <li><b>Issue:</b> {finding.title}</li>
            <li><b>Severity:</b> {finding.severity}</li>
            <li><b>First detected:</b> {finding.first_detected_at}</li>
        </ul>
        """
        self._graph.send_mail(settings.it_escalation_email, subject, body)
        return ticket_id
