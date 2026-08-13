"""
SHIELD Dashboard — a small local web UI to see notification status at a
glance, resend a specific email, and export a PDF snapshot of the current
state. Runs independently of main.py; reads/writes the same shield_state.db
and reuses the real Orchestrator for the resend action (so it goes through
the exact same Graph/Claude code path as a normal run, not a shortcut).
Only shows findings in a notifiable category (windows_update,
browser_restart) — the "config"/"app_update" ones are tracked but never
emailed to anyone, so they'd just be noise here. If that changes later
(e.g. auto-remediation gets built), this filter is the one place to update.

Expects this layout next to this file:
    dashboard.py
    templates/dashboard.html
    static/tlb_logo.png
    static/tlb_arrow.png

Run it with:
    python dashboard.py
Then open http://localhost:5050 in a browser.
"""
import sqlite3
import io
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, send_file
from config import settings
from core.orchestrator import Orchestrator, NOTIFIABLE_CATEGORIES
from core.state_store import StateStore
from core.models import Finding

app = Flask(__name__)


# Month/AM-PM spelled out by hand in English on purpose, instead of
# strftime("%b"/"%p"), since those follow the system locale and would
# show up in Spanish on this machine.
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


@app.template_filter("friendly_dt")
def friendly_dt(value):
    if not value:
        return "-"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return value
    local_dt = dt.astimezone()
    month = _MONTHS[local_dt.month - 1]
    period = "AM" if local_dt.hour < 12 else "PM"
    hour12 = local_dt.hour % 12
    if hour12 == 0:
        hour12 = 12
    return f"{month} {local_dt.day:02d}, {hour12}:{local_dt.minute:02d} {period}"


STATUS_COLORS = {
    "detected": "#9e9e9e",
    "notified": "#1976d2",
    "reminded": "#f57c00",
    "resolved": "#388e3c",
    "escalated": "#c62828",
    "on_hold_no_fix": "#7b1fa2",
}


def get_notifiable_findings():
    conn = sqlite3.connect(settings.state_db_path)
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" for _ in NOTIFIABLE_CATEGORIES)
    rows = conn.execute(
        f"SELECT * FROM findings WHERE category IN ({placeholders}) "
        f"ORDER BY last_notified_at DESC, first_detected_at DESC",
        tuple(NOTIFIABLE_CATEGORIES),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]



def get_last_run():
    return StateStore().get_last_run()


@app.route("/")
def index():
    flash = request.args.get("flash")
    flash_ok = request.args.get("ok") == "1"
    findings = get_notifiable_findings()

    total = len(findings)
    notified_count = sum(1 for f in findings if f["status"] == "notified")
    reminded_count = sum(1 for f in findings if f["status"] == "reminded")
    resolved_count = sum(1 for f in findings if f["status"] == "resolved")
    resolved_pct = round(100 * resolved_count / total) if total else 0
    reminded_pct = round(100 * reminded_count / total) if total else 0

    category_counts = {}
    for f in findings:
        category_counts[f["category"]] = category_counts.get(f["category"], 0) + 1

    return render_template(
        "dashboard.html",
        findings=findings,
        colors=STATUS_COLORS,
        flash=flash,
        flash_ok=flash_ok,
        now=datetime.now().strftime("%Y-%m-%d %H:%M"),
        last_run=get_last_run(),
        total=total,
        notified_count=notified_count,
        reminded_count=reminded_count,
        resolved_count=resolved_count,
        resolved_pct=resolved_pct,
        reminded_pct=reminded_pct,
        category_counts=category_counts,
    )


@app.route("/resend", methods=["POST"])
def resend():
    device_id = request.form["device_id"]
    recommendation_id = request.form["recommendation_id"]

    conn = sqlite3.connect(settings.state_db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM findings WHERE device_id = ? AND recommendation_id = ?",
        (device_id, recommendation_id),
    ).fetchone()
    conn.close()

    if not row or not row["user_upn"]:
        return redirect(url_for("index", flash="Could not resend — no user found for this finding.", ok="0"))

    finding = Finding(
        device_id=row["device_id"],
        recommendation_id=row["recommendation_id"],
        device_name=row["device_name"],
        user_upn=row["user_upn"],
        title=row["title"],
        category=row["category"],
        severity=row["severity"],
    )

    try:
        orch = Orchestrator()
        orch._notify([finding], row["user_upn"])
        msg = f"Resent notification to {row['user_upn']} for {row['device_name']}."
        return redirect(url_for("index", flash=msg, ok="1"))
    except Exception as e:
        return redirect(url_for("index", flash=f"Resend failed: {e}", ok="0"))


@app.route("/export-pdf")
def export_pdf():
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib import colors as rl_colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    findings = get_notifiable_findings()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
    )
    styles = getSampleStyleSheet()
    cell_style = styles["Normal"]
    cell_style.fontSize = 8
    story = []

    story.append(Paragraph("SHIELD — Status Report", styles["Title"]))
    story.append(Paragraph(f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["Normal"]))
    story.append(Spacer(1, 16))

    header = ["Device", "User", "Title", "Status", "Last Notified", "Reminders"]
    data = [header]
    for f in findings:
        data.append([
            Paragraph(f["device_name"], cell_style),
            Paragraph(f["user_upn"] or "-", cell_style),
            Paragraph(f["title"][:60], cell_style),
            Paragraph(f["status"], cell_style),
            Paragraph(f["last_notified_at"] or "-", cell_style),
            Paragraph(str(f["reminder_count"]), cell_style),
        ])

    col_widths = [doc.width * w for w in (0.16, 0.22, 0.32, 0.10, 0.12, 0.08)]

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), rl_colors.black),
        ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, rl_colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor("#f5f5f5")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(table)

    doc.build(story)
    buf.seek(0)
    return send_file(
        buf, as_attachment=True,
        download_name=f"shield_report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
        mimetype="application/pdf",
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=False)
