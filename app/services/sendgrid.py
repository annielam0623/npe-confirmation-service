import os
from datetime import datetime
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, To

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL", "confirmations@nationalparkexpress.com")
FROM_NAME = os.getenv("FROM_NAME", "National Park Express")
BASE_URL = os.getenv("BASE_URL", "https://confirm.nationalparkexpress.com")


def _get_client():
    if not SENDGRID_API_KEY:
        raise RuntimeError("SENDGRID_API_KEY not set")
    return SendGridAPIClient(SENDGRID_API_KEY)


async def send_confirmation_email(booking) -> dict:
    """Send tour confirmation email to guest."""
    confirm_url = f"{BASE_URL}/confirm/{booking.confirm_token}"
    tour_date_str = booking.tour_date.strftime("%B %d, %Y") if booking.tour_date else "TBD"
    pickup_time_str = booking.pickup_time.strftime("%I:%M %p") if booking.pickup_time else "TBD"

    html_content = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: Georgia, serif; color: #2c2c2c; max-width: 600px; margin: 0 auto; padding: 20px; }}
    .header {{ background: #1a3c2e; color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }}
    .header h1 {{ margin: 0; font-size: 24px; letter-spacing: 1px; }}
    .body {{ background: #f9f6f0; padding: 30px; border-radius: 0 0 8px 8px; }}
    .detail-row {{ display: flex; margin: 10px 0; border-bottom: 1px solid #e0d8cc; padding-bottom: 10px; }}
    .label {{ font-weight: bold; width: 150px; color: #5a4a3a; }}
    .value {{ flex: 1; }}
    .confirm-btn {{ display: block; background: #c8502a; color: white; text-align: center; padding: 16px 32px;
                    text-decoration: none; border-radius: 6px; font-size: 18px; margin: 30px auto; width: fit-content; }}
    .footer {{ text-align: center; color: #888; font-size: 12px; margin-top: 20px; }}
  </style>
</head>
<body>
  <div class="header">
    <h1>🏔️ National Park Express</h1>
    <p style="margin:8px 0 0 0; opacity:0.85;">Your Tour Confirmation</p>
  </div>
  <div class="body">
    <p>Dear {booking.guest_first_name},</p>
    <p>Your tour is confirmed! Here are your details:</p>

    <div class="detail-row"><span class="label">Tour:</span><span class="value">{booking.tour_name}</span></div>
    <div class="detail-row"><span class="label">Date:</span><span class="value">{tour_date_str}</span></div>
    <div class="detail-row"><span class="label">Pickup Time:</span><span class="value">{pickup_time_str}</span></div>
    <div class="detail-row"><span class="label">Pickup Location:</span><span class="value">{booking.pickup_location}</span></div>
    <div class="detail-row"><span class="label">Guests:</span><span class="value">{booking.party_size}</span></div>
    {"<div class='detail-row'><span class='label'>Driver:</span><span class='value'>" + booking.driver_name + "</span></div>" if booking.driver_name else ""}
    {"<div class='detail-row'><span class='label'>Bus #:</span><span class='value'>" + booking.bus_number + "</span></div>" if booking.bus_number else ""}
    {"<div class='detail-row'><span class='label'>Notes:</span><span class='value'>" + booking.special_notes + "</span></div>" if booking.special_notes else ""}

    <a class="confirm-btn" href="{confirm_url}">✓ Confirm Your Spot</a>

    <p style="color:#666; font-size:13px; text-align:center;">
      Please click the button above to confirm your booking and select your lunch preference.
    </p>
  </div>
  <div class="footer">
    <p>National Park Express · Las Vegas, NV<br>
    Questions? Reply to this email or call us.</p>
  </div>
</body>
</html>
"""

    message = Mail(
        from_email=(FROM_EMAIL, FROM_NAME),
        to_emails=booking.guest_email,
        subject=f"✓ Tour Confirmation – {booking.tour_name} on {tour_date_str}",
        html_content=html_content,
    )

    sg = _get_client()
    response = sg.send(message)
    return {
        "status_code": response.status_code,
        "message_id": response.headers.get("X-Message-Id"),
    }


async def send_morning_reminder_email(booking) -> dict:
    """Send morning pickup reminder email."""
    pickup_time_str = booking.pickup_time.strftime("%I:%M %p") if booking.pickup_time else "TBD"

    html_content = f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>
  body {{ font-family: Georgia, serif; color: #2c2c2c; max-width: 600px; margin: 0 auto; padding: 20px; }}
  .header {{ background: #1a3c2e; color: white; padding: 24px; text-align: center; border-radius: 8px 8px 0 0; }}
  .body {{ background: #f9f6f0; padding: 30px; border-radius: 0 0 8px 8px; }}
  .highlight {{ background: #c8502a; color: white; padding: 20px; border-radius: 6px; text-align: center; font-size: 20px; margin: 20px 0; }}
</style></head>
<body>
  <div class="header"><h1>🌅 Good Morning, {booking.guest_first_name}!</h1></div>
  <div class="body">
    <p>Your National Park Express tour is <strong>TODAY</strong>. Here's a quick reminder:</p>
    <div class="highlight">
      🚌 Pickup at <strong>{pickup_time_str}</strong><br>
      📍 {booking.pickup_location}
    </div>
    {"<p><strong>Your driver:</strong> " + booking.driver_name + " &nbsp;|&nbsp; <strong>Bus #:</strong> " + booking.bus_number + "</p>" if booking.driver_name else ""}
    {"<p><strong>Driver phone:</strong> " + booking.driver_phone + "</p>" if booking.driver_phone else ""}
    <p>Please be ready <strong>5–10 minutes early</strong>. Have a wonderful tour!</p>
  </div>
</body>
</html>
"""

    message = Mail(
        from_email=(FROM_EMAIL, FROM_NAME),
        to_emails=booking.guest_email,
        subject=f"🌅 Today's Tour Reminder – Pickup at {pickup_time_str}",
        html_content=html_content,
    )

    sg = _get_client()
    response = sg.send(message)
    return {"status_code": response.status_code, "message_id": response.headers.get("X-Message-Id")}


async def send_raw_email(to_email: str, to_name: str, subject: str, html_body: str) -> dict:
    """Send a pre-rendered email. Used by scheduler."""
    message = Mail(
        from_email=(FROM_EMAIL, FROM_NAME),
        to_emails=to_email,
        subject=subject,
        html_content=html_body,
    )
    sg = _get_client()
    response = sg.send(message)
    return {"status_code": response.status_code, "message_id": response.headers.get("X-Message-Id")}
