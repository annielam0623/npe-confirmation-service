"""
Twilio SMS sender — mirrors PHP tconf_send_sms / npe_ops_send_sms
Uses Messaging Service SID (not From number), same as v4.17.13.
StatusCallback points to /webhook/sms-status for delivery tracking.
"""
from __future__ import annotations
import os
import asyncio
import httpx

TWILIO_ACCOUNT_SID   = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN    = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_MESSAGING_SID = os.environ.get("TWILIO_MESSAGING_SERVICE_SID", "")

# Base URL of this service — used to build the StatusCallback URL
SERVICE_BASE_URL = os.environ.get("SERVICE_BASE_URL", "https://confirm.nationalparkexpress.com")


def send_sms(to_phone: str, body: str, module: str = "") -> dict:
    """
    Send an SMS via Twilio Messaging Service (synchronous).
    Returns:
        {"success": True,  "sid": "SMxxx", "module": module}
        {"success": False, "error": "...",  "module": module}
    """
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_MESSAGING_SID]):
        return {"success": False, "error": "Twilio not configured", "module": module}

    phone = _normalise_phone(to_phone)
    if not phone:
        return {"success": False, "error": f"Invalid phone: {to_phone}", "module": module}

    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    callback_url = f"{SERVICE_BASE_URL}/webhook/sms-status"

    try:
        resp = httpx.post(
            url,
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            data={
                "MessagingServiceSid": TWILIO_MESSAGING_SID,
                "To":                  phone,
                "Body":                body,
                "StatusCallback":      callback_url,
            },
            timeout=15,
        )
    except Exception as e:
        return {"success": False, "error": str(e), "module": module}

    if resp.status_code in range(200, 300):
        data = resp.json()
        return {"success": True, "sid": data.get("sid", ""), "module": module}

    try:
        msg = resp.json().get("message", f"HTTP {resp.status_code}")
    except Exception:
        msg = f"HTTP {resp.status_code}"
    return {"success": False, "error": msg, "module": module}


async def send_sms_async(to_phone: str, body: str, module: str = "") -> dict:
    """
    Async wrapper around send_sms() — for use in async contexts (scheduler, etc.)
    Runs the synchronous send_sms in a thread pool to avoid blocking the event loop.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: send_sms(to_phone, body, module))


def _normalise_phone(raw: str) -> str:
    """Normalise to E.164. Returns empty string if too short."""
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits[0] == "1":
        return f"+{digits}"
    if len(digits) >= 7:
        return f"+{digits}"
    return ""
