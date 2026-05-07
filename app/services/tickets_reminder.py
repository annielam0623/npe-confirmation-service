"""
NPE — Tickets Reminder service layer
Shared by send_tickets.py, tracking_tickets.py, guest.py

Contains:
  - TOUR_TYPES (9 Antelope Canyon operators)
  - Token make/verify
  - SMS / Email builders
  - Staff notification email
  - Guest confirmation page HTML renderer
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_LA = ZoneInfo("America/Los_Angeles")
from html import escape

SECRET_KEY       = os.environ.get("TOKEN_SECRET", "npe_tix_secret_fallback")
CONFIRM_BASE_URL = os.environ.get("SERVICE_BASE_URL", "https://confirm.nationalparkexpress.com")

# ── Tour types ────────────────────────────────────────────────────────────────
TOUR_TYPES: dict[str, dict] = {
    "upper_antelope_tsosie": {
        "label":            "Upper Antelope Canyon – Chief Tsosie Tours",
        "sms_label":        "Upper Antelope Canyon Tour",
        "abbr":             "U-TC",
        "checkin_location": "Antelope Slot Canyon Tours, 148 6th Ave, Page, AZ 86040",
        "maps_url":         "https://goo.gl/maps/t8e9E9uioEWG9zHn7",
        "location_photo":   "https://maps.app.goo.gl/DiwJPosKMWNXzrH3A",
        "extra_notes": [
            "★ No children, toddlers or infants (ages 0–5) are permitted due to safety concerns.",
            "Antelope Canyon does not allow any bags on the walking tour. Please leave them in your vehicle.",
        ],
        "prepare_steps": [],
    },
    "upper_antelope_brenda": {
        "label":            "Upper Antelope Canyon – Brenda (Tse Bighanilini Tours)",
        "sms_label":        "Upper Antelope Canyon Tour",
        "abbr":             "U-BR",
        "checkin_location": "Tse Bighanilini Tours, Highway 98, Milepost 299.8, Page, AZ 86040 (Between 299 and 300)",
        "maps_url":         "https://maps.app.goo.gl/kcixg7Hee9WMMt3h8",
        "location_photo":   "https://maps.app.goo.gl/3meJhQqfCAAt9Ayp7",
        "extra_notes": [
            "Car seats are required for children under 4. Visitors must provide their own car seat or booster seat.",
            "Antelope Canyon does not allow any bags on the walking tour. Please leave them in your vehicle.",
        ],
        "prepare_steps": [
            {"label": "Sign the required waiver form",
             "url": "https://fareharbor.com/waivers?shortname=tsebighanilini&bookingUuid=4487ab4e-7d05-4cea-860b-b7da6ab47df6&source=copy-link"},
            {"label": "Pay the permit fee using the provided payment link",
             "url": "https://fareharbor.com/embeds/book/navajonationparks/items/691331/calendar/2026/01/",
              "note":  "For all guests, please keep your payment receipt for check-in. Same-day Lower Antelope or Canyon X receipts can waive the Upper Antelope permit fee. If we supplied your tickets, we can provide the receipt — just let us know."},
        ],
    },
     "upper_antelope_brenda_no_fee": {
        "label":            "Upper Antelope Canyon – Brenda (Tse Bighanilini Tours)",
        "sms_label":        "Upper Antelope Canyon Tour",
        "abbr":             "U-BR",
        "checkin_location": "Tse Bighanilini Tours, Highway 98, Milepost 299.8, Page, AZ 86040 (Between 299 and 300)",
        "maps_url":         "https://maps.app.goo.gl/kcixg7Hee9WMMt3h8",
        "location_photo":   "https://maps.app.goo.gl/3meJhQqfCAAt9Ayp7",
        "extra_notes": [
            "Car seats are required for children under 4. Visitors must provide their own car seat or booster seat.",
            "Antelope Canyon does not allow any bags on the walking tour. Please leave them in your vehicle.",
        ],
        "prepare_steps": [
            {"label": "Sign the required waiver form",
             "url": "https://fareharbor.com/waivers?shortname=tsebighanilini&bookingUuid=4487ab4e-7d05-4cea-860b-b7da6ab47df6&source=copy-link"},
        ],
    },
    "upper_antelope_aact": {
        "label":            "Upper Antelope Canyon – The Adventurous Group (AACT)",
        "sms_label":        "Upper Antelope Canyon Tour",
        "abbr":             "U-AA",
        "checkin_location": "Adventurous Antelope Canyon, Highway 98 Road & Milepost 302, Page, AZ 86040",
        "maps_url":         "https://maps.app.goo.gl/hWXU2JSLSphMda529",
        "location_photo":   "https://maps.app.goo.gl/tZttDC6G3jctLC8E7",
        "extra_notes": [
            "★ Minimum age 8. Guests must be at least 8 years of age to join the walking tour.",
            "★ Pregnant guests are not permitted to participate due to safety concerns.",
            "Antelope Canyon does not allow any bags on the walking tour. Please leave them in your vehicle.",
        ],
        "prepare_steps": [],
    },
    "upper_antelope_hogan_transport": {
        "label":            "Upper Antelope Canyon – Hogan with Transport",
        "sms_label":        "Upper Antelope Hogan Tour",
        "abbr":             "U-HT",
        "checkin_location": "Antelope Hogan Canyon Tours, LLC, 302 SR-98 (7 miles east of Page), Page, AZ 86040",
        "maps_url":         "https://maps.app.goo.gl/DgmwCEepZbNLRn7A6",
        "location_photo":   "https://maps.app.goo.gl/DztGqAk8b9pUp8EV7",
        "extra_notes": [
            "Car seats are required for children under 8. Visitors must provide their own car seat.",
            "★ These entry reservations are non-refundable.",
            "Antelope Canyon does not allow any bags on the walking tour. Please leave them in your vehicle.",
            "If you can't find the check-in location, call: 928-693-9293",
        ],
        "prepare_steps": [
            {"label": "Pay the permit fee using the provided payment link",
             "url":   "https://fareharbor.com/embeds/book/navajonationparks/items/691331/calendar/2026/01/",
             "note":  "For all guests, please keep your payment receipt for check-in. Same-day Lower Antelope or Canyon X receipts can waive the Upper Antelope permit fee. If we supplied your tickets, we can provide the receipt — just let us know."},
        ],
    },
    "upper_antelope_hogan_hiking": {
        "label":            "Upper Antelope Canyon – Hogan Hiking Tour",
        "sms_label":        "Upper Antelope Hiking Tour",
        "abbr":             "U-HH",
        "checkin_location": "Antelope Hogan Canyon Tours, LLC, 302 SR-98 (7 miles east of Page), Page, AZ 86040",
        "maps_url":         "https://maps.app.goo.gl/DgmwCEepZbNLRn7A6",
        "location_photo":   "https://maps.app.goo.gl/DztGqAk8b9pUp8EV7",
        "extra_notes": [
            "★ Minimum age 8. Guests must be at least 8 years of age to join the hiking tour.",
            "★ Pregnant guests are not permitted to participate due to safety concerns.",
            "★ These entry reservations are non-refundable.",
            "Prepare for a 2-mile round-trip hike. Bring plenty of water.",
            "Antelope Canyon does not allow any bags on the walking tour. Please leave them in your vehicle.",
            "If you can't find the check-in location, call: 928-693-9293",
        ],
        "prepare_steps": [
            {"label": "Pay the permit fee using the provided payment link",
             "url":   "https://fareharbor.com/embeds/book/navajonationparks/items/691331/calendar/2026/01/",
             "note":  "For all guests, please keep your payment receipt for check-in. Same-day Lower Antelope or Canyon X receipts can waive the Upper Antelope permit fee. If we supplied your tickets, we can provide the receipt — just let us know."},
        ],
    },
    "lower_antelope_kens": {
        "label":            "Lower Antelope Canyon – Ken's Tours",
        "sms_label":        "Lower Antelope Canyon Tour",
        "abbr":             "L-KT",
        "checkin_location": "Ken's Tours, Indian Rte 222, Page, AZ 86040",
        "maps_url":         "https://maps.app.goo.gl/ZU25jjWDLPGVbKau9",
        "location_photo":   "https://goo.gl/maps/q5tH4CB2LFnNPk2w6",
        "extra_notes": [
            "★ These entry reservations are non-refundable.",
            "Antelope Canyon does not allow any bags on the walking tour. Please leave them in your vehicle.",
        ],
        "prepare_steps": [],
    },
    "lower_antelope_dixie": {
        "label":            "Lower Antelope Canyon – Dixie's Tours",
        "sms_label":        "Lower Antelope Canyon Tour",
        "abbr":             "L-DX",
        "checkin_location": "Dixie's Lower Antelope Canyon Tours, Indian Rte 222, Page, AZ 86040",
        "maps_url":         "https://goo.gl/maps/BbaUrHrV3aa5Wiw59",
        "location_photo":   "https://goo.gl/maps/QJ28NgUR8iSCf9AC7",
        "extra_notes": [
            "★ These entry reservations are non-refundable.",
            "Antelope Canyon does not allow any bags on the walking tour. Please leave them in your vehicle.",
        ],
        "prepare_steps": [],
    },
    "canyon_x": {
        "label":            "Antelope Canyon X – Taadidiin Tours",
        "sms_label":        "Canyon X Tour",
        "abbr":             "X-TT",
        "checkin_location": "Antelope Canyon X by Taadidiin Tours, MP 308 SR 98, Page, AZ 86040",
        "maps_url":         "https://goo.gl/maps/pzJmUPtykxCDzUi97",
        "location_photo":   "https://goo.gl/maps/FyBq5gGTs9ZcKebu9",
        "extra_notes": [
            "No entry for children who do not have their own car seat for children under 8 years of age, under 4'9\" (145cm), or under 80 lbs (36.3kg).",
            "Antelope Canyon does not allow any bags on the walking tour. Please leave them in your vehicle.",
        ],
        "prepare_steps": [],
    },
    "rattlesnake_aact": {
        "label":            "Rattlesnake Canyon Tour – The Adventurous Group",
        "sms_label":        "Rattlesnake Canyon Tour",
        "abbr":             "R-AA",
        "checkin_location": "Adventurous Antelope Canyon, Highway 98 Road & Milepost 302, Page, AZ 86040",
        "maps_url":         "https://maps.app.goo.gl/hWXU2JSLSphMda529",
        "location_photo":   "https://maps.app.goo.gl/tZttDC6G3jctLC8E7",
        "extra_notes": [
            "★ Minimum age 8. Guests must be at least 8 years of age to join the walking tour.",
            "★ Pregnant guests are not permitted to participate due to safety concerns.",
            "Antelope Canyon does not allow any bags on the walking tour. Please leave them in your vehicle.",
        ],
        "prepare_steps": [],
    },
}

# ── Token ─────────────────────────────────────────────────────────────────────
def make_token(record_id: int, email: str, service_date: str) -> str:
    if service_date:
        try:
            sd = datetime.strptime(service_date, "%Y-%m-%d")
            expires = int(datetime(sd.year, sd.month, sd.day, 23, 59, 59, tzinfo=_LA).timestamp())
        except ValueError:
            expires = int(time.time()) + 7 * 86400
    else:
        expires = int(time.time()) + 7 * 86400
    payload = f"{record_id}|{email}|{expires}"
    sig = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.b64encode(f"{record_id}:{expires}:{sig}".encode()).decode()


def confirm_url(token: str, src: str = "email") -> str:
    return f"{CONFIRM_BASE_URL}/confirm/tickets?token={token}&src={src}&npe_tix_autoyes=1"


async def verify_token(token: str, db) -> tuple[str | None, dict | None]:
    if not token:
        return "invalid", None
    try:
        raw = base64.b64decode(token.encode()).decode()
        record_id_str, expires_str, sig = raw.split(":", 2)
        record_id = int(record_id_str)
        expires   = int(expires_str)
    except Exception:
        return "invalid", None
    if time.time() > expires:
        return "expired", None
    from sqlalchemy import text
    result = await db.execute(text("SELECT * FROM tickets_reminders WHERE id = :id"), {"id": record_id})
    row = result.mappings().fetchone()
    if not row:
        return "invalid", None
    row = dict(row)
    expected = hmac.new(SECRET_KEY.encode(), f"{record_id}|{row['customer_email']}|{expires}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return "invalid", None
    return None, row


# ── SMS builder ───────────────────────────────────────────────────────────────
def build_sms(row: dict, tour_type: str, form_url: str) -> str:
    cfg       = TOUR_TYPES.get(tour_type, {})
    sms_label = cfg.get("sms_label", cfg.get("label", tour_type))
    first     = row.get("first_name", row.get("name", ""))
    checkin   = row.get("checkin_time", "")
    tour_time = row.get("tour_time", "")
    svc_date  = row.get("service_date", row.get("tour_date", ""))
    try:
        date_fmt = datetime.strptime(svc_date, "%Y-%m-%d").strftime("%B %-d, %Y")
    except ValueError:
        date_fmt = svc_date
    return (
        f"Dear {first}, reminder for your {sms_label} on {date_fmt}. "
        f"Check-in: {checkin}, Tour: {tour_time}. "
        f"Please use the link below to review important information and reconfirm your booking: {form_url} "
        f"Questions? Call 702-948-4190."
    )


# ── Email builder ─────────────────────────────────────────────────────────────
def build_email(row: dict, tour_type: str, service_date: str, form_url: str) -> str:
    cfg        = TOUR_TYPES.get(tour_type, {})
    label      = cfg.get("sms_label") or cfg.get("label", tour_type)
    first      = row.get("first_name", "")
    last       = row.get("last_name", "")
    chd        = row.get("chd_number") or row.get("order_number", "")
    cfm        = row.get("confirmation_no", "")
    pax        = row.get("quantities", "1")
    checkin    = row.get("checkin_time", "")
    tour_time  = row.get("tour_time", "")
    checkin_loc = cfg.get("checkin_location", "")
    maps_url   = cfg.get("maps_url", "")
    location_photo = cfg.get("location_photo", "")
    try:
        date_fmt = datetime.strptime(service_date, "%Y-%m-%d").strftime("%B %-d, %Y")
    except ValueError:
        date_fmt = service_date

    maps_row = (
        f'<tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;background:#e8f0ff;">🗺️ Maps</td>'
        f'<td style="padding:10px 16px;font-size:13px;"><a href="{maps_url}" style="color:#1a3a5c;" target="_blank">Google Maps GPS</a></td></tr>'
    ) if maps_url else ""

    resource_html = (
        f'<p style="font-size:12px;margin-top:8px;text-align:center;">'
        f'<a href="https://www.timeanddate.com/worldclock/usa/page" style="color:#1a3a5c;" target="_blank">🕐 Local Time &amp; Weather</a>'
        f'&nbsp;&nbsp;<a href="{location_photo}" style="color:#1a3a5c;margin-left:16px;" target="_blank">📸 Location Photo</a></p>'
    ) if location_photo else ""


    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f8;padding:30px 0;"><tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">
  <tr><td style="background:#1a3a5c;border-radius:12px 12px 0 0;padding:32px;text-align:center;">
    <img src="https://nationalparkexpress.com/wp-content/uploads/2026/03/image002.png" style="width:120px;height:auto;margin-bottom:12px;" />
    <h1 style="color:#fff;margin:10px 0 4px;font-size:22px;">Tickets Reminder &amp; Reconfirmation</h1>
    <p style="color:#a8c4e0;margin:0;font-size:14px;">{label}</p>
  </td></tr>
  <tr><td style="background:#fff;padding:32px;">
    <p style="font-size:16px;">Hi <strong>{first} {last}</strong>,</p>
    <p style="color:#555;line-height:1.6;margin:10px 0 20px;">This is a reminder for your upcoming Antelope Canyon tour. Please reconfirm your attendance using the button below.</p>
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f5ff;border-radius:8px;overflow:hidden;margin-bottom:20px;">
      <tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;background:#e8f0ff;width:38%;">📋 CHD#</td><td style="padding:10px 16px;font-size:13px;">{chd}</td></tr>
      <tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;">🔖 Confirmation#</td><td style="padding:10px 16px;font-size:13px;font-weight:bold;">{cfm}</td></tr>
      <tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;background:#e8f0ff;">👥 Party Size</td><td style="padding:10px 16px;font-size:13px;">{pax} Guest(s)</td></tr>
      <tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;">📅 Service Date</td><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#1a3a5c;">{date_fmt}</td></tr>
      <tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;background:#e8f0ff;">⏰ Check-in Time</td><td style="padding:10px 16px;font-size:13px;font-weight:bold;">{checkin}</td></tr>
      <tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;">🎡 Tour Time</td><td style="padding:10px 16px;font-size:13px;font-weight:bold;">{tour_time}</td></tr>
      <tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;background:#e8f0ff;">📍 Check-in Location</td><td style="padding:10px 16px;font-size:13px;">{checkin_loc}</td></tr>
      {maps_row}
    </table>
    <div style="background:#fff5f5;border:1px solid #f5c6c6;border-radius:6px;padding:8px 14px;margin-bottom:20px;font-size:11px;color:#c0392b;line-height:1.6;">
      ★ Late check-in is subject to forfeiting your tour entry.<br>
      ★ All times are based on the Arizona (AZ) time zone.
    </div>
    <p style="color:#555;line-height:1.6;margin-bottom:20px;">Please click the &ldquo;Reconfirm My Tour &amp; Continue&rdquo; button below to review important information about your tour. This may include the check-in procedure, supplier rules, age requirements, local regulations, and other important notes to help you prepare for your trip.</p>
    <div style="text-align:center;margin:28px 0;">
      <a href="{form_url}" style="display:inline-block;background:#1a3a5c;color:#fff;text-decoration:none;padding:16px 44px;border-radius:8px;font-size:16px;font-weight:bold;">Reconfirm My Tour &amp; Continue</a>
      <p style="margin:10px 0 0;font-size:12px;color:#aaa;">Link expires the day after your tour</p>
    </div>
    {resource_html}
    <p style="color:#999;font-size:12px;text-align:center;margin-top:16px;">Questions? <a href="mailto:reservations@nationalparkexpress.com" style="color:#1a3a5c;">reservations@nationalparkexpress.com</a> | 702-948-4190</p>
  </td></tr>
  <tr><td style="background:#f0f0f0;border-radius:0 0 12px 12px;padding:16px;text-align:center;">
    <p style="color:#aaa;font-size:12px;margin:0;">National Park Express — Thank you for choosing us! 🏞️</p>
  </td></tr>
</table></td></tr></table></body></html>"""


# ── Staff notification email ───────────────────────────────────────────────────
def build_staff_email(row: dict, tour_type: str, notes: str) -> tuple[str, str]:
    cfg      = TOUR_TYPES.get(tour_type, {})
    label    = cfg.get("label") or cfg.get("sms_label", tour_type)  # internal: show supplier
    svc_date = str(row.get("service_date", ""))
    try:
        date_str = datetime.strptime(svc_date, "%Y-%m-%d").strftime("%B %-d, %Y")
    except ValueError:
        date_str = svc_date
    notes_html = notes.replace("\n", "<br>") if notes else "-"
    chd        = row.get("chd_number", "")
    subject    = f"[Tickets] {chd} – YES – {label} – {date_str}"
    body = f"""<div style='font-family:Arial,sans-serif;max-width:600px;'>
    <h2 style='color:#1a5276;'>Guest Reconfirmation Received</h2>
    <table style='width:100%;border-collapse:collapse;border:1px solid #ddd;'>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;'>Tour</td><td style='padding:8px 12px;'>{label}</td></tr>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;'>Service Date</td><td style='padding:8px 12px;'>{date_str}</td></tr>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;'>CHD#</td><td style='padding:8px 12px;'>{chd}</td></tr>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;'>Confirmation#</td><td style='padding:8px 12px;'>{row.get("confirmation_no","")}</td></tr>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;'>Guest</td><td style='padding:8px 12px;'>{row.get("first_name","")} {row.get("last_name","")}</td></tr>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;'>Email</td><td style='padding:8px 12px;'>{row.get("customer_email","")}</td></tr>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;'>Phone</td><td style='padding:8px 12px;'>{row.get("phone","")}</td></tr>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;'>Party Size</td><td style='padding:8px 12px;'>{row.get("no_of_pax","")}</td></tr>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;'>Response</td><td style='padding:8px 12px;font-size:22px;font-weight:bold;color:#27ae60;'>YES</td></tr>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;vertical-align:top;'>Notes</td><td style='padding:8px 12px;'>{notes_html}</td></tr>
    </table></div>"""
    return subject, body


# ── Guest page CSS ────────────────────────────────────────────────────────────
GUEST_CSS = """*{box-sizing:border-box;margin:0;padding:0;}body{background:#f0f4f8;font-family:"Helvetica Neue",Arial,sans-serif;color:#333;padding:16px;}
.gf-wrap{max-width:580px;margin:0 auto;padding:10px 0 40px;}.gf-card{background:#fff;border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,.10);overflow:hidden;}
.gf-header{background:#1a3a5c;color:#fff;padding:26px;text-align:center;}.gf-header h1{font-size:20px;margin:8px 0 4px;}
.gf-tour-badge{background:rgba(255,255,255,.15);border-radius:6px;padding:5px 14px;display:inline-block;font-size:13px;font-weight:bold;margin-bottom:6px;}
.gf-date{font-size:17px;font-weight:bold;color:#fff;margin:4px 0;}.gf-meta{font-size:12px;color:#a8c4e0;margin-top:4px;}
.gf-pickup-box{padding:16px 22px;font-size:13px;line-height:1.6;background:#eef6ff;border-bottom:1px solid #d0e6ff;}
.gf-box-title{font-weight:bold;color:#1a3a5c;margin-bottom:10px;}
.gf-row{display:flex;gap:10px;align-items:flex-start;margin-bottom:8px;}.gf-row span:first-child{flex-shrink:0;width:20px;text-align:center;}
.gf-pickup-box a{color:#1a3a5c;font-weight:bold;}
.gf-section{padding:18px 22px;border-bottom:1px solid #eee;}.gf-section h2{font-size:15px;color:#1a3a5c;margin-bottom:12px;}.gf-opt{font-weight:normal;font-size:12px;color:#aaa;}
.gf-reminders{background:#f9f9f9;border-top:1px solid #eee;padding:14px 22px;font-size:13px;}.gf-reminders ul{padding-left:18px;line-height:1.9;color:#555;}
.gf-section textarea{width:100%;border:1px solid #ddd;border-radius:8px;padding:10px;font-size:13px;resize:vertical;}
.gf-submit{padding:18px 22px;text-align:center;}.gf-btn{width:100%;background:#1a3a5c;color:#fff;border:none;padding:15px;border-radius:10px;font-size:16px;font-weight:bold;cursor:pointer;}.gf-btn:hover{background:#0f2440;}
.gf-small{font-size:12px;color:#888;margin-top:10px;}.gf-small a{color:#1a3a5c;}
.gf-error{background:#f8d7da;color:#721c24;border:1px solid #f5c6cb;border-radius:8px;padding:12px 18px;margin:10px 22px;font-size:13px;}
.gf-info{background:#d4edda;color:#155724;border-radius:8px;padding:10px 18px;margin:10px 22px;font-size:13px;}
.gf-card.gf-thanks{text-align:center;padding:40px 30px;}.gf-thanks h1{color:#1a3a5c;margin-bottom:12px;}.gf-thanks p{color:#555;margin-bottom:8px;line-height:1.7;}
.gf-tz-note{font-size:11px;color:#c0392b;padding:2px 0 6px 30px;}.gf-note-red{color:#c0392b;font-size:11px;}
.gf-map-link{color:#1a3a5c;font-weight:bold;font-size:13px;}.gf-sub-note{font-size:11px;color:#555;}
.gf-prepare-box{padding:16px 22px;background:#eaf4ff;border-bottom:1px solid #b3d9ff;}
.gf-prepare-intro{font-size:13px;color:#555;margin:8px 0 12px;line-height:1.6;}
.gf-prepare-list{padding-left:18px;font-size:13px;line-height:2.0;color:#1a3a5c;}
.gf-prep-link{color:#1a3a5c;font-weight:bold;font-size:12px;text-decoration:underline;}
.gf-resource-links{margin-top:10px;font-size:12px;}.gf-resource-links a{color:#1a3a5c;margin-right:8px;}
@media(max-width:440px){.gf-yn-row{flex-direction:column;}}"""


# ── Guest page renderers ───────────────────────────────────────────────────────
def render_expired() -> str:
    return """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Link Expired</title>
    <style>body{font-family:Arial,sans-serif;background:#f0f4f8;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;}
    .box{background:#fff;border-radius:16px;padding:40px;max-width:480px;text-align:center;box-shadow:0 4px 20px rgba(0,0,0,.1);}
    h1{color:#1a3a5c;} p{color:#555;line-height:1.7;} a{color:#1a3a5c;font-weight:bold;}</style></head>
    <body><div class="box"><div style="font-size:56px;margin-bottom:16px;">⏰</div><h1>Link Expired</h1>
    <p>This confirmation link has expired.</p>
    <p>Please contact us at <a href="mailto:reservations@nationalparkexpress.com">reservations@nationalparkexpress.com</a> or call <strong>702-948-4190</strong>.</p>
    </div></body></html>"""


def render_thanks(row: dict) -> str:
    first = escape(row.get("first_name", ""))
    try:
        date_fmt = datetime.strptime(str(row.get("service_date", "")), "%Y-%m-%d").strftime("%A, %B %-d, %Y")
    except ValueError:
        date_fmt = str(row.get("service_date", ""))
    return f"""<!DOCTYPE html><html lang="en"><head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Tickets Reconfirmation – National Park Express</title>
    <style>{GUEST_CSS}</style></head><body>
    <div class="gf-wrap"><div class="gf-card gf-thanks">
    <div style="font-size:56px;margin-bottom:16px;">✅</div>
    <h1>Thank You, {first}!</h1>
    <p>Your response has been recorded.<br>We look forward to seeing you on<br><strong>{date_fmt}</strong>!</p>
    <p class="gf-small">Questions? <a href="mailto:reservations@nationalparkexpress.com">reservations@nationalparkexpress.com</a> | 702-948-4190</p>
    </div></div></body></html>"""


def render_form(row: dict, cfg: dict, token: str, error_msg: str = "", already: bool = False) -> str:
    try:
        date_fmt = datetime.strptime(str(row.get("service_date", "")), "%Y-%m-%d").strftime("%A, %B %-d, %Y")
    except ValueError:
        date_fmt = str(row.get("service_date", ""))
    pax       = int(row.get("no_of_pax") or 1)
    tour_slug = escape(cfg.get("sms_label") or cfg.get("label", ""))
    chd       = escape(row.get("chd_number", ""))
    cfm_no    = escape(row.get("confirmation_no", ""))
    first     = escape(row.get("first_name", ""))
    last      = escape(row.get("last_name", ""))
    checkin   = escape(row.get("checkin_time", ""))
    tourtime  = escape(row.get("tour_time", ""))
    notes_val = escape(row.get("reschedule_notes") or "")

    maps_link = ""
    if cfg.get("maps_url"):
        maps_link = f'<div class="gf-row"><span></span><a href="{cfg["maps_url"]}" target="_blank" class="gf-map-link">🗺️ Google Maps GPS</a></div>'

    prepare_html = ""
    if cfg.get("prepare_steps"):
        items = ""
        for s in cfg["prepare_steps"]:
            note_html = f'<br><span style="font-size:12px;color:#555;line-height:1.6;">{escape(s["note"])}</span>' if s.get("note") else ""
            items += f'<li>{escape(s["label"])}&nbsp;<a href="{s["url"]}" target="_blank" class="gf-prep-link">→ Open Link</a>{note_html}</li>'
        prepare_html = f"""
      <div class="gf-prepare-box">
        <div class="gf-box-title">📋 Prepare for Your Tour</div>
        <p class="gf-prepare-intro">To help you prepare for your tour, you may choose to complete the following steps in advance. Completing these steps before arrival will help shorten your check-in time.</p>
        <ul class="gf-prepare-list">{items}</ul>
      </div>"""

    reminders_html = ""
    if cfg.get("extra_notes"):
        lis = "".join(
            f'<li style="color:#c0392b;font-weight:bold;">{escape(n)}</li>' if n.startswith("★")
            else f"<li>{escape(n)}</li>"
            for n in cfg["extra_notes"]
        )
        res_links = ""
        if cfg.get("maps_url"):
            res_links += f'&nbsp;&nbsp;<a href="{cfg["maps_url"]}" target="_blank">🗺️ Google Maps GPS</a>'
        if cfg.get("location_photo"):
            res_links += f'&nbsp;&nbsp;<a href="{cfg["location_photo"]}" target="_blank">📸 Location Photo</a>'
        res_block = f'<div class="gf-resource-links"><a href="https://www.timeanddate.com/worldclock/usa/page" target="_blank">🕐 Local Time &amp; Weather</a>{res_links}</div>' if res_links else ""
        reminders_html = f"""
      <div class="gf-reminders">
        <div class="gf-box-title">📌 Know Before You Go</div>
        <ul>{lis}</ul>{res_block}
      </div>"""

    error_html   = f'<div class="gf-error">{escape(error_msg)}</div>' if error_msg else ""
    already_html = '<div class="gf-info">✅ Your booking has been confirmed. You may add notes below and click Submit to update.</div>' if already else ""

    return f"""<!DOCTYPE html><html lang="en"><head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Tickets Reconfirmation – National Park Express</title>
    <style>{GUEST_CSS}</style></head><body>
    <div class="gf-wrap"><div class="gf-card">
      <div class="gf-header">
        <img src="https://nationalparkexpress.com/wp-content/uploads/2026/03/image002.png" style="width:100px;height:auto;" />
        <div class="gf-tour-badge">{tour_slug}</div>
        <h1>Tickets Reconfirmation</h1>
        <div class="gf-date">{date_fmt}</div>
        <div class="gf-meta">CHD# {chd} &nbsp;·&nbsp; {first} {last} &nbsp;·&nbsp; Party of {pax}</div>
      </div>
      <div class="gf-pickup-box">
        <div class="gf-box-title">Your Check-in Information</div>
        <div class="gf-row"><span>📍</span><span><strong>Location:</strong> {escape(cfg.get("checkin_location",""))}</span></div>
        {maps_link}
        <div class="gf-row"><span>⏰</span><span>Check-in: <strong>{checkin}</strong> &nbsp;|&nbsp; Tour: <strong>{tourtime}</strong><br><span class="gf-note-red">★ Late check-in is subject to forfeiting your tour entry.</span></span></div>
        <div class="gf-tz-note">★ All times are based on the Arizona (AZ) time zone.</div>
        <div class="gf-row"><span>🔖</span><span>Confirmation#: <strong>{cfm_no}</strong><br><span class="gf-sub-note">Please present this number to the check-in staff upon arrival.</span></span></div>
      </div>
      {prepare_html}{reminders_html}{error_html}{already_html}
      <form method="post">
        <input type="hidden" name="token" value="{token}">
        <input type="hidden" name="npe_tix_submit" value="1">
        <input type="hidden" name="confirmation" value="yes">
        <div class="gf-section">
          <h2>📝 Notes <span class="gf-opt">(optional)</span></h2>
          <textarea name="notes" rows="3" placeholder="Any questions or special requests...">{notes_val}</textarea>
        </div>
        <div class="gf-submit">
          <p style="font-size:13px;color:#555;margin-bottom:12px;">I have read the information above and confirm my tour reservation.</p>
          <button type="submit" class="gf-btn">Submit</button>
          <p class="gf-small">Thank you for choosing National Park Express! 🏞️</p>
        </div>
      </form>
    </div></div></body></html>"""
