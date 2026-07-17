"""
State store for SHIELD.

Uses SQLite for now — one file, zero setup, perfect for building and
piloting. When you move to Stage 15 (company-wide rollout), swap this for
Azure Cosmos DB or Azure SQL by replacing this one file; nothing else in
the codebase needs to change, since the orchestrator only ever calls the
methods defined here.

One row per (device_id, recommendation_id) pair — this is what prevents
duplicate notifications and drives the reminder/escalation timers.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from config import settings
from core.models import Finding

_SCHEMA = """
CREATE TABLE IF NOT EXISTS findings (
    device_id TEXT NOT NULL,
    recommendation_id TEXT NOT NULL,
    device_name TEXT,
    user_upn TEXT,
    title TEXT,
    category TEXT,
    severity TEXT,
    status TEXT NOT NULL DEFAULT 'detected',
    first_detected_at TEXT,
    last_notified_at TEXT,
    reminder_count INTEGER NOT NULL DEFAULT 0,
    resolved_at TEXT,
    escalated_at TEXT,
    ticket_id TEXT,
    PRIMARY KEY (device_id, recommendation_id)
);
"""


class StateStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.state_db_path
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    def get(self, device_id: str, recommendation_id: str) -> Finding | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM findings WHERE device_id = ? AND recommendation_id = ?",
                (device_id, recommendation_id),
            ).fetchone()
        return _row_to_finding(row) if row else None

    def create_if_new(self, finding: Finding) -> Finding:
        """Inserts a brand-new finding, or returns the existing one untouched."""
        existing = self.get(finding.device_id, finding.recommendation_id)
        if existing:
            return existing

        finding.first_detected_at = datetime.now(timezone.utc)
        finding.status = "detected"
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO findings
                   (device_id, recommendation_id, device_name, user_upn, title,
                    category, severity, status, first_detected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    finding.device_id, finding.recommendation_id, finding.device_name,
                    finding.user_upn, finding.title, finding.category, finding.severity,
                    finding.status, finding.first_detected_at.isoformat(),
                ),
            )
        return finding

    def mark_notified(self, device_id: str, recommendation_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE findings SET status='notified', last_notified_at=? "
                "WHERE device_id=? AND recommendation_id=?",
                (datetime.now(timezone.utc).isoformat(), device_id, recommendation_id),
            )

    def mark_reminded(self, device_id: str, recommendation_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE findings SET status='reminded', last_notified_at=?, "
                "reminder_count = reminder_count + 1 "
                "WHERE device_id=? AND recommendation_id=?",
                (datetime.now(timezone.utc).isoformat(), device_id, recommendation_id),
            )

    def mark_resolved(self, device_id: str, recommendation_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE findings SET status='resolved', resolved_at=? "
                "WHERE device_id=? AND recommendation_id=?",
                (datetime.now(timezone.utc).isoformat(), device_id, recommendation_id),
            )

    def mark_escalated(self, device_id: str, recommendation_id: str, ticket_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE findings SET status='escalated', escalated_at=?, ticket_id=? "
                "WHERE device_id=? AND recommendation_id=?",
                (datetime.now(timezone.utc).isoformat(), ticket_id, device_id, recommendation_id),
            )

    def mark_on_hold_no_fix(self, device_id: str, recommendation_id: str) -> None:
        """For findings like OpenSSL, where no vendor fix exists yet."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE findings SET status='on_hold_no_fix' "
                "WHERE device_id=? AND recommendation_id=?",
                (device_id, recommendation_id),
            )

    def get_due_for_recheck(self) -> list[Finding]:
        """
        Findings that were notified/reminded long enough ago that it's
        worth checking again. Deliberately does NOT recheck same-day —
        see the architecture note on Defender's own catch-up lag.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=settings.recheck_window_hours)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM findings WHERE status IN ('notified', 'reminded') "
                "AND last_notified_at <= ?",
                (cutoff,),
            ).fetchall()
        return [_row_to_finding(r) for r in rows]

    def get_all_open(self) -> list[Finding]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM findings WHERE status NOT IN ('resolved', 'on_hold_no_fix')"
            ).fetchall()
        return [_row_to_finding(r) for r in rows]


def _row_to_finding(row: sqlite3.Row) -> Finding:
    return Finding(
        device_id=row["device_id"],
        recommendation_id=row["recommendation_id"],
        device_name=row["device_name"],
        user_upn=row["user_upn"],
        title=row["title"],
        category=row["category"],
        severity=row["severity"],
        status=row["status"],
        reminder_count=row["reminder_count"],
        ticket_id=row["ticket_id"],
    )
