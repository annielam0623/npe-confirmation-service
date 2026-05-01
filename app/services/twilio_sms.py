import os
from twilio.rest import Client

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")  # e.g. +17025551234
BASE_URL = os.getenv("BASE_URL", "https://confirm.nationalparkexpress.com")


def _get_client():
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        raise RuntimeError("Twilio credentials not set")
    return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


async def send_confirmation_sms(booking) -> dict:
    """Send tour confirmation SMS."""
    if not booking.guest_phone:
        return {"skipped": True, "reason": "no phone number"}

    confirm_url = f"{BASE_URL}/confirm/{booking.confirm_token}"
    tour_date_str = booking.tour_date.strftime("%b %d") if booking.tour_date else "TBD"
    pickup_time_str = booking.pickup_time.strftime("%I:%M %p") if booking.pickup_time else "TBD"

    body = (
        f"Hi {booking.guest_first_name}! NPE Tour confirmed ✓\n"
        f"📅 {tour_date_str} at {pickup_time_str}\n"
        f"📍 {booking.pickup_location}\n"
        f"Please confirm: {confirm_url}"
    )

    client = _get_client()
    message = client.messages.create(
        body=body,
        from_=TWILIO_FROM_NUMBER,
        to=booking.guest_phone,
    )
    return {"sid": message.sid, "status": message.status}


async def send_morning_reminder_sms(booking) -> dict:
    """Send morning pickup reminder SMS."""
    if not booking.guest_phone:
        return {"skipped": True, "reason": "no phone number"}

    pickup_time_str = booking.pickup_time.strftime("%I:%M %p") if booking.pickup_time else "TBD"

    body = (
        f"🌅 NPE Reminder: Your tour is TODAY!\n"
        f"Pickup: {pickup_time_str} at {booking.pickup_location}\n"
    )
    if booking.driver_name:
        body += f"Driver: {booking.driver_name}"
    if booking.driver_phone:
        body += f" · {booking.driver_phone}"

    client = _get_client()
    message = client.messages.create(
        body=body,
        from_=TWILIO_FROM_NUMBER,
        to=booking.guest_phone,
    )
    return {"sid": message.sid, "status": message.status}


async def send_ticket_reminder_sms(booking) -> dict:
    """Send ticket/document reminder SMS (e.g., day before)."""
    if not booking.guest_phone:
        return {"skipped": True, "reason": "no phone number"}

    tour_date_str = booking.tour_date.strftime("%b %d") if booking.tour_date else "TBD"

    body = (
        f"Hi {booking.guest_first_name}! Your NPE tour is tomorrow ({tour_date_str}).\n"
        f"Please have your booking confirmation ready. Questions? Reply to this message."
    )

    client = _get_client()
    message = client.messages.create(
        body=body,
        from_=TWILIO_FROM_NUMBER,
        to=booking.guest_phone,
    )
    return {"sid": message.sid, "status": message.status}


async def send_raw_sms(to_phone: str, body: str) -> dict:
    """Send a raw SMS. Used by scheduler."""
    client = _get_client()
    message = client.messages.create(body=body, from_=TWILIO_FROM_NUMBER, to=to_phone)
    return {"sid": message.sid, "status": message.status}
