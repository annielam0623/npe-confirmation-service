"""
SendGrid email sender.
Mirrors PHP tconf_send_mail / npe_ops_send_email.
"""
from __future__ import annotations
import os
import httpx

SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
DEFAULT_FROM_EMAIL = "confirmations@nationalparkexpress.com"
DEFAULT_FROM_NAME  = "National Park Express"


def send_email(
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,
    from_email: str = DEFAULT_FROM_EMAIL,
    from_name: str = DEFAULT_FROM_NAME,
) -> dict:
    """
    Send HTML email via SendGrid.
    Returns {"success": True} or {"success": False, "error": "..."}
    """
    if not SENDGRID_API_KEY:
        return {"success": False, "error": "SendGrid API key not configured"}

    payload = {
        "personalizations": [{"to": [{"email": to_email, "name": to_name}]}],
        "from": {"email": from_email, "name": from_name},
        "subject": subject,
        "content": [{"type": "text/html", "value": html_body}],
    }

    try:
        resp = httpx.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {SENDGRID_API_KEY}",
                "Content-Type":  "application/json",
            },
            json=payload,
            timeout=15,
        )
    except Exception as e:
        return {"success": False, "error": str(e)}

    if resp.status_code in range(200, 300):
        return {"success": True}

    try:
        errors = resp.json().get("errors", [])
        msg = errors[0].get("message", f"HTTP {resp.status_code}") if errors else f"HTTP {resp.status_code}"
    except Exception:
        msg = f"HTTP {resp.status_code}"
    return {"success": False, "error": msg}
