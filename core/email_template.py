"""
Branded HTML email template for SHIELD notifications.
Contains the TLB logo (base64-embedded from the brand asset file) and
three placeholders filled in by render_email() below:
  {{first_name}}       -> recipient's first name
  {{intro_text}}       -> one-line intro, differs for new findings vs. reminders
  {{ACTION_ITEMS_ROWS}} -> one <tr><td>...</td></tr> block per finding
"""

TEMPLATE_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
</head>
<body style="margin:0; padding:0; background-color:#EEF2F5; font-family:Arial, Helvetica, sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#EEF2F5; padding:32px 0;">
    <tr>
      <td align="center">
        <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="background-color:#FFFFFF; border-radius:8px; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,0.08);">

          <!-- Header -->
          <tr>
            <td style="background-color:#1A1A1A; padding:20px 32px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td>
                    <span style="color:#FF6600; font-size:20px; font-weight:bold; letter-spacing:0.5px;">SHIELD</span>
                    <span style="color:#FFFFFF; font-size:13px; margin-left:8px;">Security Operations</span>
                  </td>
                  <td align="right" valign="middle">
                    <img src="data:image/png;base64,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" alt="The Launch Box" width="110" height="20" style="display:block; width:110px; height:20px; border:0;">
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:32px;">
              <p style="margin:0 0 16px 0; font-size:15px; color:#1A1A1A;">Hi {{first_name}},</p>

              <p style="margin:0 0 20px 0; font-size:15px; color:#1A1A1A; line-height:1.5;">
                {{intro_text}}
              </p>

              <!-- Action items -->
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:8px;">
                {{ACTION_ITEMS_ROWS}}
              </table>

              <p style="margin:16px 0 0 0; font-size:13px; color:#6B7280;">
                Take care of these whenever's convenient today, no rush.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color:#EEF2F5; padding:20px 32px; border-top:1px solid #E5E7EB;">
              <p style="margin:0; font-size:12px; color:#6B7280;">
                This is an automated message from SHIELD, TLB's security monitoring agent.<br>
                Please do not reply to this email.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def _row(item_html: str) -> str:
    """Wraps one action-item description in the template's row styling."""
    return (
        '<tr><td style="padding:10px 14px; background-color:#EEF2F5; '
        'border-radius:6px; font-size:14px; color:#1A1A1A;">'
        f'{item_html}</td></tr>'
        '<tr><td style="height:8px;"></td></tr>'
    )


def render_email(first_name: str, intro_text: str, items: list[str]) -> str:
    """
    Renders the full branded HTML email.
    items: a list of short HTML strings, one per finding, e.g.
           ['<strong>Restart your browser (Chrome)</strong> - an update is '
           'downloaded and waiting for a restart to apply.']
    """
    rows = "".join(_row(item) for item in items)
    # Strip the trailing spacer row after the last item so there is no
    # dangling gap at the bottom of the list.
    spacer = '<tr><td style="height:8px;"></td></tr>'
    if rows.endswith(spacer):
        rows = rows[: -len(spacer)]

    html = TEMPLATE_HTML
    html = html.replace("{{first_name}}", first_name)
    html = html.replace("{{intro_text}}", intro_text)
    html = html.replace("{{ACTION_ITEMS_ROWS}}", rows)
    return html
