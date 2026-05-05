"""
Tour Confirmation service — mirrors tour-confirmation-v4.17.13.php
9 tour types, lunch selection, pickup location, token generation.
"""
from __future__ import annotations
import hashlib
import hmac
import os
import time
import base64
from datetime import datetime, timezone, timedelta

SECRET_KEY = os.environ.get("TOKEN_SECRET", "tconf_secret_fallback")
CONFIRM_BASE_URL = os.environ.get("SERVICE_BASE_URL", "https://confirm.nationalparkexpress.com")

# ── Tour types — mirrors tconf_tour_types() v4.17.13 ────────────────────────
TOUR_TYPES: dict[str, dict] = {
    "upper_antelope": {
        "label": "Upper Antelope Canyon Bus Tour",
        "has_lunch": True, "has_beef": True, "has_park_fee": False,
        "extra_reminders": [
            "To reduce dropoff time, tour will only drop off at: <strong>TREASURE ISLAND, PARK MGM, or EXCALIBUR</strong>. Subject to change due to road closures."
        ],
    },
    "lower_antelope": {
        "label": "Lower Antelope Canyon Bus Tour",
        "has_lunch": True, "has_beef": True, "has_park_fee": False,
        "extra_reminders": [
            "To reduce dropoff time, tour will only drop off at: <strong>TREASURE ISLAND, PARK MGM, or EXCALIBUR</strong>. Subject to change due to road closures."
        ],
    },
    "antelop_X": {
        "label": "Antelope Canyon X Bus Tour",
        "has_lunch": True, "has_beef": True, "has_park_fee": False,
        "extra_reminders": [
            "To reduce dropoff time, tour will only drop off at: <strong>TREASURE ISLAND, PARK MGM, or EXCALIBUR</strong>. Subject to change due to road closures."
        ],
    },
    "grand_canyon_south": {
        "label": "Grand Canyon South Rim Bus Tour",
        "has_lunch": True, "has_beef": False, "has_park_fee": True,
        "extra_reminders": [
            "To reduce dropoff time, tour will only drop off at: <strong>TREASURE ISLAND, PARK MGM, or EXCALIBUR</strong>. Subject to change due to road closures.",
            'For your return trip, please meet in front of <a href="https://nationalparkexpress.com/grand-canyon-south-rim-pickup/">Bright Angel Lodge</a>.',
        ],
    },
    "grand_canyon_west": {
        "label": "Grand Canyon West Rim Bus Tour",
        "has_lunch": False, "has_beef": False, "has_park_fee": False,
        "extra_reminders": [],
    },
    "bryce_zion": {
        "label": "Bryce Canyon & Zion National Park Bus Tour",
        "has_lunch": True, "has_beef": False, "has_park_fee": True,
        "extra_reminders": [
            "To reduce dropoff time, tour will only drop off at: <strong>TREASURE ISLAND, PARK MGM, or EXCALIBUR</strong>. Subject to change due to road closures."
        ],
    },
    "valley_of_fire_full": {
        "label": "Valley of Fire Tour (Full Day)",
        "has_lunch": True, "has_beef": False, "has_park_fee": False,
        "extra_reminders": [],
    },
    "valley_of_fire_half": {
        "label": "Valley of Fire Tour (Half Day)",
        "has_lunch": False, "has_beef": False, "has_park_fee": False,
        "extra_reminders": [],
    },
    "hoover_dam": {
        "label": "Hoover Dam Tour",
        "has_lunch": False, "has_beef": False, "has_park_fee": False,
        "extra_reminders": [],
    },
}

# ── Token ────────────────────────────────────────────────────────────────────
def make_token(record_id: int, email: str, tour_date: str) -> str:
    """
    Token expires at 6:00 PM PST (= 02:00 UTC next day) the day before tour.
    Mirrors PHP tconf_make_token().
    """
    if tour_date:
        try:
            td = datetime.strptime(tour_date, "%Y-%m-%d")
            day_before = td - timedelta(days=1)
            # 18:00 PST = 18:00 + 8h = 02:00 UTC next day  → store as unix ts
            expires_dt = datetime(day_before.year, day_before.month, day_before.day,
                                  18, 0, 0, tzinfo=timezone(timedelta(hours=-8)))
            expires = int(expires_dt.timestamp())
        except ValueError:
            expires = int(time.time()) + 7 * 86400
    else:
        expires = int(time.time()) + 7 * 86400

    payload = f"{record_id}|{email}|{expires}"
    sig = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    raw = f"{record_id}:{expires}:{sig}"
    return base64.b64encode(raw.encode()).decode()


def confirm_url(token: str, src: str = "email") -> str:
    return f"{CONFIRM_BASE_URL}/confirm/{token}?src={src}"


# ── SMS body ─────────────────────────────────────────────────────────────────
def build_sms(first_name: str, tour_type: str, tour_date: str, form_url: str) -> str:
    cfg = TOUR_TYPES.get(tour_type, {})
    label = cfg.get("label", tour_type)
    try:
        date_fmt = datetime.strptime(tour_date, "%Y-%m-%d").strftime("%B %-d, %Y")
    except ValueError:
        date_fmt = tour_date

    if cfg.get("has_lunch"):
        return (
            f"Hi {first_name}! This is National Park Express, your local tour operator "
            f"for {label} on {date_fmt}. Please confirm your tour and select your lunch "
            f"option here: {form_url}. Thank you"
        )
    return (
        f"Hi {first_name}! This is National Park Express, your local tour operator "
        f"for {label} on {date_fmt}. Please confirm your tour here: {form_url}. Thank you"
    )


# ── Email body ───────────────────────────────────────────────────────────────
def build_email(row: dict, tour_type: str, tour_date: str, form_url: str,
                pickup_instruction: str = "", pickup_photo_url: str = "",
                pickup_photo_label: str = "") -> str:
    cfg = TOUR_TYPES.get(tour_type, {})
    label = cfg.get("label", tour_type)
    first = row.get("first_name", "")
    qty = int(row.get("quantities") or 1)
    onum = row.get("order_number", "")
    ptime = row.get("pickup_time", "")
    ploc = row.get("pickup_location", "")

    try:
        date_fmt = datetime.strptime(tour_date, "%Y-%m-%d").strftime("%B %-d, %Y")
    except ValueError:
        date_fmt = tour_date

    # Pickup cell
    if pickup_photo_url:
        pickup_cell = (
            f'<a href="{pickup_photo_url}" style="color:#1a3a5c;font-weight:bold;">'
            f'{ploc} Pickup location - click here for detail</a>'
        )
    else:
        pickup_cell = pickup_instruction or f"Please arrive at <strong>{ploc}</strong>"

    # Park fee block
    fee_html = ""
    if cfg.get("has_park_fee"):
        fee_html = """
        <div style="background:#fff8e1;border:1px solid #f0d080;border-radius:6px;padding:14px;margin:16px 0;">
          <ul style="margin:8px 0 0;padding-left:18px;font-size:13px;color:#555;">
            <li><strong>Non-U.S. Residents fee (ages 16+):</strong> $100/person or $250 America the Beautiful Annual Pass (up to 4 people).</li>
            <li><strong>Legal U.S. residents:</strong> Present valid government-issued ID to waive the $100 fee.</li>
          </ul>
        </div>"""

    # Lunch block
    lunch_html = ""
    if cfg.get("has_lunch"):
        has_beef = cfg.get("has_beef", True)
        beef_col = """
            <td style="text-align:center;">
              <div style="font-size:28px;">🥩</div>
              <div style="font-size:12px;color:#555;">Beef<br>Sandwich</div>
            </td>""" if has_beef else ""
        lunch_html = f"""
        <div style="background:#fffbf0;border:1px solid #f0d080;border-radius:8px;padding:16px;margin:20px 0;">
          <p style="margin:0 0 10px;font-weight:bold;color:#8a6000;">🥪 Available lunch options:</p>
          <table width="100%" cellpadding="4"><tr>
            <td style="text-align:center;"><div style="font-size:28px;">🦃</div><div style="font-size:12px;color:#555;">Turkey<br>Sandwich</div></td>
            <td style="text-align:center;"><div style="font-size:28px;">🥗</div><div style="font-size:12px;color:#555;">Veggie<br>Sandwich</div></td>
            {beef_col}
          </tr></table>
          <p style="margin:8px 0 0;font-size:12px;color:#999;text-align:center;">Default is Turkey Sandwich if no selection received.</p>
        </div>"""

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f8;padding:30px 0;"><tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">
  <tr><td style="background:#1a3a5c;border-radius:12px 12px 0 0;padding:20px 28px;">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td style="width:20%;vertical-align:middle;">
        <img src="https://nationalparkexpress.com/wp-content/uploads/2026/03/image002.png" style="width:90px;height:auto;display:block;" />
      </td>
      <td style="vertical-align:middle;text-align:center;padding-right:20px;">
        <h1 style="color:#fff;margin:0 0 2px;font-size:20px;line-height:1.3;">Tour Confirmation &amp; Lunch Selection</h1>
        <p style="color:#c8dff7;margin:2px 0 6px;font-size:13px;">(If Applicable)</p>
        <p style="color:#a8c4e0;margin:0;font-size:13px;">{label}</p>
      </td>
    </tr></table>
  </td></tr>
  <tr><td style="background:#fff;padding:32px;">
    <p style="font-size:16px;">Hi <strong>{first}</strong>,</p>
    <p style="color:#555;line-height:1.6;margin:10px 0 20px;">Your tour is scheduled for <strong style="color:#1a3a5c;">{date_fmt}</strong>. Please confirm your attendance.</p>
    <p style="color:#555;line-height:1.6;margin:-10px 0 20px;">(The lunch selection is not applicable to Hoover Dam tours, tours without meals, or voucher bookings.)</p>
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f5ff;border-radius:8px;overflow:hidden;margin-bottom:16px;">
      <tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;background:#e8f0ff;width:38%;">📋 Order #</td><td style="padding:10px 16px;font-size:13px;">{onum}</td></tr>
      <tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;background:#e8f0ff;">👥 Party Size</td><td style="padding:10px 16px;font-size:13px;">{qty} Guest(s)</td></tr>
      <tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;">📅 Tour Date</td><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#1a3a5c;">{date_fmt}</td></tr>
      <tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;background:#e8f0ff;">⏰ Pickup Time</td><td style="padding:10px 16px;font-size:13px;font-weight:bold;">{ptime}</td></tr>
      <tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;">📍 Pickup Location</td><td style="padding:10px 16px;font-size:13px;">{pickup_cell}</td></tr>
    </table>
    {fee_html}
    <p style="color:#555;font-size:14px;margin:16px 0;">You will choose your lunch option after clicking the Confirm My Tour button.</p>
    {lunch_html}
    <div style="text-align:center;margin:28px 0;">
      <a href="{form_url}" style="display:inline-block;background:#1a3a5c;color:#fff;text-decoration:none;padding:16px 44px;border-radius:8px;font-size:16px;font-weight:bold;">✅ Confirm My Tour</a>
      <p style="margin:10px 0 0;font-size:12px;color:#aaa;">Link expires at 6:00 PM PST the day before your tour</p>
    </div>
    <p style="color:#999;font-size:12px;text-align:center;">Questions? <a href="mailto:reservations@nationalparkexpress.com" style="color:#1a3a5c;">reservations@nationalparkexpress.com</a> | 702-948-4190</p>
  </td></tr>
  <tr><td style="background:#f0f0f0;border-radius:0 0 12px 12px;padding:16px;text-align:center;">
    <p style="color:#aaa;font-size:12px;margin:0;">National Park Express — Thank you for choosing us! 🏞️</p>
  </td></tr>
</table></td></tr></table></body></html>"""
