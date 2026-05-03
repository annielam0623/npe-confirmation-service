"""
NPE Bookings API
GET  /api/bookings/          — list bookings with sorting
PATCH /api/bookings/{id}/confirmation-no  — inline edit
POST /api/bookings/{id}/dismiss           — dismiss from Action Required
POST /api/bookings/{id}/handle            — mark as handled
GET  /api/bookings/stats                  — counts for pills/badges
"""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, and_, or_, not_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import get_current_user
from app.models import Booking, BookingStatus, DismissedBooking

router = APIRouter()

# ─── Status groupings ─────────────────────────────────────────────────────────

# Rezdy statuses that require attention → Action Required section
ACTION_REQUIRED_STATUSES = {
    "NEW", "ON_HOLD", "PENDING_SUPPLIER", "PENDING_CUSTOMER", "CANCELLED"
}

# "Handled" flag is stored as a JSON note in notes_history or a separate field
# We use a simple approach: booking has handled_by / handled_at columns
# (added via migrate_v4.sql below)

# ─── Schemas ──────────────────────────────────────────────────────────────────

class BookingOut(BaseModel):
    id: int
    order_number: str
    first_name: str
    last_name: str
    phone: Optional[str]
    customer_email: str
    product_code: Optional[str]
    product_name: Optional[str]
    tour_date: Optional[date]
    pickup_time: Optional[str]
    pickup_location: Optional[str]
    quantities: int
    rezdy_status: Optional[str]
    confirmation_no: Optional[str]
    source: Optional[str]
    agent_name: Optional[str]
    email_sent_at: Optional[datetime]
    sms_sent_at: Optional[datetime]
    # handled
    handled_by: Optional[str]
    handled_at: Optional[datetime]
    # dismissed
    is_dismissed: bool = False
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class ConfirmationNoUpdate(BaseModel):
    confirmation_no: str


class DismissRequest(BaseModel):
    reason: Optional[str] = None


class HandleRequest(BaseModel):
    pass  # handled_by comes from current_user


class BookingStats(BaseModel):
    action_required: int
    new_orders: int
    total: int
    by_product: dict


# ─── Helpers ──────────────────────────────────────────────────────────────────

def is_action_required(booking: Booking) -> bool:
    """Determine if booking needs attention."""
    status = (booking.rezdy_status or "").upper()
    if status in ACTION_REQUIRED_STATUSES:
        return True
    return False


def booking_to_dict(b: Booking, dismissed_ids: set) -> dict:
    return {
        "id":              b.id,
        "order_number":    b.order_number,
        "first_name":      b.first_name,
        "last_name":       b.last_name,
        "guest_name":      f"{b.first_name} {b.last_name}".strip(),
        "phone":           b.phone,
        "customer_email":  b.customer_email,
        "product_code":    b.product_code,
        "product_name":    b.product_name,
        "tour_date":       b.tour_date.isoformat() if b.tour_date else None,
        "pickup_time":     b.pickup_time,
        "pickup_location": b.pickup_location,
        "quantities":      b.quantities or 1,
        "rezdy_status":    b.rezdy_status if hasattr(b, "rezdy_status") else None,
        "confirmation_no": b.confirmation_no,
        "source":          b.source.value if b.source else None,
        "agent_name":      b.agent_name,
        "email_sent_at":   b.email_sent_at.isoformat() if b.email_sent_at else None,
        "sms_sent_at":     b.sms_sent_at.isoformat()   if b.sms_sent_at   else None,
        "handled_by":      getattr(b, "handled_by", None),
        "handled_at":      getattr(b, "handled_at", None),
        "is_dismissed":    b.id in dismissed_ids,
        "created_at":      b.created_at.isoformat() if b.created_at else None,
        "updated_at":      b.updated_at.isoformat() if b.updated_at else None,
    }


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/")
async def list_bookings(
    tour_date:    Optional[str] = Query(None, description="YYYY-MM-DD"),
    product_code: Optional[str] = Query(None),
    show_dismissed: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Returns bookings in two sections:
    1. action_required — statuses needing attention, sorted by updated_at desc
    2. new_orders      — CONFIRMED, sorted by updated_at desc
    Dismissed bookings are excluded by default.
    """
    # Build base query
    filters = []
    if tour_date:
        try:
            td = date.fromisoformat(tour_date)
            filters.append(Booking.tour_date == td)
        except ValueError:
            pass
    if product_code and product_code != "all":
        filters.append(Booking.product_code == product_code)

    result = await db.execute(
        select(Booking)
        .where(and_(*filters) if filters else True)
        .order_by(Booking.updated_at.desc())
    )
    all_bookings = result.scalars().all()

    # Get dismissed IDs
    dismissed_result = await db.execute(select(DismissedBooking.booking_id))
    dismissed_ids = {r[0] for r in dismissed_result.all()}

    action_required = []
    new_orders = []

    for b in all_bookings:
        if b.id in dismissed_ids and not show_dismissed:
            continue

        rezdy_status = (getattr(b, "rezdy_status", None) or "").upper()
        handled_by   = getattr(b, "handled_by", None)

        # Already handled → goes to new_orders regardless of status
        if handled_by:
            new_orders.append(booking_to_dict(b, dismissed_ids))
        elif rezdy_status in ACTION_REQUIRED_STATUSES:
            action_required.append(booking_to_dict(b, dismissed_ids))
        else:
            new_orders.append(booking_to_dict(b, dismissed_ids))

    return {
        "action_required": action_required,
        "new_orders":      new_orders,
        "total":           len(action_required) + len(new_orders),
    }


@router.get("/stats")
async def booking_stats(
    tour_date: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Counts for dashboard badges and pill counts."""
    filters = []
    if tour_date:
        try:
            td = date.fromisoformat(tour_date)
            filters.append(Booking.tour_date == td)
        except ValueError:
            pass

    result = await db.execute(
        select(Booking).where(and_(*filters) if filters else True)
    )
    bookings = result.scalars().all()

    dismissed_result = await db.execute(select(DismissedBooking.booking_id))
    dismissed_ids = {r[0] for r in dismissed_result.all()}

    action_required = 0
    new_orders = 0
    by_product: dict[str, dict] = {}

    for b in bookings:
        if b.id in dismissed_ids:
            continue

        rezdy_status = (getattr(b, "rezdy_status", None) or "").upper()
        handled_by   = getattr(b, "handled_by", None)

        if not handled_by and rezdy_status in ACTION_REQUIRED_STATUSES:
            action_required += 1
        else:
            new_orders += 1

        code = b.product_code or "unknown"
        if code not in by_product:
            by_product[code] = {"pax": 0, "orders": 0}
        by_product[code]["pax"]    += b.quantities or 1
        by_product[code]["orders"] += 1

    return {
        "action_required": action_required,
        "new_orders":      new_orders,
        "total":           action_required + new_orders,
        "by_product":      by_product,
    }


@router.patch("/{booking_id}/confirmation-no")
async def update_confirmation_no(
    booking_id: int,
    payload: ConfirmationNoUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Inline edit — save confirmation_no on blur/Enter."""
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    booking.confirmation_no = payload.confirmation_no.strip()
    booking.updated_at = datetime.utcnow()
    await db.commit()
    return {"ok": True, "confirmation_no": booking.confirmation_no}


@router.post("/{booking_id}/dismiss")
async def dismiss_booking(
    booking_id: int,
    payload: DismissRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Remove booking from Action Required (soft dismiss)."""
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Check not already dismissed
    existing = await db.execute(
        select(DismissedBooking).where(DismissedBooking.booking_id == booking_id)
    )
    if existing.scalar_one_or_none():
        return {"ok": True, "already_dismissed": True}

    dismissed = DismissedBooking(
        booking_id=booking_id,
        dismissed_by=current_user.username,
        reason=payload.reason,
    )
    db.add(dismissed)
    await db.commit()
    return {"ok": True}


@router.post("/{booking_id}/handle")
async def handle_booking(
    booking_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Mark booking as handled — moves it from Action Required to normal list.
    Records who handled it and when.
    """
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    booking.handled_by = current_user.username
    booking.handled_at = datetime.utcnow()
    booking.updated_at = datetime.utcnow()
    await db.commit()

    return {
        "ok": True,
        "handled_by": booking.handled_by,
        "handled_at": booking.handled_at.isoformat(),
    }


@router.delete("/{booking_id}/handle")
async def unhandle_booking(
    booking_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Undo handle — puts booking back into Action Required."""
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    booking.handled_by = None
    booking.handled_at = None
    booking.updated_at = datetime.utcnow()
    await db.commit()
    return {"ok": True}
