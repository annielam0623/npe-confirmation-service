"""
NPE Webhook Router
Receives Rezdy order webhooks and upserts into bookings table.

Endpoints (configured in Rezdy UI):
  POST /webhook/rezdy   ← single URL for all three event types
                          Rezdy sends newOrder / updatedOrder / cancelledOrder
                          all with the same payload shape; we differentiate by status.
"""

import json
import secrets
from datetime import datetime, date
from typing import Optional
from unittest import result

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from zoneinfo import ZoneInfo

from app.database import get_db
from app.models import Booking, BookingSource, BookingStatus, ManifestProduct

router = APIRouter()


# ─── Field helpers ────────────────────────────────────────────────────────────

def _get_field(fields: list[dict], *labels: str) -> Optional[str]:
    """
    Search a Rezdy fields array for any matching label (case-insensitive).
    Returns the first non-empty value found, or None.

    Rezdy custom fields look like:
      [{"label": "TT #", "value": "12345"}, ...]
    """
    if not fields:
        return None
    labels_lower = [l.lower() for l in labels]
    for f in fields:
        if isinstance(f, dict) and f.get("label", "").lower() in labels_lower:
            v = f.get("value", "")
            if v and str(v).strip():
                return str(v).strip()
    return None


def _extract_quantities(items: list[dict]) -> int:
    """Sum totalQuantity across all items."""
    total = 0
    for item in items:
        total += item.get("totalQuantity", 0)
    return total or 1


def _parse_start_date(start_time: Optional[str]) -> Optional[date]:
    """
    Parse Rezdy startTime → Python date.
    Rezdy format: "2017-08-16T09:00:00Z" or "2017-08-16 19:00:00"
    """
    if not start_time:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(start_time[:19], fmt[:len(start_time[:19])]).date()
        except ValueError:
            continue
    return None


def _parse_start_time(start_time: Optional[str]) -> Optional[str]:
    """
    Extract HH:MM AM/PM from Rezdy startTimeLocal.
    e.g. "2017-08-16 06:00:00" → "6:00 AM"
    """
    if not start_time:
        return None
    try:
        # Try local time first (no Z suffix)
        dt = datetime.strptime(start_time[:19], "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%-I:%M %p")   # e.g. "6:00 AM"
    except Exception:
        pass
    try:
        dt = datetime.strptime(start_time[:19], "%Y-%m-%dT%H:%M:%S")
        return dt.strftime("%-I:%M %p")
    except Exception:
        return None


def _parse_lunch(special_req: str) -> dict:
    """
    Parse lunch counts from Order Special Requirements string.
    Rezdy sends e.g. "2 turkey 1 beef" or "3 Turkey Sandwich 1 Veggie"
    Returns dict with turkey / veggie / beef counts.
    """
    s = (special_req or "").lower()
    import re

    def _find(pattern):
        m = re.search(r'(\d+)\s*' + pattern, s)
        return int(m.group(1)) if m else 0

    return {
        "lunch_turkey": _find(r'turkey'),
        "lunch_veggie": _find(r'veg(?:gie|etarian)?'),
        "lunch_beef":   _find(r'beef'),
    }


# ─── Main parser ──────────────────────────────────────────────────────────────

def _parse_order(payload: dict) -> Optional[dict]:
    order_number = str(payload.get("orderNumber", "") or "").strip()
    if not order_number:
        return None

    customer = payload.get("customer") or {}
    first_name = str(customer.get("firstName", "") or "").strip()
    last_name = str(customer.get("lastName", "") or "").strip()
    email = str(customer.get("email", "") or "").strip()
    phone = (
        str(customer.get("mobile", "") or "").strip()
        or str(customer.get("phone", "") or "").strip()
    )

    # Do NOT reject order if email is missing.
    # Rezdy PROCESSING webhook may not have complete customer data yet.

    items = payload.get("items") or []
    item = items[0] if items else {}

    product_code = str(item.get("productCode", "") or "").strip()
    product_name = str(item.get("productName", "") or "").strip()

    start_time_local = item.get("startTimeLocal") or item.get("startTime")
    tour_date = _parse_start_date(start_time_local)
    pickup_time = _parse_start_time(start_time_local)

    quantities = _extract_quantities(items)

    order_fields = payload.get("fields") or []
    participants = item.get("participants") or []
    part_fields = participants[0].get("fields", []) if participants else []

    tt_number = _get_field(order_fields, "TT #", "TT#", "TT Number")

    confirmation_no = (
        _get_field(
            order_fields,
            "Confirmation #",
            "Confirmation#",
            "Antelope Canyon X Confirmation #",
            "Lower Antelope Canyon Confirmation #",
            "Confirmation Number",
        )
        or _get_field(
            part_fields,
            "Confirmation #",
            "Confirmation#",
            "Barcode",
            "Ticket Number",
        )
    )

    def _extract_location(val) -> Optional[str]:
        if not val:
            return None
        if isinstance(val, str):
            return val.strip() or None
        if isinstance(val, dict):
            return (
                str(val.get("locationName") or val.get("name") or "").strip()
                or None
            )
        return None

    raw_pickup = payload.get("pickupLocation") or item.get("pickupLocation")
    pickup_location = (
        _extract_location(raw_pickup)
        or _get_field(
            part_fields,
            "Pick-up Location",
            "Pickup Location",
            "Hotel Name",
            "Hotel",
            "Pick Up Location",
        )
        or _get_field(order_fields, "Pick-up Location", "Pickup Location")
    )

    pickup_location_obj = payload.get("pickupLocation") or item.get("pickupLocation") or {}
    pickup_time_raw = (
        pickup_location_obj.get("pickupTime")
        if isinstance(pickup_location_obj, dict)
        else None
    )
    pickup_time = _parse_start_time(pickup_time_raw) or pickup_time

    special_req = str(payload.get("comments", "") or "").strip()
    item_req = str(item.get("comments", "") or "").strip()
    if item_req and item_req not in special_req:
        special_req = f"{special_req} {item_req}".strip()

    field_req = _get_field(
        order_fields,
        "Order Special Requirements",
        "Special Requirements",
        "Special Needs",
    )
    if field_req and field_req not in special_req:
        special_req = f"{special_req} {field_req}".strip()

    lunch = _parse_lunch(special_req)
    agent_name = str(payload.get("resellerName", "") or "").strip()

    return {
        "order_number": order_number,
        "rezdy_order_id": order_number,
        "rezdy_status": str(payload.get("status", "") or "").strip().upper(),
        "product_code": product_code or None,
        "product_name": product_name or None,
        "tt_number": tt_number,
        "confirmation_no": confirmation_no,
        "first_name": first_name or "Guest",
        "last_name": last_name or "",
        "customer_email": email or "",
        "phone": phone or None,
        "quantities": quantities,
        "tour_date": tour_date,
        "pickup_time": pickup_time,
        "pickup_location": pickup_location or None,
        "special_requirements": special_req or None,
        "agent_name": agent_name or None,
        "lunch_turkey": lunch["lunch_turkey"],
        "lunch_veggie": lunch["lunch_veggie"],
        "lunch_beef": lunch["lunch_beef"],
        "source": BookingSource.rezdy,
    }

# ─── Booking type lookup ──────────────────────────────────────────────────────

async def _get_booking_type(db: AsyncSession, product_code: Optional[str]) -> str:
    """
    Look up booking_type via manifest_products → manifests.
    Falls back to 'bus_tour' if not configured yet.
    """
    if not product_code:
        return "bus_tour"
    result = await db.execute(
        select(ManifestProduct).where(ManifestProduct.product_code == product_code)
    )
    mp = result.scalar_one_or_none()
    if mp and mp.manifest:
        return mp.manifest.booking_type
    return "bus_tour"


# ─── Route ────────────────────────────────────────────────────────────────────

@router.post("/rezdy")
async def rezdy_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Single endpoint for all three Rezdy webhook event types:
      - newOrder       → status: PROCESSING / CONFIRMED / etc.
      - updatedOrder   → any status change
      - cancelledOrder → status: CANCELLED

    Rezdy UI config: point all three events at /webhook/rezdy
    """
    print("===== REZDY WEBHOOK HIT =====")
    # ── Parse body ──
    try:
        payload = await request.json()
    except Exception as e:
        print(f"[webhook] JSON parse error: {e}")
        return {"status": "error", "reason": "invalid json"}

    order_number = str(payload.get("orderNumber", "") or "").strip()
    rezdy_status = str(payload.get("status", "") or "").strip().upper()

    if not order_number and not rezdy_status:
        print("[webhook] ignored empty payload")
        return {"status": "ignored", "reason": "empty payload"}

    print(f"[webhook] order={order_number} status={rezdy_status}")

    # ── Handle cancellation ──
    if rezdy_status in ("CANCELLED", "DELETED"):
        result = await db.execute(
            select(Booking).where(Booking.order_number == order_number)
        )
        booking = result.scalar_one_or_none()
        if booking:
            booking.status = BookingStatus.cancelled
            await db.commit()
            print(f"[webhook] cancelled booking id={booking.id}")
            return {"status": "cancelled", "order_number": order_number}
        return {"status": "not_found", "order_number": order_number}

    # ── Skip non-actionable statuses ──
    # PROCESSING = OTA reservation not yet confirmed
    # We accept PROCESSING so the booking appears in the system early,
    # but mark it as pending until CONFIRMED arrives via updatedOrder.
    if rezdy_status not in ("CONFIRMED", "PENDING_SUPPLIER", "PENDING_CUSTOMER", "PROCESSING"):
        print(f"[webhook] skipped status={rezdy_status}")
        return {"status": "skipped", "reason": f"status={rezdy_status}"}

    # ── Parse fields ──
    fields = _parse_order(payload)
    if not fields:
        print(f"[webhook] could not parse order {order_number}")
        return {"status": "error", "reason": "parse failed"}

    # ── Resolve booking_type from manifest_products table ──
    booking_type = await _get_booking_type(db, fields.get("product_code"))

    # ── Update product_name in manifest_products if it changed ──
    if fields.get("product_code") and fields.get("product_name"):
        mp_result = await db.execute(
            select(ManifestProduct).where(
                ManifestProduct.product_code == fields["product_code"]
            )
        )
        mp = mp_result.scalar_one_or_none()
        if mp and mp.product_name != fields["product_name"]:
            mp.product_name = fields["product_name"]
            print(f"[webhook] updated product_name for {fields['product_code']}")

    # ── UPSERT ──
    result = await db.execute(
        select(Booking).where(Booking.order_number == order_number)
    )
    existing = result.scalar_one_or_none()

    if existing:
        # Update — only overwrite fields that Rezdy owns.
        # Do NOT overwrite: driver, vehicle_no, confirmation_no (if staff filled it),
        #                   lunch counts (if staff adjusted), notes
        existing.product_code   = fields["product_code"]
        existing.product_name   = fields["product_name"]
        existing.tt_number      = fields["tt_number"]
        existing.first_name     = fields["first_name"]
        existing.last_name      = fields["last_name"]
        existing.customer_email = fields["customer_email"]
        existing.phone          = fields["phone"]
        existing.quantities     = fields["quantities"]
        existing.tour_date      = fields["tour_date"]
        existing.pickup_time    = fields["pickup_time"]
        existing.pickup_location = fields["pickup_location"]
        existing.agent_name     = fields["agent_name"]
        existing.special_requirements = fields["special_requirements"]

        # Only set confirmation_no from Rezdy if staff hasn't already filled it
        if not existing.confirmation_no and fields["confirmation_no"]:
            existing.confirmation_no = fields["confirmation_no"]

        # Only set lunch from Rezdy if staff hasn't adjusted
        if not (existing.lunch_turkey or existing.lunch_veggie or existing.lunch_beef):
            existing.lunch_turkey = fields["lunch_turkey"]
            existing.lunch_veggie = fields["lunch_veggie"]
            existing.lunch_beef   = fields["lunch_beef"]

        # If status was cancelled and order comes back, re-activate
        if existing.status == BookingStatus.cancelled:
            existing.status = BookingStatus.pending

        print(f"[webhook] updated booking id={existing.id}")
        await db.execute(_text("""
    INSERT INTO activity_log (order_number, event_type, detail, actor, actor_type)
    VALUES (:order_number, :event_type, :detail, :actor, :actor_type)
"""), {
    "order_number": order_number,
    "event_type":   "booking_updated",
    "detail":       f"Rezdy updated booking — status: {fields.get('rezdy_status', '')}",
    "actor":        "rezdy",
    "actor_type":   "system",
})
    else:
        # Insert new booking
        booking = Booking(
            booking_type     = booking_type,
            source           = BookingSource.rezdy,
            status           = BookingStatus.pending,
            confirm_token    = secrets.token_urlsafe(32),
            order_number     = order_number,
            rezdy_order_id   = order_number,
            product_code     = fields["product_code"],
            product_name     = fields["product_name"],
            tt_number        = fields["tt_number"],
            confirmation_no  = fields["confirmation_no"],
            first_name       = fields["first_name"],
            last_name        = fields["last_name"],
            customer_email   = fields["customer_email"],
            phone            = fields["phone"],
            quantities       = fields["quantities"],
            tour_date        = fields["tour_date"],
            pickup_time      = fields["pickup_time"],
            pickup_location  = fields["pickup_location"],
            agent_name       = fields["agent_name"],
            special_requirements = fields["special_requirements"],
            lunch_turkey     = fields["lunch_turkey"],
            lunch_veggie     = fields["lunch_veggie"],
            lunch_beef       = fields["lunch_beef"],
        )
        db.add(booking)
        print(f"[webhook] created new booking order={order_number}")
        await db.execute(_text("""
    INSERT INTO activity_log (order_number, event_type, detail, actor, actor_type)
    VALUES (:order_number, :event_type, :detail, :actor, :actor_type)
"""), {
    "order_number": order_number,
    "event_type":   "booking_created",
    "detail":       f"New booking from Rezdy — {fields.get('product_name', '')}",
    "actor":        "rezdy",
    "actor_type":   "system",
})

    await db.commit()
    return {"status": "ok", "order_number": order_number}

# ─────────────────────────────────────────────────────────────────────────────
# APPEND THIS BLOCK to the bottom of app/routers/webhook.py
# ─────────────────────────────────────────────────────────────────────────────
#
# Delivery status callbacks
# Twilio:   POST /webhook/sms-status     (set as StatusCallback in sms.py ✓)
# SendGrid: POST /webhook/sendgrid-status (set once in SendGrid dashboard)
#
# send_log columns used:
#   sms_sid          — matched to find the row for Twilio
#   email_message_id — matched to find the row for SendGrid
#   sms_status       — updated to e.g. "delivered", "failed", "undelivered"
#   email_status     — updated to e.g. "delivered", "bounce", "dropped"
#   delivered_at     — set when delivered
# ─────────────────────────────────────────────────────────────────────────────

import json as _json
from datetime import datetime, timezone
from sqlalchemy import text as _text


@router.post("/sms-status")
async def sms_status_callback(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Twilio delivery status callback.
    Twilio POSTs application/x-www-form-urlencoded with:
      MessageSid, MessageStatus, To, From, ...
    Statuses: queued → sent → delivered / undelivered / failed
    """
    try:
        form = await request.form()
        message_sid    = str(form.get("MessageSid", "")).strip()
        message_status = str(form.get("MessageStatus", "")).strip().lower()
    except Exception as e:
        print(f"[webhook/sms-status] parse error: {e}")
        return {"status": "error"}

    if not message_sid or not message_status:
        return {"status": "ignored"}

    now_utc = datetime.now(timezone.utc)
    delivered_at = now_utc if message_status == "delivered" else None

    try:
        if delivered_at:
            await db.execute(
                _text("""
                    UPDATE send_log
                       SET sms_status   = :status,
                           delivered_at = :delivered_at
                     WHERE sms_sid = :sid
                """),
                {"status": message_status, "delivered_at": delivered_at, "sid": message_sid},
            )
        else:
            await db.execute(
                _text("""
                    UPDATE send_log
                       SET sms_status = :status
                     WHERE sms_sid = :sid
                """),
                {"status": message_status, "sid": message_sid},
            )
        await db.commit()
        print(f"[webhook/sms-status] sid={message_sid} status={message_status}")
    except Exception as e:
        print(f"[webhook/sms-status] db error: {e}")

    # Twilio expects a 200 with empty or minimal body
    return {"status": "ok"}


@router.post("/sendgrid-status")
async def sendgrid_status_callback(request: Request, db: AsyncSession = Depends(get_db)):
    """
    SendGrid Event Webhook callback.
    SendGrid POSTs a JSON array of events, each with:
      sg_message_id, event, email, timestamp, ...

    Events we care about:
      delivered  → email_status = "delivered", delivered_at = timestamp
      bounce     → email_status = "bounce"
      dropped    → email_status = "dropped"
      spamreport → email_status = "spam"

    Configure once in SendGrid dashboard:
      Settings → Mail Settings → Event Webhook → HTTP POST URL →
      https://confirm.nationalparkexpress.com/webhook/sendgrid-status
      Enable: Delivered, Bounce, Dropped, Spam Report
    """
    try:
        body = await request.body()
        events = _json.loads(body)
        if not isinstance(events, list):
            events = [events]
    except Exception as e:
        print(f"[webhook/sendgrid-status] parse error: {e}")
        return {"status": "error"}

    for event in events:
        try:
            # sg_message_id may have a suffix like ".filter-xxx" — strip it
            raw_id      = str(event.get("sg_message_id", "")).split(".")[0].strip()
            event_type  = str(event.get("event", "")).lower()
            ts          = event.get("timestamp")  # Unix timestamp int

            if not raw_id or not event_type:
                continue

            status_map = {
                "delivered":  "delivered",
                "bounce":     "bounce",
                "bounced":    "bounce",
                "dropped":    "dropped",
                "spamreport": "spam",
                "deferred":   "deferred",
            }
            new_status = status_map.get(event_type)
            if not new_status:
                continue  # open, click, unsubscribe etc. — ignore

            delivered_at = (
                datetime.fromtimestamp(ts, tz=timezone.utc)
                if ts and new_status == "delivered"
                else None
            )

            if delivered_at:
                await db.execute(
                    _text("""
                        UPDATE send_log
                           SET email_status   = :status,
                               delivered_at   = :delivered_at
                         WHERE email_message_id = :mid
                    """),
                    {"status": new_status, "delivered_at": delivered_at, "mid": raw_id},
                )
            else:
                await db.execute(
                    _text("""
                        UPDATE send_log
                           SET email_status = :status
                         WHERE email_message_id = :mid
                    """),
                    {"status": new_status, "mid": raw_id},
                )

            print(f"[webhook/sendgrid-status] msg_id={raw_id} event={event_type} → {new_status}")

        except Exception as e:
            print(f"[webhook/sendgrid-status] row error: {e}")
            continue

    await db.commit()
    return {"status": "ok"}

# ─────────────────────────────────────────────────────────────────────────────
# ADD THIS BLOCK to the bottom of app/routers/webhook.py
# (after the sendgrid_status_callback function)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/twilio/inbound")
async def twilio_inbound_sms(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Twilio inbound SMS webhook.
    Twilio POSTs application/x-www-form-urlencoded with:
      From, To, Body, MessageSid, ...

    Matching logic:
      1. Normalise the From number
      2. Find the most recent send_log row with matching phone → get booking_id
      3. Write a booking_notes row with direction='sms_in'

    Configure in Twilio console:
      Phone Numbers → your number → Messaging → A message comes in →
      Webhook → https://confirm.nationalparkexpress.com/webhook/twilio/inbound
      HTTP POST
    """
    try:
        form = await request.form()
        from_number = str(form.get("From", "")).strip()
        body_text   = str(form.get("Body", "")).strip()
        message_sid = str(form.get("MessageSid", "")).strip()
    except Exception as e:
        print(f"[webhook/twilio/inbound] parse error: {e}")
        return _twiml_response("")   # always return 200 to Twilio

    if not from_number or not body_text:
        return _twiml_response("")

    print(f"[webhook/twilio/inbound] from={from_number} sid={message_sid}")

    # ── Normalise phone: strip spaces/dashes, keep + prefix ──
    import re
    clean_from = re.sub(r"[\s\-\(\)]", "", from_number)

    # ── Find most recent send_log entry matching this phone ──
    # send_log.phone stores the number as sent (may vary in format),
    # so we match on the last 10 digits which are format-independent.
    suffix = clean_from[-10:] if len(clean_from) >= 10 else clean_from

    # ── Try tickets_reminders first, then bookings ──────────────────────────
    # tickets_reminders.id is used as booking_notes.booking_id for ticket orders
    result = await db.execute(
    _text("""
        SELECT
            tr.id          AS ticket_id,
            NULL           AS booking_id
        FROM send_log sl
        JOIN tickets_reminders tr ON tr.chd_number = sl.order_number
        WHERE RIGHT(REGEXP_REPLACE(sl.phone, '[^0-9]', '', 'g'), 10) = :suffix
          AND sl.module = 'tickets_reminder'
        ORDER BY sl.sent_at DESC
        LIMIT 1
    """),
    {"suffix": suffix},
)
    row = result.fetchone()

    if row and row.ticket_id:
        booking_id = row.ticket_id
        print(f"[webhook/twilio/inbound] matched tickets_reminders id={booking_id}")
    else:
        # fallback: check bookings table (tour / morning)
        result2 = await db.execute(
        _text("""
            SELECT b.id AS booking_id
            FROM send_log sl
            JOIN bookings b ON b.order_number = sl.order_number
            WHERE RIGHT(REGEXP_REPLACE(sl.phone, '[^0-9]', '', 'g'), 10) = :suffix
            ORDER BY sl.sent_at DESC
            LIMIT 1
        """),
        {"suffix": suffix},
    )
        row2 = result2.fetchone()
        if not row2 or not row2.booking_id:
            print(f"[webhook/twilio/inbound] no matching booking for {from_number}")
            return _twiml_response("")
        booking_id = row2.booking_id
        print(f"[webhook/twilio/inbound] matched bookings id={booking_id}")

    # ── Write to booking_notes ──
    now_la = datetime.now(ZoneInfo("America/Los_Angeles"))
    await db.execute(
        _text("""
            INSERT INTO booking_notes
              (booking_id, author_username, body, direction, channel, created_at)
            VALUES
              (:booking_id, 'guest', :body, 'sms_in', 'sms', :created_at)
        """),
        {
            "booking_id": booking_id,
            "body":       body_text,
            "created_at": now_la,
        },
    )
    await db.commit()
    print(f"[webhook/twilio/inbound] wrote sms_in note for booking_id={booking_id}")

    # ── Return empty TwiML (no auto-reply) ──
    return _twiml_response("")


def _twiml_response(message: str):
    """Return a minimal TwiML response. Empty message = no auto-reply."""
    from fastapi.responses import Response
    if message:
        xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{message}</Message></Response>'
    else:
        xml = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
    return Response(content=xml, media_type="application/xml")
