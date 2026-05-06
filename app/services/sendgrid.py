"""
app/services/sendgrid.py
Async SendGrid via httpx — NPE actual email templates ported from PHP
"""

import os
import httpx
from datetime import datetime

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
FROM_EMAIL       = os.getenv("FROM_EMAIL", "confirmations@nationalparkexpress.com")
FROM_NAME        = os.getenv("FROM_NAME",  "National Park Express")
BASE_URL         = os.getenv("BASE_URL",   "https://confirm.nationalparkexpress.com")

LOGO_URL = "https://nationalparkexpress.com/wp-content/uploads/2026/03/image002.png"


# ── Internal helpers ──────────────────────────────────────────────────────────

def _wrap(inner: str) -> str:
    """Standard NPE email wrapper — matches PHP npe_ops_email_wrap."""
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f8;padding:30px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">
  <tr><td style="background:#1a3a5c;border-radius:12px 12px 0 0;padding:32px;text-align:center;">
    <img src="{LOGO_URL}" style="width:120px;height:auto;margin-bottom:12px;" />
  </td></tr>
  <tr><td style="background:#fff;padding:32px;">{inner}</td></tr>
  <tr><td style="background:#f0f0f0;border-radius:0 0 12px 12px;padding:16px;text-align:center;">
    <p style="color:#aaa;font-size:12px;margin:0;">National Park Express — Thank you for choosing us! 🏞️</p>
  </td></tr>
</table></td></tr></table></body></html>"""


async def _send(to_email: str, subject: str, html: str,
                attachments: list[dict] | None = None) -> dict:
    """Raw SendGrid v3 send via httpx."""
    if not SENDGRID_API_KEY:
        raise RuntimeError("SENDGRID_API_KEY not set")

    payload: dict = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": FROM_EMAIL, "name": FROM_NAME},
        "subject": subject,
        "content": [{"type": "text/html", "value": html}],
    }
    if attachments:
        payload["attachments"] = attachments

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://api.sendgrid.com/v3/mail/send",
            json=payload,
            headers={"Authorization": f"Bearer {SENDGRID_API_KEY}"},
        )

    if resp.status_code in (200, 202):
        return {"message_id": resp.headers.get("X-Message-Id", "sent")}
    raise RuntimeError(f"SendGrid error {resp.status_code}: {resp.text[:300]}")


def _fmt_date(d) -> str:
    if d is None:
        return "TBD"
    if isinstance(d, str):
        try:
            return datetime.strptime(d, "%Y-%m-%d").strftime("%B %-d, %Y")
        except ValueError:
            return d
    return d.strftime("%B %-d, %Y")


def _fmt_time(t) -> str:
    if t is None:
        return "TBD"
    if isinstance(t, str):
        return t
    return t.strftime("%-I:%M %p")


# ── Tour config helper ────────────────────────────────────────────────────────

from app.services.tour_config import TOUR_TYPES


# ── Tour Confirmation Email ───────────────────────────────────────────────────

async def send_confirmation_email(booking, pickup_info: dict | None = None) -> dict:
    """
    Tour Confirmation email — matches PHP npe_tconf_build_email exactly.
    booking: Booking ORM object
    pickup_info: {"instruction": str, "photo_url": str, "photo_label": str}
    """
    tour_config  = TOUR_TYPES.get(booking.tour_type or "", list(TOUR_TYPES.values())[0])
    pickup_info  = pickup_info or {}
    confirm_url  = f"{BASE_URL}/confirm/{booking.confirm_token}"
    tour_date_f  = _fmt_date(booking.tour_date)
    pickup_time  = _fmt_time(booking.pickup_time)
    ploc         = booking.pickup_location or ""
    photo_url    = pickup_info.get("photo_url", "")

    pickup_cell = (
        f'<a href="{photo_url}" style="color:#1a3a5c;font-weight:bold;">'
        f'{ploc} Pickup location - click here for detail</a>'
        if photo_url
        else (pickup_info.get("instruction") or f"Please arrive at <strong>{ploc}</strong>")
    )

    fee_html = ""
    if tour_config.get("has_park_fee"):
        fee_html = """<div style="background:#fff8e1;border:1px solid #f0d080;border-radius:6px;padding:14px;margin:16px 0;">
        <ul style="margin:8px 0 0;padding-left:18px;font-size:13px;color:#555;">
        <li><strong>Non-U.S. Residents fee (ages 16+):</strong> $100/person or $250 America the Beautiful Annual Pass (up to 4 people).</li>
        <li><strong>Legal U.S. residents:</strong> Present valid government-issued ID to waive the $100 fee.</li>
        </ul></div>"""

    lunch_html = ""
    if tour_config.get("has_lunch"):
        beef_col = (
            '<td style="text-align:center;"><div style="font-size:28px;">🥩</div>'
            '<div style="font-size:12px;color:#555;">Beef<br>Sandwich</div></td>'
            if tour_config.get("has_beef") else ""
        )
        lunch_html = f"""<div style="background:#fffbf0;border:1px solid #f0d080;border-radius:8px;padding:16px;margin:20px 0;">
        <p style="margin:0 0 10px;font-weight:bold;color:#8a6000;">🥪 Available lunch options:</p>
        <table width="100%" cellpadding="4"><tr>
          <td style="text-align:center;"><div style="font-size:28px;">🦃</div><div style="font-size:12px;color:#555;">Turkey<br>Sandwich</div></td>
          <td style="text-align:center;"><div style="font-size:28px;">🥗</div><div style="font-size:12px;color:#555;">Veggie<br>Sandwich</div></td>
          {beef_col}
        </tr></table>
        <p style="margin:8px 0 0;font-size:12px;color:#999;text-align:center;">Default is Turkey Sandwich if no selection received.</p>
        </div>"""

    label = tour_config["label"]
    inner = f"""
    <h1 style="color:#1a3a5c;font-size:22px;margin:0 0 4px;">Tour Confirmation &amp; Lunch Selection</h1>
    <p style="color:#a8c4e0;margin:0 0 20px;font-size:14px;">{label}</p>
    <p style="font-size:16px;">Hi <strong>{booking.first_name}</strong>,</p>
    <p style="color:#555;line-height:1.6;margin:10px 0 20px;">Your tour is scheduled for
      <strong style="color:#1a3a5c;">{tour_date_f}</strong>. Please confirm your attendance.</p>
    <table width="100%" cellpadding="0" cellspacing="0"
           style="background:#f0f5ff;border-radius:8px;overflow:hidden;margin-bottom:16px;">
      <tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;background:#e8f0ff;width:38%;">📋 Order #</td>
          <td style="padding:10px 16px;font-size:13px;">{booking.order_number}</td></tr>
      <tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;background:#e8f0ff;">👥 Party Size</td>
          <td style="padding:10px 16px;font-size:13px;">{booking.quantities} Guest(s)</td></tr>
      <tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;">📅 Tour Date</td>
          <td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#1a3a5c;">{tour_date_f}</td></tr>
      <tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;background:#e8f0ff;">⏰ Pickup Time</td>
          <td style="padding:10px 16px;font-size:13px;font-weight:bold;">{pickup_time}</td></tr>
      <tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;">📍 Pickup Location</td>
          <td style="padding:10px 16px;font-size:13px;">{pickup_cell}</td></tr>
    </table>
    {fee_html}
    <p style="color:#555;font-size:14px;margin:16px 0;">You will choose your lunch option after clicking the button below.</p>
    {lunch_html}
    <div style="text-align:center;margin:28px 0;">
      <a href="{confirm_url}" style="display:inline-block;background:#1a3a5c;color:#fff;
         text-decoration:none;padding:16px 44px;border-radius:8px;font-size:16px;font-weight:bold;">
         ✅ Confirm My Tour</a>
      <p style="margin:10px 0 0;font-size:12px;color:#aaa;">Link expires at 6:00 PM PST the day before your tour</p>
    </div>
    <p style="color:#999;font-size:12px;text-align:center;">
      Questions? <a href="mailto:reservations@nationalparkexpress.com"
      style="color:#1a3a5c;">reservations@nationalparkexpress.com</a> | 702-948-4190</p>"""

    subject = f"Tour Confirmation — {label} — {tour_date_f}"
    return await _send(booking.customer_email, subject, _wrap(inner))


# ── Morning Reminder Email ────────────────────────────────────────────────────

async def send_morning_reminder_email(booking) -> dict:
    """Morning pickup reminder — matches PHP npe_morning_email."""
    from urllib.parse import quote
    pickup_time = _fmt_time(booking.pickup_time)
    van_key     = booking.vehicle_no or booking.driver or ""
    track_url   = (
        f"{BASE_URL}/?van={quote(van_key)}"
        f"&order={quote(booking.order_number or '')}"
        f"&name={quote(booking.first_name or '')}"
        f"&phone={quote(booking.phone or '')}"
    )
    support = os.getenv("SUPPORT_PHONE", "702-948-4190")

    inner = f"""
    <p style="font-size:16px;">Hi <strong>{booking.first_name}</strong>,</p>
    <p style="color:#555;line-height:1.7;">
      This is a reminder that your pickup time for today's tour is
      <strong style="color:#1a3a5c;">{pickup_time}</strong>.
    </p>
    <p style="color:#555;line-height:1.7;">
      Please use the link below to check in when you arrive at your pickup location
      and to track your vehicle in real time:
    </p>
    <div style="text-align:center;margin:28px 0;">
      <a href="{track_url}" style="display:inline-block;background:#1a3a5c;color:#fff;
         text-decoration:none;padding:14px 40px;border-radius:8px;font-size:15px;font-weight:bold;">
         Check In &amp; Track Vehicle</a>
    </div>
    <p style="color:#999;font-size:12px;text-align:center;">
      If you need assistance, please call {support}</p>"""

    subject = f"Your Pickup Reminder — {pickup_time}"
    return await _send(booking.customer_email, subject, _wrap(inner))


# ── Ticket Reminder Email ────────────────────────────────────────────────────

async def send_ticket_reminder_email(booking) -> dict:
    """Ticket reminder for self-drive / Antelope Canyon guests."""
    tour_date_f  = _fmt_date(booking.tour_date)
    checkin_time = _fmt_time(booking.checkin_time)
    tour_time    = _fmt_time(booking.tour_time)
    cfg = TOUR_TYPES.get(booking.tour_type or "", {})
    label = cfg.get("sms_label") or cfg.get("label", booking.tour_type or "Tour")
    inner = f"""
    <h2 style="color:#1a3a5c;margin:0 0 16px;">Your {label} Reminder</h2>
    <p style="font-size:16px;">Hi <strong>{booking.first_name}</strong>,</p>
    <p style="color:#555;line-height:1.6;margin:10px 0 20px;">
      This is a reminder for your upcoming tour. Please review the details below.</p>
    <table width="100%" cellpadding="0" cellspacing="0"
           style="background:#f0f5ff;border-radius:8px;overflow:hidden;margin-bottom:16px;">
      <tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;background:#e8f0ff;width:40%;">📋 Order #</td>
          <td style="padding:10px 16px;font-size:13px;">{booking.order_number}</td></tr>
      <tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;">🎫 Confirmation #</td>
          <td style="padding:10px 16px;font-size:13px;">{booking.confirmation_no or "—"}</td></tr>
      <tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;background:#e8f0ff;">📅 Service Date</td>
          <td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#1a3a5c;">{tour_date_f}</td></tr>
      <tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;">⏰ Check-in Time</td>
          <td style="padding:10px 16px;font-size:13px;font-weight:bold;">{checkin_time}</td></tr>
      <tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;background:#e8f0ff;">🎡 Tour Time</td>
          <td style="padding:10px 16px;font-size:13px;">{tour_time}</td></tr>
      <tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;">👥 Party Size</td>
          <td style="padding:10px 16px;font-size:13px;">{booking.quantities} Guest(s)</td></tr>
      <tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;background:#e8f0ff;">📍 Location</td>
          <td style="padding:10px 16px;font-size:13px;">{booking.tour_location or "—"}</td></tr>
    </table>
    <p style="color:#999;font-size:12px;text-align:center;">
      Questions? <a href="mailto:reservations@nationalparkexpress.com"
      style="color:#1a3a5c;">reservations@nationalparkexpress.com</a> | 702-948-4190</p>"""

    subject = f"Your {label} Reminder — {tour_date_f}"
    return await _send(booking.customer_email, subject, _wrap(inner))


# ── Staff Notification ────────────────────────────────────────────────────────

async def send_staff_notification(booking, conf: str,
                                  turkey: int = 0, veggie: int = 0, beef: int = 0,
                                  notes: str = "", submission_count: int = 1) -> dict:
    """
    Staff notification when guest confirms — matches PHP npe_tconf_notify.
    conf: "yes" | "modify_req"
    """
    tour_config  = TOUR_TYPES.get(booking.tour_type or "", list(TOUR_TYPES.values())[0])
    tour_date_f  = _fmt_date(booking.tour_date)
    label        = tour_config["label"]
    color        = "#27ae60" if conf == "yes" else "#e67e22"
    is_repeat    = conf == "modify_req" and submission_count >= 2
    conf_display = ("MODIFY" if conf == "modify_req" else conf.upper()) + (" ★" if is_repeat else "")

    lunch_row = ""
    if tour_config.get("has_lunch") and conf == "yes":
        lunch_row = (
            f"<tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;'>🥪 Lunch</td>"
            f"<td style='padding:8px 12px;'>Turkey:{turkey} Veggie:{veggie} Beef:{beef}</td></tr>"
        )

    notes_html = notes.replace("\n", "<br>") if notes else "—"

    body = f"""<div style='font-family:Arial,sans-serif;max-width:600px;'>
    <h2 style='color:#1a5276;'>Guest Confirmation Received</h2>
    <table style='width:100%;border-collapse:collapse;border:1px solid #ddd;'>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;'>Tour</td><td style='padding:8px 12px;'>{label}</td></tr>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;'>Date</td><td style='padding:8px 12px;'>{tour_date_f}</td></tr>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;'>Order #</td><td style='padding:8px 12px;'>{booking.order_number}</td></tr>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;'>Guest</td><td style='padding:8px 12px;'>{booking.first_name} {booking.last_name}</td></tr>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;'>Email</td><td style='padding:8px 12px;'>{booking.customer_email}</td></tr>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;'>Phone</td><td style='padding:8px 12px;'>{booking.phone or "—"}</td></tr>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;'>Pickup</td><td style='padding:8px 12px;'>{booking.pickup_time} @ {booking.pickup_location}</td></tr>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;'>Party</td><td style='padding:8px 12px;'>{booking.quantities}</td></tr>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;'>Confirmation</td>
        <td style='padding:8px 12px;font-size:22px;font-weight:bold;color:{color};'>{conf_display}</td></tr>
    {lunch_row}
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;vertical-align:top;'>Notes</td>
        <td style='padding:8px 12px;'>{notes_html}</td></tr>
    </table></div>"""

    to      = "reservations@nationalparkexpress.com" if conf == "modify_req" else "confirmations@nationalparkexpress.com"
    subject = f"[Tour] {booking.order_number} – {conf_display} – {label} – {tour_date_f}"
    return await _send(to, subject, body)


# ── Raw send (used by scheduler) ─────────────────────────────────────────────

async def send_raw_email(to_email: str, to_name: str, subject: str,
                         html_body: str, attachments: list[dict] | None = None) -> dict:
    return await _send(to_email, subject, html_body, attachments)
