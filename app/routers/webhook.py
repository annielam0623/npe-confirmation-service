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

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

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
    """
    Parse a Rezdy webhook payload into a flat dict matching Booking columns.
    Returns None if the payload is missing required fields.
    """
    order_number = payload.get("orderNumber", "").strip()
    if not order_number:
        return None

    # ── Customer ──
    customer   = payload.get("customer") or {}
    first_name = customer.get("firstName", "").strip()
    last_name  = customer.get("lastName", "").strip()
    email      = customer.get("email", "").strip()
    phone      = customer.get("mobile", "").strip() or customer.get("phone", "").strip()

    if not email:
        return None

    # ── Items — take first item for tour info ──
    items = payload.get("items") or []
    item  = items[0] if items else {}

    product_code = item.get("productCode", "").strip()
    product_name = item.get("productName", "").strip()

    # startTimeLocal is in venue's local timezone — use for display
    start_time_local = item.get("startTimeLocal") or item.get("startTime")
    tour_date        = _parse_start_date(start_time_local)
    pickup_time      = _parse_start_time(start_time_local)
    quantities       = _extract_quantities(items)

    # ── Fields — order level ──
    order_fields = payload.get("fields") or []

    # ── Fields — participant level (first participant of first item) ──
    participants  = item.get("participants") or []
    part_fields   = participants[0].get("fields", []) if participants else []

    # ── Extract key fields ──
    # TT# — financial reference, stored but not displayed
    tt_number = _get_field(order_fields, "TT #", "TT#", "TT Number")

    # Confirmation# — attraction confirmation number (e.g. Antelope Canyon X)
    # Try common label patterns; also check participant fields
    confirmation_no = (
        _get_field(order_fields, "Confirmation #", "Confirmation#",
                   "Antelope Canyon X Confirmation #",
                   "Lower Antelope Canyon Confirmation #",
                   "Confirmation Number")
        or _get_field(part_fields, "Confirmation #", "Confirmation#",
                      "Barcode", "Ticket Number")
    )

    # Pickup location — Rezdy can send a string OR a dict with locationName/address
    def _extract_location(val) -> Optional[str]:
        if not val:
            return None
        if isinstance(val, str):
            return val.strip() or None
        if isinstance(val, dict):
            return (val.get("locationName") or val.get("name", "")).strip() or None
        return None

    _raw_pickup = payload.get("pickupLocation") or item.get("pickupLocation")
    print(f"[webhook] raw pickupLocation={_raw_pickup}")
    pickup_location = (
        _extract_location(_raw_pickup)
        or _get_field(part_fields, "Pick-up Location", "Pickup Location",
                      "Hotel Name", "Hotel", "Pick Up Location")
        or _get_field(order_fields, "Pick-up Location", "Pickup Location")
    )
    print(f"[webhook] parsed pickup_location={pickup_location}")

    # Pickup time — from pickupLocation.pickupTime (earlier than startTime)
    pickup_location_obj = payload.get("pickupLocation") or item.get("pickupLocation") or {}
    pickup_time_raw = pickup_location_obj.get("pickupTime") if isinstance(pickup_location_obj, dict) else None
    pickup_time = _parse_start_time(pickup_time_raw) or pickup_time
    # Special requirements — order level comments + item level
    special_req = (payload.get("comments") or "").strip()
    item_req    = (item.get("comments") or "").strip()
    if item_req and item_req not in special_req:
        special_req = f"{special_req} {item_req}".strip()

    # Also check Order Special Requirements custom field
    field_req = _get_field(order_fields, "Order Special Requirements",
                           "Special Requirements", "Special Needs")
    if field_req and field_req not in special_req:
        special_req = f"{special_req} {field_req}".strip()

    # Lunch from special requirements
    lunch = _parse_lunch(special_req)

    # Agent
    agent_name = payload.get("resellerName", "").strip()

    return {
        "order_number":          order_number,
        "rezdy_order_id":        order_number,
        "product_code":          product_code or None,
        "product_name":          product_name or None,
        "tt_number":             tt_number,
        "confirmation_no":       confirmation_no,
        "first_name":            first_name or "Guest",
        "last_name":             last_name,
        "customer_email":        email,
        "phone":                 phone or None,
        "quantities":            quantities,
        "tour_date":             tour_date,
        "pickup_time":           pickup_time,
        "pickup_location":       pickup_location or None,
        "special_requirements":  special_req or None,
        "agent_name":            agent_name or None,
        "lunch_turkey":          lunch["lunch_turkey"],
        "lunch_veggie":          lunch["lunch_veggie"],
        "lunch_beef":            lunch["lunch_beef"],
        "source":                BookingSource.rezdy,
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
    # ── Parse body ──
    try:
        payload = await request.json()
    except Exception as e:
        print(f"[webhook] JSON parse error: {e}")
        return {"status": "error", "reason": "invalid json"}

    order_number = payload.get("orderNumber", "").strip()
    rezdy_status = payload.get("status", "").strip().upper()

    print(f"[webhook] order={order_number} status={rezdy_status}")
    print(f"[webhook] payload={json.dumps(payload, ensure_ascii=False)[:3000]}")

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

    await db.commit()
    return {"status": "ok", "order_number": order_number}
