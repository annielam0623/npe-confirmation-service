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
from sqlalchemy import text

from app.database import get_db
from app.auth import require_staff
from app.models import Booking, BookingStatus, DismissedBooking

router = APIRouter()
async def _log_activity(
    db: AsyncSession,
    order_number: str,
    event_type: str,
    detail: str,
    actor: str,
    actor_type: str,
):
    try:
        from zoneinfo import ZoneInfo
        now_la = datetime.now(ZoneInfo("America/Los_Angeles")).replace(tzinfo=None)
        await db.execute(text("""
            INSERT INTO activity_log
                (order_number, event_type, detail, actor, actor_type, created_at)
            VALUES
                (:order_number, :event_type, :detail, :actor, :actor_type, :created_at)
        """), {
            "order_number": order_number,
            "event_type":   event_type,
            "detail":       detail,
            "actor":        actor,
            "actor_type":   actor_type,
            "created_at":   now_la,
        })
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"_log_activity failed: {e}")

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
    current_user=Depends(require_staff),
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

    from sqlalchemy import func as _func
    result = await db.execute(
        select(Booking)
        .where(and_(*filters) if filters else True)
        .order_by(_func.greatest(Booking.created_at, Booking.updated_at).desc())
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
    current_user=Depends(require_staff),
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
    current_user=Depends(require_staff),
):
    """Inline edit — save confirmation_no on blur/Enter."""
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    booking.confirmation_no = payload.confirmation_no.strip()
    await db.commit()
    return {"ok": True, "confirmation_no": booking.confirmation_no}


@router.post("/{booking_id}/dismiss")
async def dismiss_booking(
    booking_id: int,
    payload: DismissRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_staff),
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
    current_user=Depends(require_staff),
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
    await _log_activity(db,
    order_number = booking.order_number,
    event_type   = "booking_handled",
    detail       = "Marked as handled",
    actor        = current_user.username,
    actor_type   = "staff",
)
    await db.commit()

    return {
        "ok": True,
        "handled_by": booking.handled_by,
        "handled_at": booking.handled_at.isoformat(),
    }


@router.put("/{booking_id}/confirmation")
async def update_confirmation(
    booking_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_staff),
):
    """
    Update confirmation status + optional lunch counts.
    Used by Tracking page inline dropdown.
    Cancel → clears lunch counts.
    """
    from sqlalchemy import text
    from zoneinfo import ZoneInfo
    LA = ZoneInfo("America/Los_Angeles")
    now_la = datetime.now(LA).replace(tzinfo=None)

    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    allowed = {"yes", "pending", "modify_req", "cancel"}
    new_conf = (payload.get("confirmation") or "").lower()
    if new_conf not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid confirmation: {new_conf}")

    booking.confirmation = new_conf
    booking.updated_at   = now_la

    # Cancel → clear lunch
    if new_conf == "cancel":
        booking.lunch_turkey = 0
        booking.lunch_veggie = 0
        booking.lunch_beef   = 0

    # Update lunch if provided (only meaningful for YES)
    if new_conf == "yes" and "lunch_turkey" in payload:
        booking.lunch_turkey = int(payload.get("lunch_turkey") or 0)
        booking.lunch_veggie = int(payload.get("lunch_veggie") or 0)
        booking.lunch_beef   = int(payload.get("lunch_beef")   or 0)

    await _log_activity(db,
    order_number = booking.order_number,
    event_type   = "status_changed",
    detail       = f"Status changed to {new_conf}",
    actor        = current_user.username,
    actor_type   = "staff",
)
    await db.commit()
    return {
        "ok":           True,
        "confirmation": booking.confirmation,
        "lunch_turkey": booking.lunch_turkey,
        "lunch_veggie": booking.lunch_veggie,
        "lunch_beef":   booking.lunch_beef,
    }


@router.put("/{booking_id}/lunch")
async def update_lunch(
    booking_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_staff),
):
    """Update lunch counts for a YES booking."""
    from zoneinfo import ZoneInfo
    LA = ZoneInfo("America/Los_Angeles")
    now_la = datetime.now(LA).replace(tzinfo=None)

    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.confirmation != "yes":
        raise HTTPException(status_code=400, detail="Lunch can only be edited for YES bookings")

    turkey = int(payload.get("lunch_turkey") or 0)
    veggie = int(payload.get("lunch_veggie") or 0)
    beef   = int(payload.get("lunch_beef")   or 0)

    booking.lunch_turkey = turkey
    booking.lunch_veggie = veggie
    booking.lunch_beef   = beef
    booking.updated_at   = now_la
    await db.commit()
    return {"ok": True, "lunch_turkey": turkey, "lunch_veggie": veggie, "lunch_beef": beef}


@router.put("/{booking_id}/mtlv-ticket-status")
async def update_mtlv_ticket_status(
    booking_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_staff),
):
    """Update MTLV ticket send status. Values: pending_send | sent"""
    from zoneinfo import ZoneInfo
    LA = ZoneInfo("America/Los_Angeles")
    now_la = datetime.now(LA).replace(tzinfo=None)

    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if not getattr(booking, "mtlv_eligible", False):
        raise HTTPException(status_code=400, detail="Booking is not MTLV eligible")

    new_status = (payload.get("mtlv_ticket_status") or "").lower()
    if new_status not in ("pending_send", "sent"):
        raise HTTPException(status_code=400, detail="Invalid status. Use pending_send or sent.")

    booking.mtlv_ticket_status = new_status
    booking.updated_at = now_la

    # Record who sent and when
    display_name = getattr(current_user, "full_name", None) or getattr(current_user, "display_name", None) or current_user.username
    if new_status == "sent":
        booking.mtlv_ticket_sent_by = display_name
        booking.mtlv_ticket_sent_at = now_la
    else:
        # Reverted to pending — clear sent_by/sent_at
        booking.mtlv_ticket_sent_by = None
        booking.mtlv_ticket_sent_at = None

    await _log_activity(db,
        order_number = booking.order_number,
        event_type   = "mtlv_ticket_sent",
        detail       = f"MTLV ticket status set to {new_status} by {display_name}",
        actor        = current_user.username,
        actor_type   = "staff",
    )
    await db.commit()

    sent_at_str = now_la.strftime("%-m/%-d/%y %-I:%M %p") if new_status == "sent" else None
    return {
        "ok":                  True,
        "mtlv_ticket_status":  booking.mtlv_ticket_status,
        "sent_by":             booking.mtlv_ticket_sent_by,
        "sent_at":             sent_at_str,
    }


@router.delete("/{booking_id}/handle")
async def unhandle_booking(
    booking_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_staff),
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

# take action on Notes
@router.put("/{booking_id}/take-action")
async def take_action(
    booking_id: int,
    source: str = Query(default="booking"),  # "tickets" → tickets_reminders, else bookings
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_staff),
):
    """Toggle action_taken. source=tickets uses tickets_reminders table."""
    from zoneinfo import ZoneInfo
    LA = ZoneInfo("America/Los_Angeles")
    now_la = datetime.now(LA).replace(tzinfo=None)

    # ── tickets_reminders table ───────────────────────────────────────────────
    if source == "tickets":
        tr = await db.execute(
            text("SELECT id, chd_number, action_taken_by FROM tickets_reminders WHERE id = :id"),
            {"id": booking_id}
        )
        ticket = tr.fetchone()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")

        if ticket.action_taken_by:
            # Toggle OFF
            await db.execute(
                text("UPDATE tickets_reminders SET action_taken_by=NULL, action_taken_at=NULL WHERE id=:id"),
                {"id": booking_id}
            )
            action_taken_by = ""
            action_taken_at = None
        else:
            # Toggle ON
            await db.execute(
                text("UPDATE tickets_reminders SET action_taken_by=:actor, action_taken_at=:now WHERE id=:id"),
                {"actor": current_user.username, "now": now_la, "id": booking_id}
            )
            action_taken_by = current_user.username
            action_taken_at = now_la
            await _log_activity(db,
                order_number = ticket.chd_number,
                event_type   = "action_taken",
                detail       = "Took action on notes",
                actor        = current_user.username,
                actor_type   = "staff",
            )

        await db.commit()
        return {
            "ok":              True,
            "action_taken_by": action_taken_by,
            "action_taken_at": action_taken_at.isoformat() if action_taken_at else None,
        }

    # ── bookings table (default) ──────────────────────────────────────────────
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.action_taken_by:
        # Toggle OFF
        booking.action_taken_by = None
        booking.action_taken_at = None
    else:
        # Toggle ON
        booking.action_taken_by = current_user.username
        booking.action_taken_at = now_la
        await _log_activity(db,
            order_number = booking.order_number,
            event_type   = "action_taken",
            detail       = "Took action on notes",
            actor        = current_user.username,
            actor_type   = "staff",
        )

    booking.updated_at = now_la
    await db.commit()
    return {
        "ok":              True,
        "action_taken_by": booking.action_taken_by or "",
        "action_taken_at": booking.action_taken_at.isoformat() if booking.action_taken_at else None,
    }