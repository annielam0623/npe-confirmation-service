"""
app/services/twilio_sms.py
Async Twilio via httpx — Messaging Service SID, NPE actual SMS templates
"""

import os
from urllib.parse import urlencode, quote
import httpx

TWILIO_ACCOUNT_SID   = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN    = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_MESSAGING_SERVICE_SID = os.getenv("TWILIO_MESSAGING_SERVICE_SID", "")  # MG...
BASE_URL             = os.getenv("BASE_URL", "https://confirm.nationalparkexpress.com")
SUPPORT_PHONE        = os.getenv("SUPPORT_PHONE", "702-948-4190")

from app.services.tour_config import TOUR_TYPES


# ── Internal send ─────────────────────────────────────────────────────────────

async def _send(to_phone: str, body: str) -> dict:
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_MESSAGING_SERVICE_SID:
        raise RuntimeError("Twilio credentials not set")

    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            url,
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            data={
                "MessagingServiceSid": TWILIO_MESSAGING_SERVICE_SID,
                "To":   to_phone,
                "Body": body,
            },
        )

    data = resp.json()
    if resp.status_code == 201:
        return {"sid": data.get("sid"), "status": data.get("status")}
    raise RuntimeError(f"Twilio error {resp.status_code}: {data.get('message', resp.text[:200])}")


def _fmt_date(d) -> str:
    from datetime import datetime
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


# ── Tour Confirmation SMS ─────────────────────────────────────────────────────

async def send_confirmation_sms(booking) -> dict:
    """
    Tour confirmation SMS — matches PHP npe_tconf_sms().
    Includes lunch mention if tour has lunch option.
    """
    if not booking.phone:
        return {"skipped": True, "reason": "no phone number"}

    tour_config  = TOUR_TYPES.get(booking.tour_type or "", list(TOUR_TYPES.values())[0])
    tour_label   = tour_config["label"]
    has_lunch    = tour_config.get("has_lunch", False)
    tour_date_f  = _fmt_date(booking.tour_date)
    confirm_url  = f"{BASE_URL}/confirm/{booking.confirm_token}"

    if has_lunch:
        body = (
            f"Hi {booking.first_name}! This is National Park Express, your local tour operator "
            f"for {tour_label} on {tour_date_f}. "
            f"Please confirm your tour and select your lunch option here: {confirm_url}. Thank you"
        )
    else:
        body = (
            f"Hi {booking.first_name}! This is National Park Express, your local tour operator "
            f"for {tour_label} on {tour_date_f}. "
            f"Please confirm your tour here: {confirm_url}. Thank you"
        )

    return await _send(booking.phone, body)


# ── Morning Reminder SMS ──────────────────────────────────────────────────────

async def send_morning_reminder_sms(booking) -> dict:
    """
    Morning pickup reminder SMS — matches PHP npe_morning_sms().
    Includes real-time vehicle tracking link.
    """
    if not booking.phone:
        return {"skipped": True, "reason": "no phone number"}

    pickup_time = _fmt_time(booking.pickup_time)
    van_key     = booking.vehicle_no or booking.driver or ""
    track_url   = (
        f"{BASE_URL}/?van={quote(van_key)}"
        f"&order={quote(booking.order_number or '')}"
        f"&name={quote(booking.first_name or '')}"
        f"&phone={quote(booking.phone or '')}"
    )

    body = "\n".join([
        f"Good morning, {booking.first_name}.",
        f"This is a reminder that your pickup time for today's tour is {pickup_time}.",
        "Please use the link below to check in when you arrive at your pickup location and to track your vehicle in real time:",
        track_url,
        f"If you need assistance, please call {SUPPORT_PHONE}.",
    ])

    return await _send(booking.phone, body)


# ── Ticket Reminder SMS ───────────────────────────────────────────────────────

async def send_ticket_reminder_sms(booking) -> dict:
    """
    Ticket/self-drive reminder SMS — matches PHP tickets_reminder module.
    """
    if not booking.phone:
        return {"skipped": True, "reason": "no phone number"}

    tour_config  = TOUR_TYPES.get(booking.tour_type or "", {})
    tour_label   = tour_config.get("label", booking.tour_type or "Tour")
    tour_date_f  = _fmt_date(booking.tour_date)
    checkin_time = _fmt_time(booking.checkin_time)
    tour_time    = _fmt_time(booking.tour_time)

    body = (
        f"Hi {booking.first_name}! This is National Park Express. "
        f"Your {tour_label} is on {tour_date_f}. "
        f"Check-in Time: {checkin_time}. Tour Time: {tour_time}. "
        f"Confirmation #: {booking.confirmation_no or '—'}. "
        f"Please reply YES to confirm. Questions? Call {SUPPORT_PHONE}."
    )

    return await _send(booking.phone, body)


# ── Raw send (used by scheduler) ─────────────────────────────────────────────

async def send_raw_sms(to_phone: str, body: str) -> dict:
    return await _send(to_phone, body)
