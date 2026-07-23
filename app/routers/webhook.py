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
        "first_name": first_name or None,
        "last_name": last_name or None,
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
        "source": BookingSource.rezdy.value,
    }

# ─── Product code → booking_type mapping ─────────────────────────────────────
# Update this list when new products are added in Rezdy.
# Unknown codes fall back to 'bus_tour' (safe default).

_SELF_DRIVE_CODES = {
    "P00ZPQ",   # Upper Antelope Canyon Hiking Tour (Hogan)
    "P0JEQM",   # 2026 Lower Antelope Canyon Admission Ticket (KT)
    "P0QPP8",   # Upper Antelope Canyon Admission Ticket (AACT)
    "P0SE0N",   # Antelope Valley Canyon Ligai Si Anii Tour
    "P8VPVW",   # Waterhole Canyon Experience #1
    "PK1B2V",   # 2026 Lower Antelope Canyon Admission Ticket (GYG)
    "PLFHV3",   # Upper Antelope Canyon Admission Ticket (GYG Exclusive)
    "PMKHS1",   # Lower Antelope Canyon Admission Ticket (DX)
    "PQFH2D",   # Upper Antelope Canyon Admission Ticket (AS)
    "PRGC2T",   # Upper Antelope Canyon Admission Ticket (AACT)(GYG)
    "PSUCDG",   # Waterhole Canyon Experience #4 Canyon O
    "PT0N8C",   # Antelope Canyon X Admission Ticket
    "PTTK01",   # Antelope Canyon X Admission Ticket (GYG Exclusive)
    "PWBSA0",   # Antelope Valley Canyon Ligai Si Anii Stargazing Night Tour
    "PWUDBV",   # Upper Antelope Canyon Transportation Tour (Hogan)
    "PY45SW",   # Upper Antelope Canyon Admission Ticket (TB)
}

_SHUTTLE_CODES = {
    "P649R9",   # One-way Shuttle: Springdale (Zion area) to Las Vegas
    "P6BUXR",   # One-way Shuttle: Bryce Canyon Area to Las Vegas
    "PBKRCW",   # One-way Shuttle: Las Vegas to Page, Arizona
    "PDBTC8",   # One-way Shuttle: Page, Arizona to Las Vegas
    "PDHLW9",   # One-way Shuttle: Page to St.George
    "PDR5BV",   # One-way Shuttle: St. George to Las Vegas
    "PG41NY",   # One-way Shuttle: Bryce Canyon National Park to Las Vegas
    "PG8ZGQ",   # One-way Shuttle: Las Vegas to Bryce Canyon National Park
    "PGP101",   # One-way Shuttle: Las Vegas to Zion National Park
    "PHN0QB",   # Roundtrip Shuttle: Las Vegas to Grand Canyon South Rim
    "PKG0MN",   # One-way Shuttle: Page to Kanab
    "PMDFGV",   # One-way Shuttle: Las Vegas to Tusayan (Grand Canyon Area)
    "PN5SQN",   # One-way Shuttle: Bryce Canyon Area to Zion NP
    "PNREDR",   # One-way Shuttle: Kanab to Las Vegas
    "PP0RZE",   # One-way Shuttle: St. George to Bryce Canyon Area
    "PQFLY1",   # One-way Shuttle: Las Vegas to Grand Canyon South Rim
    "PTHWQ1",   # Las Vegas to Grand Canyon South Round-trip Shuttle
    "PTXGGQ",   # One-way Shuttle: Tusayan to Las Vegas
    "PU10NT",   # One-way Shuttle: Grand Canyon South Rim to Las Vegas
    "PV1VFQ",   # One-way Shuttle: Kanab to St.George
    "PV2LB1",   # One-way Shuttle: Zion National Park to Las Vegas
    "PW5C8M",   # Grand Canyon West Day Tour with Heli & Boat SB:DP
    "PW8JBS",   # One-way Shuttle: Grand Canyon West to Las Vegas
    "PWQPS3",   # One-way Shuttle: Las Vegas to Bryce Canyon Area
    "PXCBZM",   # Grand Canyon West Rim Day Tour (Musement)
    "PZK1UA",   # One-way Shuttle: Las Vegas to St.George
    "PZYTDM",   # One-way Shuttle: Las Vegas to Grand Canyon West
}

_ADMISSIONS_CODES = {
    "P56Y49",   # Grand Canyon West Rim Admissions
}

_OTHER_CODES = {
    "PFYF01",   # Manual Admin Item
}


def _infer_booking_type(product_code: Optional[str]) -> str:
    """Look up booking_type from product_code. Falls back to 'bus_tour'."""
    if product_code in _SELF_DRIVE_CODES:
        return "self_drive"
    if product_code in _SHUTTLE_CODES:
        return "shuttle"
    if product_code in _ADMISSIONS_CODES:
        return "admissions"
    if product_code in _OTHER_CODES:
        return "other"
    return "bus_tour"


async def _get_booking_type(db: AsyncSession, product_code: Optional[str]) -> str:
    """
    Determine booking_type:
    1. Try manifest_products table (if populated in future)
    2. Fall back to product_code lookup
    """
    if product_code:
        result = await db.execute(
            select(ManifestProduct).where(ManifestProduct.product_code == product_code)
        )
        mp = result.scalar_one_or_none()
        if mp and mp.manifest:
            return mp.manifest.booking_type
    return _infer_booking_type(product_code)


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
        print(f"[webhook] payload keys: {list(payload.keys())}")
        print(f"[webhook] payload sample: {json.dumps(payload)[:500]}")
        print(f"[webhook] fields= {json.dumps(payload.get('fields'), ensure_ascii=False)}")
    except Exception as e:
        print(f"[webhook] JSON parse error: {e}")
        return {"status": "error", "reason": "invalid json"}

    order_number = str(payload.get("orderNumber", "") or "").strip()
    rezdy_status = str(payload.get("status", "") or "").strip().upper()

    if not order_number and not rezdy_status:
        print("[webhook] ignored empty payload")
        return {"status": "ignored", "reason": "empty payload"}

    print(f"[webhook] order={order_number} status={rezdy_status}")

    # ── Main processing — wrapped so ANY db/parse error returns 200 to Rezdy ──
    try:

      # ── Handle cancellation ──
      if rezdy_status in ("CANCELLED", "DELETED"):
        result = await db.execute(
            select(Booking).where(Booking.order_number == order_number)
        )
        booking = result.scalar_one_or_none()
        if booking:
            booking.status = BookingStatus.cancelled.value
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
          if fields["first_name"] and fields["first_name"].lower() != "unknown":
              existing.first_name = fields["first_name"]
          if fields["last_name"] and fields["last_name"].lower() != "unknown":
              existing.last_name  = fields["last_name"]
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

          # Sync status from Rezdy
          if rezdy_status == "CONFIRMED":
             existing.status = BookingStatus.confirmed.value
          elif existing.status == BookingStatus.cancelled.value:
             existing.status = BookingStatus.pending.value

          # Record the time Rezdy pushed this update
          from zoneinfo import ZoneInfo as _ZI
          existing.updated_at = datetime.now(_ZI("America/Los_Angeles")).replace(tzinfo=None)

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
              source           = BookingSource.rezdy.value,
              status = BookingStatus.confirmed.value if rezdy_status == "CONFIRMED" else BookingStatus.pending.value,
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

    except Exception as e:
        print(f"[webhook] ERROR processing order={order_number} status={rezdy_status}: {e}")
        try:
            await db.rollback()
        except Exception:
            pass
        return {"status": "error", "reason": str(e)}

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
    #
    # IMPORTANT: booking_notes is keyed by order_number (NOT booking_id).
    # We resolve the order_number directly from send_log and do NOT join
    # bookings — Excel-sourced sends have an order_number that may not exist
    # in the bookings table, and bookings.id is not unique per order_number
    # (id drift), which previously caused inbound replies to be dropped.
    suffix = clean_from[-10:] if len(clean_from) >= 10 else clean_from

    try:
        result = await db.execute(
            _text("""
                SELECT sl.order_number
                FROM send_log sl
                WHERE RIGHT(REGEXP_REPLACE(sl.phone, '[^0-9]', '', 'g'), 10) = :suffix
                  AND sl.order_number IS NOT NULL
                  AND sl.order_number <> ''
                ORDER BY sl.sent_at DESC
                LIMIT 1
            """),
            {"suffix": suffix},
        )
        row = result.fetchone()

        if not row or not row.order_number:
            print(f"[webhook/twilio/inbound] no matching order for {from_number}")
            return _twiml_response("")

        order_number = row.order_number

        # ── Write to booking_notes (keyed by order_number) ──
        now_la = datetime.now(ZoneInfo("America/Los_Angeles"))
        await db.execute(
            _text("""
                INSERT INTO booking_notes
                  (order_number, author_username, body, direction, channel, created_at)
                VALUES
                  (:order_number, 'guest', :body, 'sms_in', 'sms', :created_at)
            """),
            {
                "order_number": order_number,
                "body":         body_text,
                "created_at":   now_la,
            },
        )
        # ── Clear action_taken_by — new inbound message needs staff attention ──
        # Resolve by order_number on the bookings table.
        await db.execute(
            _text("""
                UPDATE bookings
                SET action_taken_by = NULL, action_taken_at = NULL
                WHERE order_number = :order_number
            """),
            {"order_number": order_number}
        )
        # Tickets rows live in tickets_reminders and take precedence in the
        # tracking COALESCE, so they must be cleared too. Joined by chd_number.
        await db.execute(
            _text("""
                UPDATE tickets_reminders
                SET action_taken_by = NULL, action_taken_at = NULL
                WHERE chd_number = :order_number
            """),
            {"order_number": order_number}
        )
        await db.commit()
        print(f"[webhook/twilio/inbound] wrote sms_in note for order_number={order_number}")
    except Exception as e:
        print(f"[webhook/twilio/inbound] db error: {e}")
        try:
            await db.rollback()
        except Exception:
            pass

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
