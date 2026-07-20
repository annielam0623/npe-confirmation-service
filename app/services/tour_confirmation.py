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
from html import escape as _html_escape
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.template_copy import get_copy_many, get_copy_value
import re as _re
_LA = ZoneInfo("America/Los_Angeles")


# ── Content Studio copy helpers ──────────────────────────────────────────────
def _esc(s: str) -> str:
    """Match preview esc(): escape only & < >, NOT quotes (quote=False)."""
    return _html_escape(str(s), quote=False)


# get_copy() returns "" when a settings row exists but is blank. Per product
# decision, a blank value is intentional (admin removed that line) and is passed
# through as-is; we only fall back to the English default when the DB read errors.
async def _copy(db, key: str, fallback: str) -> str:
    try:
        copy = await get_copy_many(db, [key])
    except Exception:
        return fallback
    return copy.get(key, "") if key in copy else fallback


def _apply(raw: str, **vars) -> str:
    """Mirror preview: HTML-escape the DB text first, then substitute system
    values into {placeholders} (escaped text so injected label/date not double-escaped)."""
    out = _esc(raw)
    for k, val in vars.items():
        out = out.replace("{" + k + "}", val)
    return out


# Footer rendering: esc -> linkify (url/email/tel) -> nl2br. Kept byte-identical
# with footerHtml() in settings_templates.html so preview == sent email.
_URL_RE   = _re.compile(r"(https?://[^\s<]+|www\.[^\s<]+)")
_EMAIL_RE = _re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_TEL_RE   = _re.compile(r"(\+?\d[\d()\s\-]{7,}\d)")

def _footer_html(raw: str) -> str:
    out = _esc(raw)                                          # 1. escape first

    def _url_sub(m):
        s = m.group(0)
        href = s if s.startswith("http") else "https://" + s
        return f'<a href="{href}" style="color:#93c5fd;">{s}</a>'
    out = _URL_RE.sub(_url_sub, out)                         # 2a. urls

    def _email_sub(m):
        before = out[:m.start()]
        if _re.search(r'href="[^"]*$', before):             # already inside a link
            return m.group(0)
        e = m.group(0)
        return f'<a href="mailto:{e}" style="color:#93c5fd;">{e}</a>'
    out = _EMAIL_RE.sub(_email_sub, out)                     # 2b. emails

    def _tel_sub(m):
        s = m.group(0)
        tel = _re.sub(r"[^\d+]", "", s)
        return f'<a href="tel:{tel}" style="color:#93c5fd;">{s}</a>'
    out = _TEL_RE.sub(_tel_sub, out)                         # 2c. phones

    return out.replace("\n", "<br>")                         # 3. newlines last

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
    "antelope_x": {
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
    "upper_antelope":       "https://nationalparkexpress.com/wp-content/uploads/2026/04/Upper_Antelope_BSCT_lg.jpg",
    "lower_antelope":       "https://nationalparkexpress.com/wp-content/uploads/2023/09/leon-liu-_0aOFIW34rw-unsplash-scaled.jpg",
    "antelope_x":            "https://nationalparkexpress.com/wp-content/uploads/2023/09/leon-liu-_0aOFIW34rw-unsplash-scaled.jpg",
    "grand_canyon_south":   "https://nationalparkexpress.com/wp-content/uploads/2024/04/National-Park-Express-Which-Section-of-the-Grand-Canyon-img1.jpg",
    "grand_canyon_west":    "https://nationalparkexpress.com/wp-content/uploads/2023/04/GCW_Banner.jpg",
    "bryce_zion":           "https://nationalparkexpress.com/wp-content/uploads/2023/01/6Bryce.jpg",
    "valley_of_fire_full":  "https://nationalparkexpress.com/wp-content/uploads/2026/01/3ValleyofFire-scaled-1-1.jpg",
    "valley_of_fire_half":  "https://nationalparkexpress.com/wp-content/uploads/2026/01/3ValleyofFire-scaled-1-1.jpg",
    "hoover_dam":           "https://nationalparkexpress.com/wp-content/uploads/2023/06/hoover-dam-img1.jpg",
}

LOGO_URL = "https://nationalparkexpress.com/wp-content/uploads/2026/03/image002.png"


# ── SMS body ─────────────────────────────────────────────────────────────────
async def build_sms(first_name: str, tour_type: str, tour_date: str, form_url: str,
                    db: AsyncSession) -> str:
    cfg = TOUR_TYPES.get(tour_type, {})
    label = cfg.get("label", tour_type)
    try:
        date_fmt = datetime.strptime(tour_date, "%Y-%m-%d").strftime("%B %-d, %Y")
    except ValueError:
        date_fmt = tour_date

    # SMS is plain text — do NOT HTML-escape (would corrupt & ' etc.); bare .replace().
    if cfg.get("has_lunch"):
        tmpl = await _copy(db, "tmpl__global__tc_sms_with_lunch",
            "Hi {name}, This is National Park Express, your local tour operator "
            "for {label} on {date}. Please reconfirm your tour and select your lunch "
            "option here: {url}. Thank you")
    else:
        tmpl = await _copy(db, "tmpl__global__tc_sms_no_lunch",
            "Hi {name}, This is National Park Express, your local tour operator "
            "for {label} on {date}. Please reconfirm your tour here: {url}. Thank you")

    return (tmpl
            .replace("{name}", first_name)
            .replace("{label}", label)
            .replace("{date}", date_fmt)
            .replace("{url}", form_url))


# ── Email body ───────────────────────────────────────────────────────────────
async def build_email(row: dict, tour_type: str, tour_date: str, form_url: str,
                pickup_instruction: str = "", pickup_photo_url: str = "",
                pickup_photo_label: str = "", db: AsyncSession = None) -> str:
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

    # ── Content Studio editable copy (DB-backed) ──────────────────────────────
    # Rendering mirrors settings_templates.html preview byte-for-byte:
    #   greeting/review/closing/expiry : esc(value)
    #   intro                          : esc(value) -> .replace('{label}', label) -> fill {date}
    #   footer                         : esc -> linkify -> nl2br
    # label/date are injected as PLAIN TEXT (exactly like preview's tourLabel/SAMPLE.date).
    # Per product decision: a blank value = admin removed that line, so the whole
    # <p> block is omitted (no empty paragraph); fallback English only on DB error.
    greeting_raw = await _copy(db, "tmpl__global__tc_email_greeting",
        "Greetings from National Park Express!")
    intro_raw = await _copy(db, "tmpl__global__tc_email_intro",
        "As your local tour operator for the {label}, we're excited to welcome you on {date}.")
    review_raw = await _copy(db, "tmpl__global__tc_email_review",
        "Please review your tour details below and reconfirm your participation so we can ensure everything is ready for your visit.")
    closing_raw = await _copy(db, "tmpl__global__tc_email_closing",
        "Thank you for choosing National Park Express. We are honored to be part of your adventure and are committed to making your experience smooth, enjoyable and filled with lasting memories.")
    expiry_raw = await _copy(db, "tmpl__global__tc_email_link_expiry",
        "Link expires at 6:00 PM PST the day before your tour")
    footer_raw = await _copy(db, "tmpl__global__tc_email_footer_contact",
        "Questions? We're here to help!")

    _PSTYLE = "font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:14px;font-weight:400;color:#24364f;line-height:1.7;letter-spacing:-0.1px;"
    def _para(raw_text, margin, extra_html=""):
        """Render one <p> only if there's content; empty -> '' (no blank paragraph)."""
        body = _esc(raw_text).strip()
        if not body and not extra_html:
            return ""
        return f'<p style="{_PSTYLE}margin:{margin};">{body}{extra_html}</p>'

    # intro: replace {label} then {date}, both plain text (matches preview)
    intro_body = _esc(intro_raw).replace("{label}", _esc(label)).replace("{date}", _esc(date_fmt))
    intro_html = (f'<p style="{_PSTYLE}margin:0 0 6px;">{intro_body}</p>' if intro_body.strip() else "")

    greeting_html = _para(greeting_raw, "0 0 6px")
    review_extra = ('  Please also select your <strong style="font-weight:600;">lunch option</strong> using the button below.'
                    if has_lunch else "")
    review_html = _para(review_raw, "0 0 6px", review_extra)
    closing_html = _para(closing_raw, "0 0 28px")
    link_expiry_txt = _esc(expiry_raw)            # rendered inside its own existing <p>
    footer_txt = _footer_html(footer_raw)         # esc -> linkify -> nl2br

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
                <div style="width:36px;height:36px;border-radius:9px;background:#eef6ff;text-align:center;line-height:36px;font-size:18px;">&#128101;</div>
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
    {greeting_html}
    {intro_html}
    {review_html}
    {closing_html}

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
        <p style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:11px;font-weight:300;color:#aaa;margin:6px 0 0;">{link_expiry_txt}</p>
      </td></tr>
    </table>

  </td></tr>

  <!-- Footer -->
  <tr><td style="background:#061a33;padding:20px 36px;text-align:center;">
    <img src="{LOGO_URL}" alt="NPE Logo" width="60" style="width:60px;height:60px;object-fit:contain;border-radius:50%;margin-bottom:12px;" />
    <p style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:13px;font-weight:300;color:#dbeafe;line-height:1.7;margin:0;">{footer_txt}</p>
  </td></tr>

</table>
</td></tr></table>
</body>
</html>"""

# ── Last Minute Email ─────────────────────────────────────────────────────────
async def build_last_minute_email(row: dict, tour_type: str, tour_date: str, form_url: str,
                            pickup_instruction: str = "", pickup_photo_url: str = "",
                            pickup_photo_label: str = "", db: AsyncSession = None) -> str:
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

    # ── Content Studio editable copy (Last Minute) — mirrors renderTcLmEmailPreview ──
    # Order: greeting(DB) -> "As your local…" (hard-coded, also hard-coded in preview)
    #        -> lm_intro(DB with/no lunch) -> lm_closing(DB). btn/expiry/footer from DB.
    lm_greeting_raw = await _copy(db, "tmpl__global__tc_email_greeting",
        "Greetings from National Park Express!")
    if has_lunch:
        lm_intro_raw = await _copy(db, "tmpl__global__tc_lm_email_intro_with_lunch",
            "Please review your tour details below and select your lunch option using the button below to help ensure a smooth and hassle-free departure.")
    else:
        lm_intro_raw = await _copy(db, "tmpl__global__tc_lm_email_intro_no_lunch",
            "Please review your tour details below and confirm your pickup information to help ensure a smooth and hassle-free departure.")
    lm_closing_raw = await _copy(db, "tmpl__global__tc_lm_email_closing",
        "We look forward to seeing you soon.")
    lm_expiry_raw = await _copy(db, "tmpl__global__tc_email_link_expiry",
        "Link expires at 6:00 PM PST the day before your tour")
    lm_footer_raw = await _copy(db, "tmpl__global__tc_email_footer_contact",
        "Questions? We're here to help!")

    _LMPSTYLE = "font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:14px;font-weight:400;color:#24364f;line-height:1.7;letter-spacing:-0.1px;"
    def _lmpara(raw_text, margin):
        body = _esc(raw_text).strip()
        return f'<p style="{_LMPSTYLE}margin:{margin};">{body}</p>' if body else ""

    lm_greeting_html = _lmpara(lm_greeting_raw, "0 0 6px")
    lm_intro_html    = _lmpara(lm_intro_raw, "0 0 6px")
    lm_closing_html  = _lmpara(lm_closing_raw, "0 0 28px")
    lm_expiry_txt    = _esc(lm_expiry_raw)
    lm_footer_txt    = _footer_html(lm_footer_raw)

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
                <div style="width:36px;height:36px;border-radius:9px;background:#eef6ff;text-align:center;line-height:36px;font-size:18px;">&#128101;</div>
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
    if has_lunch:
        _btn_db = await _copy(db, "tmpl__global__tc_lm_email_btn_lunch", "")
        btn_text = _esc(_btn_db) if _btn_db.strip() else "🍴 SELECT MY LUNCH OPTION"
    else:
        _btn_db = await _copy(db, "tmpl__global__tc_lm_email_btn_no_lunch", "")
        btn_text = _esc(_btn_db) if _btn_db.strip() else "&#10003; I'VE READ THIS MESSAGE"

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
    {lm_greeting_html}
    <p style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:14px;font-weight:400;color:#24364f;line-height:1.7;margin:0 0 6px;letter-spacing:-0.1px;">
      As your local tour operator for the <strong style="font-weight:600;">{label}</strong>, we're excited to welcome you on <strong style="color:#2563eb;font-weight:600;">{date_fmt}</strong>.
    </p>
    {lm_intro_html}
    {lm_closing_html}

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
        <p style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:11px;font-weight:300;color:#aaa;margin:6px 0 0;">{lm_expiry_txt}</p>
      </td></tr>
    </table>

  </td></tr>

  <tr><td style="background:#061a33;padding:20px 36px;text-align:center;">
    <img src="{LOGO_URL}" alt="NPE Logo" width="60" style="width:60px;height:60px;object-fit:contain;border-radius:50%;margin-bottom:12px;" />
    <p style="font-family:'Nunito Sans','Segoe UI',Arial,sans-serif;font-size:13px;font-weight:300;color:#dbeafe;line-height:1.7;margin:0;">{lm_footer_txt}</p>
  </td></tr>

</table>
</td></tr></table>
</body>
</html>"""
