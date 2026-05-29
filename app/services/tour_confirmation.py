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
from zoneinfo import ZoneInfo
_LA = ZoneInfo("America/Los_Angeles")

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
    Token expires at 6:00 PM LA time (DST-aware) the day before tour.
    Mirrors PHP tconf_make_token().
    """
    if tour_date:
        try:
            td = datetime.strptime(tour_date, "%Y-%m-%d")
            day_before = td - timedelta(days=1)
            # 18:00 PST = 18:00 + 8h = 02:00 UTC next day  → store as unix ts
            expires_dt = datetime(day_before.year, day_before.month, day_before.day,
                                  18, 0, 0, tzinfo=_LA)
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


# ── Tour images ──────────────────────────────────────────────────────────────
TOUR_IMAGES: dict[str, str] = {
    "upper_antelope":       "https://nationalparkexpress.com/wp-content/uploads/2023/09/leon-liu-_0aOFIW34rw-unsplash-scaled.jpg",
    "lower_antelope":       "https://nationalparkexpress.com/wp-content/uploads/2023/09/leon-liu-_0aOFIW34rw-unsplash-scaled.jpg",
    "antelop_X":            "https://nationalparkexpress.com/wp-content/uploads/2023/09/leon-liu-_0aOFIW34rw-unsplash-scaled.jpg",
    "grand_canyon_south":   "https://nationalparkexpress.com/wp-content/uploads/2024/04/National-Park-Express-Which-Section-of-the-Grand-Canyon-img1.jpg",
    "grand_canyon_west":    "https://nationalparkexpress.com/wp-content/uploads/2023/04/GCW_Banner.jpg",
    "bryce_zion":           "https://nationalparkexpress.com/wp-content/uploads/2023/01/6Bryce.jpg",
    "valley_of_fire_full":  "https://nationalparkexpress.com/wp-content/uploads/2026/01/3ValleyofFire-scaled-1-1.jpg",
    "valley_of_fire_half":  "https://nationalparkexpress.com/wp-content/uploads/2026/01/3ValleyofFire-scaled-1-1.jpg",
    "hoover_dam":           "https://nationalparkexpress.com/wp-content/uploads/2023/06/hoover-dam-img1.jpg",
}

LOGO_URL = "https://nationalparkexpress.com/wp-content/uploads/2026/03/image002.png"


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
            f"Hi {first_name}, This is National Park Express, your local tour operator "
            f"for {label} on {date_fmt}. Please reconfirm your tour and select your lunch "
            f"option here: {form_url}. Thank you"
        )
    return (
        f"Hi {first_name}, This is National Park Express, your local tour operator "
        f"for {label} on {date_fmt}. Please reconfirm your tour here: {form_url}. Thank you"
    )


# ── Email body ───────────────────────────────────────────────────────────────
def build_email(row: dict, tour_type: str, tour_date: str, form_url: str,
                pickup_instruction: str = "", pickup_photo_url: str = "",
                pickup_photo_label: str = "") -> str:
    cfg   = TOUR_TYPES.get(tour_type, {})
    label = cfg.get("label", tour_type)
    has_lunch = cfg.get("has_lunch", False) 
    first = row.get("first_name", "")
    qty   = int(row.get("quantities") or 1)
    onum  = row.get("order_number", "")
    ptime = row.get("pickup_time", "")
    ploc  = row.get("pickup_location", "")
    

    try:
        date_fmt = datetime.strptime(tour_date, "%Y-%m-%d").strftime("%B %-d, %Y")
    except ValueError:
        date_fmt = tour_date

    # Hero image
    hero_url = TOUR_IMAGES.get(tour_type, TOUR_IMAGES["grand_canyon_south"])

    # Pickup cell
    if pickup_photo_url:
        pickup_cell = (
            f'<a href="{pickup_photo_url}" style="color:#2563eb;font-weight:600;">' 
            f'{ploc} Pickup location - click here for detail</a>'
        )
    else:
        pickup_cell = pickup_instruction or f"<strong>{ploc}</strong>"

    # Park fee block
    fee_html = ""
    if cfg.get("has_park_fee"):
        fee_html = """
        <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5faff;border:1px solid #bfdbfe;border-radius:12px;margin-bottom:24px;">
          <tr>
            <td style="padding:14px 18px;border-bottom:1px solid #dbeafe;">
              <table width="100%" cellpadding="0" cellspacing="0"><tr>
                <td style="width:42px;vertical-align:top;">
                  <div style="width:36px;height:36px;border-radius:9px;background:#eef6ff;text-align:center;line-height:36px;font-size:18px;">&#128100;</div>
                </td>
                <td style="vertical-align:top;padding-left:12px;">
                  <div style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:13px;font-weight:600;color:#0b1f3a;margin-bottom:3px;">Non-U.S. Residents fee (ages 16+):</div>
                  <div style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:13px;font-weight:300;color:#333;line-height:1.6;">$100/person or $250 America the Beautiful Annual Pass (up to 4 people).</div>
                </td>
              </tr></table>
            </td>
          </tr>
          <tr>
            <td style="padding:14px 18px;">
              <table width="100%" cellpadding="0" cellspacing="0"><tr>
                <td style="width:42px;vertical-align:top;">
                  <div style="width:36px;height:36px;border-radius:9px;background:#eef6ff;text-align:center;line-height:36px;font-size:18px;">&#129538;</div>
                </td>
                <td style="vertical-align:top;padding-left:12px;">
                  <div style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:13px;font-weight:600;color:#0b1f3a;margin-bottom:3px;">Legal U.S. residents:</div>
                  <div style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:13px;font-weight:300;color:#333;line-height:1.6;">Present valid government-issued ID to waive the $100 fee.</div>
                </td>
              </tr></table>
            </td>
          </tr>
        </table>"""

    # Lunch note (shown for all tours, explains applicability)
    lunch_html = ""
    if cfg.get("has_lunch"):
        lunch_html = """
        <table width="100%" cellpadding="0" cellspacing="0" style="background:#fffbf0;border:1px solid #f0d080;border-radius:10px;margin-bottom:24px;">
          <tr><td style="padding:14px 18px;">
            <table width="100%" cellpadding="0" cellspacing="0"><tr>
              <td style="width:42px;vertical-align:top;">
                <div style="width:36px;height:36px;border-radius:9px;background:#eef6ff;text-align:center;line-height:36px;font-size:18px;">&#127374;</div>
              </td>
              <td style="vertical-align:top;padding-left:12px;">
                <div style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:13px;font-weight:300;color:#24364f;line-height:1.6;margin-bottom:4px;">
                  For tours including lunch, you will choose your lunch option after clicking the <strong style="font-weight:600;">Reconfirm My Spot</strong> button.
                </div>
                <div style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:12px;font-weight:300;color:#f97316;line-height:1.6;">
                  This does not apply to Hoover Dam tours, tours without meals, or voucher bookings.
                </div>
              </td>
            </tr></table>
          </td></tr>
        </table>"""

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Nunito+Sans:wght@300;400;600&display=swap');
  </style>
</head>
<body style="margin:0;padding:0;background:#f4f8fc;font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f8fc;padding:30px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;">

  <!-- Hero header with destination image -->
  <tr><td style="padding:0;margin:0;height:200px;position:relative;overflow:hidden;">
    <div style="position:relative;height:200px;overflow:hidden;">
      <img src="{hero_url}" alt="{label}" width="600" style="width:100%;height:200px;object-fit:cover;display:block;" />
      <div style="position:absolute;inset:0;background:linear-gradient(to bottom,rgba(6,26,51,0.45),rgba(6,26,51,0.82));display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:20px;">
        <img src="{LOGO_URL}" alt="NPE Logo" width="72" style="width:72px;height:72px;object-fit:contain;border-radius:50%;margin-bottom:10px;" />
        <div style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:20px;font-weight:600;color:#ffffff;letter-spacing:0.3px;">National Park <span style="color:#f97316;">Express</span></div>
        <div style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:10px;font-weight:300;color:#ffffff;margin-top:5px;letter-spacing:1.5px;">YOUR JOURNEY. OUR PASSION.</div>
      </div>
    </div>
  </td></tr>

  <!-- Body -->
  <tr><td style="padding:32px 40px;background:#ffffff;">

    <p style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:15px;font-weight:400;color:#1a1a1a;margin:0 0 8px;letter-spacing:-0.1px;">Hi <strong style="font-weight:600;">{first}</strong>,</p>
    <p style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:14px;font-weight:400;color:#24364f;line-height:1.7;margin:0 0 6px;letter-spacing:-0.1px;">
      Greetings from National Park Express!
    </p>
    <p style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:14px;font-weight:400;color:#24364f;line-height:1.7;margin:0 0 6px;letter-spacing:-0.1px;">
      As your local tour operator for the <strong style="font-weight:600;">{label}</strong>, we're excited to welcome you on <strong style="color:#2563eb;font-weight:600;">{date_fmt}</strong>.
    </p>
    <p style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:14px;font-weight:400;color:#24364f;line-height:1.7;margin:0 0 6px;letter-spacing:-0.1px;">
      Please review your tour details below and reconfirm your spot.{'  Please also select your <strong style="font-weight:600;">lunch option</strong> using the button below.' if has_lunch else ''}
    </p>
    <p style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:14px;font-weight:400;color:#24364f;line-height:1.7;margin:0 0 28px;letter-spacing:-0.1px;">
      We look forward to seeing you soon.
    </p>

    <!-- Details card -->
    <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e5ecf5;border-radius:12px;overflow:hidden;margin-bottom:24px;">
      <tr>
        <td style="width:42px;padding:14px 0 14px 16px;vertical-align:middle;border-bottom:1px solid #e5ecf5;">
          <div style="width:36px;height:36px;border-radius:9px;background:#eef6ff;text-align:center;line-height:36px;font-size:16px;">&#128196;</div>
        </td>
        <td style="padding:14px 16px;font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;border-bottom:1px solid #e5ecf5;">
          <div style="font-size:10px;font-weight:600;color:#5b6b80;text-transform:uppercase;letter-spacing:0.7px;">Order #</div>
          <div style="font-size:14px;font-weight:600;color:#0b1f3a;margin-top:2px;">{onum}</div>
        </td>
      </tr>
      <tr>
        <td style="width:42px;padding:14px 0 14px 16px;vertical-align:middle;border-bottom:1px solid #e5ecf5;">
          <div style="width:36px;height:36px;border-radius:9px;background:#eef6ff;text-align:center;line-height:36px;font-size:16px;">&#128101;</div>
        </td>
        <td style="padding:14px 16px;font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;border-bottom:1px solid #e5ecf5;">
          <div style="font-size:10px;font-weight:600;color:#5b6b80;text-transform:uppercase;letter-spacing:0.7px;">Party Size</div>
          <div style="font-size:14px;font-weight:600;color:#0b1f3a;margin-top:2px;">{qty} Guest(s)</div>
        </td>
      </tr>
      <tr>
        <td style="width:42px;padding:14px 0 14px 16px;vertical-align:middle;border-bottom:1px solid #e5ecf5;">
          <div style="width:36px;height:36px;border-radius:9px;background:#eef6ff;text-align:center;line-height:36px;font-size:16px;">&#128197;</div>
        </td>
        <td style="padding:14px 16px;font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;border-bottom:1px solid #e5ecf5;">
          <div style="font-size:10px;font-weight:600;color:#5b6b80;text-transform:uppercase;letter-spacing:0.7px;">Tour Date</div>
          <div style="font-size:14px;font-weight:600;color:#2563eb;margin-top:2px;">{date_fmt}</div>
        </td>
      </tr>
      <tr>
        <td style="width:42px;padding:14px 0 14px 16px;vertical-align:middle;border-bottom:1px solid #e5ecf5;">
          <div style="width:36px;height:36px;border-radius:9px;background:#eef6ff;text-align:center;line-height:36px;font-size:16px;">&#128336;</div>
        </td>
        <td style="padding:14px 16px;font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;border-bottom:1px solid #e5ecf5;">
          <div style="font-size:10px;font-weight:600;color:#5b6b80;text-transform:uppercase;letter-spacing:0.7px;">Pickup Time</div>
          <div style="font-size:14px;font-weight:600;color:#0b1f3a;margin-top:2px;">{ptime}</div>
        </td>
      </tr>
      <tr>
        <td style="width:42px;padding:14px 0 14px 16px;vertical-align:middle;">
          <div style="width:36px;height:36px;border-radius:9px;background:#eef6ff;text-align:center;line-height:36px;font-size:16px;">&#128205;</div>
        </td>
        <td style="padding:14px 16px;font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;">
          <div style="font-size:10px;font-weight:600;color:#5b6b80;text-transform:uppercase;letter-spacing:0.7px;">Pickup Location</div>
          <div style="font-size:14px;font-weight:300;color:#0b1f3a;margin-top:2px;">{pickup_cell}</div>
        </td>
      </tr>
    </table>

    {fee_html}
    {lunch_html}

    <!-- CTA Button -->
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr><td align="center" style="padding:4px 0 8px;">
        <a href="{form_url}" style="display:inline-block;background:#1a3a5c;color:#ffffff;text-decoration:none;padding:16px 48px;border-radius:10px;font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:15px;font-weight:600;letter-spacing:0.5px;">&#10003; RECONFIRM MY SPOT</a>
      </td></tr>
      <tr><td align="center">
        <p style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:11px;font-weight:300;color:#aaa;margin:6px 0 0;">Link expires at 6:00 PM PST the day before your tour</p>
      </td></tr>
    </table>

  </td></tr>

  <!-- Footer -->
  <tr><td style="background:#061a33;padding:20px 36px;text-align:center;">
    <img src="{LOGO_URL}" alt="NPE Logo" width="60" style="width:60px;height:60px;object-fit:contain;border-radius:50%;margin-bottom:12px;" />
    <p style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:13px;font-weight:300;color:#dbeafe;margin:0 0 4px;">Questions? We're here to help!</p>
    <p style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:13px;font-weight:300;color:#dbeafe;margin:0 0 4px;">+1 (702) 948-4190 | <a href="mailto:reservations@nationalparkexpress.com" style="color:#93c5fd;">reservations@nationalparkexpress.com</a></p>
    <p style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:12px;font-weight:300;color:#93c5fd;margin:0;"><a href="https://www.nationalparkexpress.com" style="color:#93c5fd;">nationalparkexpress.com</a></p>
  </td></tr>

</table>
</td></tr></table>
</body>
</html>"""

# ── Last Minute Email ─────────────────────────────────────────────────────────
def build_last_minute_email(row: dict, tour_type: str, tour_date: str, form_url: str,
                            pickup_instruction: str = "", pickup_photo_url: str = "",
                            pickup_photo_label: str = "") -> str:
    cfg   = TOUR_TYPES.get(tour_type, {})
    label = cfg.get("label", tour_type)
    has_lunch = cfg.get("has_lunch", False)
    first = row.get("first_name", "")
    qty   = int(row.get("quantities") or 1)
    onum  = row.get("order_number", "")
    ptime = row.get("pickup_time", "")
    ploc  = row.get("pickup_location", "")
   
    try:
        date_fmt = datetime.strptime(tour_date, "%Y-%m-%d").strftime("%B %-d, %Y")
    except ValueError:
        date_fmt = tour_date

    hero_url = TOUR_IMAGES.get(tour_type, TOUR_IMAGES["grand_canyon_south"])

    if pickup_photo_url:
        pickup_cell = (
            f'<a href="{pickup_photo_url}" style="color:#2563eb;font-weight:600;">'
            f'{ploc} Pickup location - click here for detail</a>'
        )
    else:
        pickup_cell = pickup_instruction or f"<strong>{ploc}</strong>"

    fee_html = ""
    if cfg.get("has_park_fee"):
        fee_html = """
        <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5faff;border:1px solid #bfdbfe;border-radius:12px;margin-bottom:24px;">
          <tr>
            <td style="padding:14px 18px;border-bottom:1px solid #dbeafe;">
              <table width="100%" cellpadding="0" cellspacing="0"><tr>
                <td style="width:42px;vertical-align:top;">
                  <div style="width:36px;height:36px;border-radius:9px;background:#eef6ff;text-align:center;line-height:36px;font-size:18px;">&#128100;</div>
                </td>
                <td style="vertical-align:top;padding-left:12px;">
                  <div style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:13px;font-weight:600;color:#0b1f3a;margin-bottom:3px;">Non-U.S. Residents fee (ages 16+):</div>
                  <div style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:13px;font-weight:300;color:#333;line-height:1.6;">$100/person or $250 America the Beautiful Annual Pass (up to 4 people).</div>
                </td>
              </tr></table>
            </td>
          </tr>
          <tr>
            <td style="padding:14px 18px;">
              <table width="100%" cellpadding="0" cellspacing="0"><tr>
                <td style="width:42px;vertical-align:top;">
                  <div style="width:36px;height:36px;border-radius:9px;background:#eef6ff;text-align:center;line-height:36px;font-size:18px;">&#129538;</div>
                </td>
                <td style="vertical-align:top;padding-left:12px;">
                  <div style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:13px;font-weight:600;color:#0b1f3a;margin-bottom:3px;">Legal U.S. residents:</div>
                  <div style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:13px;font-weight:300;color:#333;line-height:1.6;">Present valid government-issued ID to waive the $100 fee.</div>
                </td>
              </tr></table>
            </td>
          </tr>
        </table>"""

    lunch_html = ""
    if cfg.get("has_lunch"):
        lunch_html = """
        <table width="100%" cellpadding="0" cellspacing="0" style="background:#fffbf0;border:1px solid #f0d080;border-radius:10px;margin-bottom:24px;">
          <tr><td style="padding:14px 18px;">
            <table width="100%" cellpadding="0" cellspacing="0"><tr>
              <td style="width:42px;vertical-align:top;">
                <div style="width:36px;height:36px;border-radius:9px;background:#eef6ff;text-align:center;line-height:36px;font-size:18px;">&#127374;</div>
              </td>
              <td style="vertical-align:top;padding-left:12px;">
                <div style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:13px;font-weight:400;color:#24364f;line-height:1.6;margin-bottom:4px;">
                  Please click the button below to select your <strong style="font-weight:600;">lunch option</strong> and confirm your pickup details.
                </div>
                <div style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:12px;font-weight:400;color:#f97316;line-height:1.6;">
                  This does not apply to Hoover Dam tours, tours without meals, or voucher bookings.
                </div>
              </td>
            </tr></table>
          </td></tr>
        </table>"""

    has_lunch = cfg.get("has_lunch", False)
    btn_text  = "&#127374; SELECT MY LUNCH OPTION" if has_lunch else "&#10003; I'VE READ THIS MESSAGE"

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Nunito+Sans:wght@300;400;600&display=swap');
  </style>
</head>
<body style="margin:0;padding:0;background:#f4f8fc;font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f8fc;padding:30px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;">

  <tr><td style="padding:0;margin:0;height:200px;position:relative;overflow:hidden;">
    <div style="position:relative;height:200px;overflow:hidden;">
      <img src="{hero_url}" alt="{label}" width="600" style="width:100%;height:200px;object-fit:cover;display:block;" />
      <div style="position:absolute;inset:0;background:linear-gradient(to bottom,rgba(6,26,51,0.45),rgba(6,26,51,0.82));display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:20px;">
        <img src="{LOGO_URL}" alt="NPE Logo" width="72" style="width:72px;height:72px;object-fit:contain;border-radius:50%;margin-bottom:10px;" />
        <div style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:20px;font-weight:600;color:#ffffff;letter-spacing:0.3px;">National Park <span style="color:#f97316;">Express</span></div>
        <div style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:10px;font-weight:300;color:#dbeafe;margin-top:5px;letter-spacing:1.5px;">YOUR JOURNEY. OUR PASSION.</div>
      </div>
    </div>
  </td></tr>

  <tr><td style="padding:32px 40px;background:#ffffff;">

    <p style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:15px;font-weight:400;color:#1a1a1a;margin:0 0 8px;letter-spacing:-0.1px;">Hi <strong style="font-weight:600;">{first}</strong>,</p>
    <p style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:14px;font-weight:400;color:#24364f;line-height:1.7;margin:0 0 6px;letter-spacing:-0.1px;">
      Greetings from National Park Express!
    </p>
    <p style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:14px;font-weight:400;color:#24364f;line-height:1.7;margin:0 0 6px;letter-spacing:-0.1px;">
      As your local tour operator for the <strong style="font-weight:600;">{label}</strong>, we're excited to welcome you on <strong style="color:#2563eb;font-weight:600;">{date_fmt}</strong>.
    </p>
    <p style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:14px;font-weight:400;color:#24364f;line-height:1.7;margin:0 0 6px;letter-spacing:-0.1px;">
      {'Please review your tour details below and select your <strong style="font-weight:600;">lunch option</strong> using the button below to help ensure a smooth and hassle-free departure.' if has_lunch else 'Please review your tour details below and confirm your pickup information to help ensure a smooth and hassle-free departure.'}
    </p>
    <p style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:14px;font-weight:400;color:#24364f;line-height:1.7;margin:0 0 28px;letter-spacing:-0.1px;">
      We look forward to seeing you soon.
    </p>

    <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e5ecf5;border-radius:12px;overflow:hidden;margin-bottom:24px;">
      <tr>
        <td style="width:42px;padding:14px 0 14px 16px;vertical-align:middle;border-bottom:1px solid #e5ecf5;">
          <div style="width:36px;height:36px;border-radius:9px;background:#eef6ff;text-align:center;line-height:36px;font-size:16px;">&#128196;</div>
        </td>
        <td style="padding:14px 16px;font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;border-bottom:1px solid #e5ecf5;">
          <div style="font-size:10px;font-weight:600;color:#5b6b80;text-transform:uppercase;letter-spacing:0.7px;">Order #</div>
          <div style="font-size:14px;font-weight:600;color:#0b1f3a;margin-top:2px;">{onum}</div>
        </td>
      </tr>
      <tr>
        <td style="width:42px;padding:14px 0 14px 16px;vertical-align:middle;border-bottom:1px solid #e5ecf5;">
          <div style="width:36px;height:36px;border-radius:9px;background:#eef6ff;text-align:center;line-height:36px;font-size:16px;">&#128101;</div>
        </td>
        <td style="padding:14px 16px;font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;border-bottom:1px solid #e5ecf5;">
          <div style="font-size:10px;font-weight:600;color:#5b6b80;text-transform:uppercase;letter-spacing:0.7px;">Party Size</div>
          <div style="font-size:14px;font-weight:600;color:#0b1f3a;margin-top:2px;">{qty} Guest(s)</div>
        </td>
      </tr>
      <tr>
        <td style="width:42px;padding:14px 0 14px 16px;vertical-align:middle;border-bottom:1px solid #e5ecf5;">
          <div style="width:36px;height:36px;border-radius:9px;background:#eef6ff;text-align:center;line-height:36px;font-size:16px;">&#128197;</div>
        </td>
        <td style="padding:14px 16px;font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;border-bottom:1px solid #e5ecf5;">
          <div style="font-size:10px;font-weight:600;color:#5b6b80;text-transform:uppercase;letter-spacing:0.7px;">Tour Date</div>
          <div style="font-size:14px;font-weight:600;color:#2563eb;margin-top:2px;">{date_fmt}</div>
        </td>
      </tr>
      <tr>
        <td style="width:42px;padding:14px 0 14px 16px;vertical-align:middle;border-bottom:1px solid #e5ecf5;">
          <div style="width:36px;height:36px;border-radius:9px;background:#eef6ff;text-align:center;line-height:36px;font-size:16px;">&#128336;</div>
        </td>
        <td style="padding:14px 16px;font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;border-bottom:1px solid #e5ecf5;">
          <div style="font-size:10px;font-weight:600;color:#5b6b80;text-transform:uppercase;letter-spacing:0.7px;">Pickup Time</div>
          <div style="font-size:14px;font-weight:600;color:#0b1f3a;margin-top:2px;">{ptime}</div>
        </td>
      </tr>
      <tr>
        <td style="width:42px;padding:14px 0 14px 16px;vertical-align:middle;">
          <div style="width:36px;height:36px;border-radius:9px;background:#eef6ff;text-align:center;line-height:36px;font-size:16px;">&#128205;</div>
        </td>
        <td style="padding:14px 16px;font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;">
          <div style="font-size:10px;font-weight:600;color:#5b6b80;text-transform:uppercase;letter-spacing:0.7px;">Pickup Location</div>
          <div style="font-size:14px;font-weight:300;color:#0b1f3a;margin-top:2px;">{pickup_cell}</div>
        </td>
      </tr>
    </table>

    {fee_html}
    {lunch_html}

    <table width="100%" cellpadding="0" cellspacing="0">
      <tr><td align="center" style="padding:4px 0 8px;">
        <a href="{form_url}" style="display:inline-block;background:#1a3a5c;color:#ffffff;text-decoration:none;padding:16px 48px;border-radius:10px;font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:15px;font-weight:600;letter-spacing:0.5px;">{btn_text}</a>
      </td></tr>
      <tr><td align="center">
        <p style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:11px;font-weight:300;color:#aaa;margin:6px 0 0;">Link expires at 6:00 PM PST the day before your tour</p>
      </td></tr>
    </table>

  </td></tr>

  <tr><td style="background:#061a33;padding:20px 36px;text-align:center;">
    <img src="{LOGO_URL}" alt="NPE Logo" width="60" style="width:60px;height:60px;object-fit:contain;border-radius:50%;margin-bottom:12px;" />
    <p style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:13px;font-weight:300;color:#dbeafe;margin:0 0 4px;">Questions? We're here to help!</p>
    <p style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:13px;font-weight:300;color:#dbeafe;margin:0 0 4px;">+1 (702) 948-4190 | <a href="mailto:reservations@nationalparkexpress.com" style="color:#93c5fd;">reservations@nationalparkexpress.com</a></p>
    <p style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:12px;font-weight:300;color:#93c5fd;margin:0;"><a href="https://www.nationalparkexpress.com" style="color:#93c5fd;">nationalparkexpress.com</a></p>
  </td></tr>

</table>
</td></tr></table>
</body>
</html>"""