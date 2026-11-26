"""Branded HTML version of the transactional emails.

The plain-text body stays the source of truth (it is what we log and send as the text
alternative); this only dresses it in the same design tokens as the app. Email clients ignore
web fonts and external CSS, so everything is inline, table-based, with system-font fallbacks.
"""

from html import escape

ORANGE = "#ff5c00"
INK = "#1d1d1d"
BODY = "#4a4a4a"
MUTED = "#7b7b7b"
LINE = "#e1e1e1"
CANVAS = "#f6f6f6"
SANS = "Geist, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
SERIF = "'Instrument Serif', Georgia, 'Times New Roman', serif"

# template -> (badge label, badge background, badge text colour)
BADGES: dict[str, tuple[str, str, str]] = {
    "policy_issued": ("Policy issued", "#e7f4ec", "#1f8a4c"),
    "payment_received": ("Paid", "#e7f4ec", "#1f8a4c"),
    "payment_failed": ("Payment failed", "#fde8e8", "#b91c1c"),
    "coverage_added": ("Coverage added", "#ffdecc", "#cc4a00"),
    "coverage_corrected": ("Correction", "#ffdecc", "#cc4a00"),
    "policy_cancelled": ("Cancelled", "#eeeeee", "#4a4a4a"),
    "refund_issued": ("Refund issued", "#e7f4ec", "#1f8a4c"),
}


def _paragraphs(body: str) -> list[str]:
    parts = [p.strip() for p in body.strip().split("\n\n")]
    # drop the plain-text sign-off; the HTML has a proper footer
    return [p for p in parts if p and not p.startswith("— Corgi")]


def render_email_html(template: str, subject: str, body: str, portal_url: str) -> str:
    label, badge_bg, badge_fg = BADGES.get(template, ("Update", "#eeeeee", BODY))
    paras = "".join(
        f'<p style="margin:0 0 14px;font-size:15px;line-height:1.6;color:{BODY};">'
        f"{escape(p).replace(chr(10), '<br>')}</p>"
        for p in _paragraphs(body)
    )
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:{CANVAS};">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:{CANVAS};">
<tr><td align="center" style="padding:32px 16px;">
  <table role="presentation" width="560" cellspacing="0" cellpadding="0"
         style="max-width:560px;width:100%;font-family:{SANS};">
    <tr><td style="padding:0 4px 16px;font-size:22px;font-weight:600;color:{INK};">
      <span style="color:{ORANGE};">&#9679;</span> corgi
      <span style="font-family:{SERIF};font-style:italic;color:{ORANGE};font-weight:400;">
        policy admin</span>
    </td></tr>
    <tr><td style="background:#ffffff;border:1px solid {LINE};border-radius:8px;padding:28px;">
      <span style="display:inline-block;padding:4px 10px;border-radius:999px;
                   background:{badge_bg};color:{badge_fg};font-size:12px;font-weight:600;">
        {escape(label)}</span>
      <h1 style="margin:14px 0 16px;font-size:22px;line-height:1.3;color:{INK};font-weight:600;">
        {escape(subject)}</h1>
      {paras}
      <table role="presentation" cellspacing="0" cellpadding="0" style="margin-top:8px;"><tr>
        <td style="background:{ORANGE};border-radius:8px;">
          <a href="{escape(portal_url)}" style="display:inline-block;padding:11px 20px;
             color:#ffffff;text-decoration:none;font-size:14px;font-weight:600;">
             Open your portal</a>
        </td></tr></table>
    </td></tr>
    <tr><td style="padding:16px 4px;font-size:12px;line-height:1.5;color:{MUTED};">
      Demo environment: Stripe test mode, fictional data. Every amount in this email is
      traceable line by line in your portal.
    </td></tr>
  </table>
</td></tr></table>
</body></html>"""


def html_with_note(html: str, note: str) -> str:
    """Insert a small demo banner above the card (used when an email is redirected)."""
    banner = (
        f'<tr><td style="padding:0 4px 12px;font-size:12px;line-height:1.5;color:#cc4a00;">'
        f"{escape(note)}</td></tr>"
    )
    marker = '<tr><td style="background:#ffffff;'
    return html.replace(marker, banner + marker, 1)
