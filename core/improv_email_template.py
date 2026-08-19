"""
Branded HTML email template for SHIELD - Improvizations tenant.
Dark theme, no background images (Outlook compatible).
"""

IMPROV_LOGO_B64 = "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"

IMPROV_TEMPLATE_HTML = """<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background-color:#000000;font-family:Arial,Helvetica,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#000000;padding:32px 0;">
<tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="background-color:#0A0A0A;border-radius:8px;overflow:hidden;">

<!-- Header -->
<tr>
  <td style="background-color:#0D0D1A;padding:28px 32px;border-bottom:3px solid #0047BB;">
    <img src="data:image/png;base64,IMPROV_LOGO_PLACEHOLDER" alt="Improv" height="22" style="display:block;border:0;">
  </td>
</tr>

<!-- Body -->
<tr>
  <td style="padding:32px;background-color:#0A0A0A;">
    <p style="margin:0 0 16px 0;font-size:15px;color:#FFFFFF;">Hi {first_name},</p>
    <p style="margin:0 0 20px 0;font-size:15px;color:#B0B8C8;line-height:1.6;">{intro_text}</p>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:8px;">
      {ACTION_ITEMS_ROWS}
    </table>
    <p style="margin:16px 0 0 0;font-size:13px;color:#4B5563;">Take care of these whenever's convenient today, no rush.</p>
  </td>
</tr>

<!-- Footer -->
<tr>
  <td style="background-color:#050505;padding:20px 32px;border-top:1px solid #1A1A2E;">
    <p style="margin:0;font-size:12px;color:#4B5563;">
      This is an automated message from SHIELD, Improvizations' security monitoring agent.<br>
      Please do not reply to this email.
    </p>
  </td>
</tr>

</table>
</td></tr>
</table>
</body>
</html>
"""


def _row(item_html):
    return (
        '<tr><td style="padding:12px 16px;background-color:#0D1B35;'
        'border-left:3px solid #0047BB;border-radius:6px;font-size:14px;color:#D1D5DB;margin-bottom:8px;">'
        + item_html
        + '</td></tr>'
        '<tr><td style="height:8px;"></td></tr>'
    )


def render_improv_email(first_name, intro_text, items):
    rows = "".join(_row(item) for item in items)
    spacer = '<tr><td style="height:8px;"></td></tr>'
    if rows.endswith(spacer):
        rows = rows[: -len(spacer)]
    html = IMPROV_TEMPLATE_HTML
    html = html.replace("IMPROV_LOGO_PLACEHOLDER", IMPROV_LOGO_B64)
    html = html.replace("{first_name}", first_name)
    html = html.replace("{intro_text}", intro_text)
    html = html.replace("{ACTION_ITEMS_ROWS}", rows)
    return html
