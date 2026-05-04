"""
Tickets Reminder service — mirrors tickets-reminder.php v1.3.18
9 Antelope Canyon tour types, confirm token, email + SMS templates.
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import os
import time
from datetime import datetime, timedelta

SECRET_KEY = os.environ.get("TOKEN_SECRET", "npe_tix_secret_fallback")
CONFIRM_BASE_URL = os.environ.get("SERVICE_BASE_URL", "https://confirm.nationalparkexpress.com")

# ── Tour types ───────────────────────────────────────────────────────────────
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
             "url": "https://fareharbor.com/embeds/book/navajonationparks/items/691331/calendar/2026/01/"},
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
        "prepare_steps": [],
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
            "Antelope Canyon does not allow any bags on the walking tour. Please leave them in your vehicle.",
            "If you can't find the check-in location, call: 928-693-9293",
        ],
        "prepare_steps": [],
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


# ── Token — expires at end of service date (+1 day 23:59:59) ────────────────
def make_token(record_id: int, email: str, service_date: str) -> str:
    """Mirrors PHP npe_tix_make_token()"""
    if service_date:
        try:
            sd = datetime.strptime(service_date, "%Y-%m-%d")
            expires = int((sd + timedelta(days=1, hours=23, minutes=59, seconds=59)).timestamp())
        except ValueError:
            expires = int(time.time()) + 7 * 86400
    else:
        expires = int(time.time()) + 7 * 86400

    payload = f"{record_id}|{email}|{expires}"
    sig = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    raw = f"{record_id}:{expires}:{sig}"
    return base64.b64encode(raw.encode()).decode()


def confirm_url(token: str, src: str = "email") -> str:
    return f"{CONFIRM_BASE_URL}/confirm/tickets/{token}?src={src}"


# ── SMS ──────────────────────────────────────────────────────────────────────
def build_sms(row: dict, tour_type: str, form_url: str) -> str:
    cfg = TOUR_TYPES.get(tour_type, {})
    sms_label = cfg.get("sms_label", cfg.get("label", tour_type))
    first = row.get("first_name", row.get("name", ""))
    checkin = row.get("checkin_time", "")
    service_date = row.get("service_date", row.get("tour_date", ""))
    try:
        date_fmt = datetime.strptime(service_date, "%Y-%m-%d").strftime("%B %-d, %Y")
    except ValueError:
        date_fmt = service_date

    return (
        f"Hi {first}! This is National Park Express. "
        f"Reminder for your {sms_label} on {date_fmt}. "
        f"Check-in time: {checkin}. "
        f"Please reconfirm your attendance here: {form_url}. Thank you"
    )


# ── Email ────────────────────────────────────────────────────────────────────
def build_email(row: dict, tour_type: str, service_date: str, form_url: str) -> str:
    cfg = TOUR_TYPES.get(tour_type, {})
    label = cfg.get("label", tour_type)
    first = row.get("first_name", "")
    last = row.get("last_name", "")
    chd = row.get("order_number", "")
    cfm = row.get("confirmation_no", "")
    pax = row.get("quantities", "1")
    checkin = row.get("checkin_time", "")
    tour_time = row.get("tour_time", "")
    checkin_loc = cfg.get("checkin_location", "")
    maps_url = cfg.get("maps_url", "")
    location_photo = cfg.get("location_photo", "")

    try:
        date_fmt = datetime.strptime(service_date, "%Y-%m-%d").strftime("%B %-d, %Y")
    except ValueError:
        date_fmt = service_date

    maps_row = f"""
      <tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;">🗺️ Maps</td>
          <td style="padding:10px 16px;font-size:13px;">
            <a href="{maps_url}" style="color:#1a3a5c;" target="_blank">Google Maps GPS</a>
          </td></tr>""" if maps_url else ""

    location_photo_row = f"""
      <tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;background:#e8f0ff;">📸 Location Photo</td>
          <td style="padding:10px 16px;font-size:13px;">
            <a href="{location_photo}" style="color:#1a3a5c;" target="_blank">View check-in location</a>
          </td></tr>""" if location_photo else ""

    # Prepare steps (waiver / permit fee)
    prepare_html = ""
    steps = cfg.get("prepare_steps", [])
    if steps:
        items = "".join(
            f'<li><a href="{s["url"]}" style="color:#1a3a5c;" target="_blank">{s["label"]}</a></li>'
            for s in steps
        )
        prepare_html = f"""
        <div style="background:#e8f4fd;border:1px solid #90caf9;border-radius:8px;padding:16px;margin:20px 0;">
          <p style="margin:0 0 8px;font-weight:bold;color:#1a3a5c;">📋 Before your tour, please complete:</p>
          <ul style="margin:0;padding-left:18px;line-height:2;">{items}</ul>
        </div>"""

    extra_lis = "".join(f"<li>{n}</li>" for n in cfg.get("extra_notes", []))

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
      {location_photo_row}
    </table>
    {prepare_html}
    <div style="background:#fff3cd;border:1px solid #ffc107;border-radius:8px;padding:14px;margin:16px 0;">
      <ul style="margin:0;padding-left:18px;font-size:13px;line-height:1.9;color:#555;">
        {extra_lis}
      </ul>
    </div>
    <div style="text-align:center;margin:28px 0;">
      <a href="{form_url}" style="display:inline-block;background:#1a3a5c;color:#fff;text-decoration:none;padding:16px 44px;border-radius:8px;font-size:16px;font-weight:bold;">✅ Confirm My Attendance</a>
    </div>
    <p style="color:#999;font-size:12px;text-align:center;">Questions? <a href="mailto:reservations@nationalparkexpress.com" style="color:#1a3a5c;">reservations@nationalparkexpress.com</a> | 702-948-4190</p>
  </td></tr>
  <tr><td style="background:#f0f0f0;border-radius:0 0 12px 12px;padding:16px;text-align:center;">
    <p style="color:#aaa;font-size:12px;margin:0;">National Park Express — Thank you for choosing us! 🏞️</p>
  </td></tr>
</table></td></tr></table></body></html>"""
