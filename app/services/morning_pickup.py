"""
Morning Pickup Reminder service — mirrors morning-pickup.php v1.3.18
SMS + Email templates. Tracking URL uses van=vehicle_no&order=order_number.
"""
from __future__ import annotations
import os

TRACKING_BASE_URL = os.environ.get("TRACKING_BASE_URL", "https://confirm.nationalparkexpress.com")
SUPPORT_PHONE = os.environ.get("SUPPORT_PHONE", "702-948-4190")


def _tracking_url(row: dict) -> str:
    """
    If send.py already injected a short link into row["tracking_url"], use it.
    Otherwise fall back to building the full URL (name/phone exposed) — used
    for direct calls outside the send flow.
    """
    if row.get("tracking_url"):
        return row["tracking_url"]
    import urllib.parse
    van = row.get("vehicle_no") or row.get("driver", "")
    base = TRACKING_BASE_URL.rstrip("/")
    params = urllib.parse.urlencode({
        "van":   van,
        "order": row.get("order_number", ""),
        "name":  row.get("name", ""),
        "phone": row.get("phone", ""),
    })
    return f"{base}/tracking?{params}"


def build_sms(row: dict) -> str:
    """Mirrors npe_morning_sms()"""
    url = _tracking_url(row)
    name = row.get("name", "")
    pickup_time = row.get("pickup_time", "")
    return (
        f"Good morning, {name}.\n"
        f"This is a reminder that your pickup time for today's tour is {pickup_time}.\n"
        f"Please use the link below to check in when you arrive at your pickup location "
        f"and to track your vehicle in real time:\n"
        f"{url}\n"
        f"If you need assistance, please call {SUPPORT_PHONE}."
    )


def build_email(row: dict) -> str:
    """Mirrors npe_morning_email()"""
    url = _tracking_url(row)
    name = row.get("name", "")
    pickup_time = row.get("pickup_time", "")

    inner = f"""
        <p style="font-size:16px">Hi <strong>{name}</strong>,</p>
        <p style="color:#555;line-height:1.7">
            This is a reminder that your pickup time for today's tour is
            <strong style="color:#1a3a5c">{pickup_time}</strong>.
        </p>
        <p style="color:#555;line-height:1.7">
            Please use the link below to check in when you arrive at your pickup location
            and to track your vehicle in real time:
        </p>
        <div style="text-align:center;margin:28px 0">
            <a href="{url}"
               style="display:inline-block;background:#1a3a5c;color:#fff;text-decoration:none;
                      padding:14px 40px;border-radius:8px;font-size:15px;font-weight:bold">
               Check In &amp; Track Vehicle
            </a>
        </div>
        <p style="color:#999;font-size:12px;text-align:center">
            If you need assistance, please call {SUPPORT_PHONE}
        </p>"""

    return _email_wrap(inner)


def email_subject(row: dict) -> str:
    return f"Your Pickup Reminder — {row.get('pickup_time', '')}"


def _email_wrap(inner: str) -> str:
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f8;padding:30px 0;"><tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">
  <tr><td style="background:#1a3a5c;border-radius:12px 12px 0 0;padding:32px;text-align:center;">
    <img src="https://nationalparkexpress.com/wp-content/uploads/2026/03/image002.png" style="width:120px;height:auto;margin-bottom:12px;" />
    <h1 style="color:#fff;margin:10px 0 4px;font-size:22px;">Morning Pickup Reminder</h1>
  </td></tr>
  <tr><td style="background:#fff;padding:32px;">{inner}</td></tr>
  <tr><td style="background:#f0f0f0;border-radius:0 0 12px 12px;padding:16px;text-align:center;">
    <p style="color:#aaa;font-size:12px;margin:0;">National Park Express — Have a great tour! 🏞️</p>
  </td></tr>
</table></td></tr></table></body></html>"""
