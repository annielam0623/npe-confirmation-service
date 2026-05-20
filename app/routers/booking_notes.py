# app/routers/booking_notes.py

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, text
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from typing import Optional, List
from zoneinfo import ZoneInfo
from datetime import datetime, date

from app.database import get_db
from app.auth import require_staff
from app.models import Booking, BookingNote, BroadcastLog, BroadcastRecipient
from app.services.sms import send_sms_async
from app.services.sendgrid import send_email

router = APIRouter(prefix="/booking-notes", tags=["booking_notes"])

LA = ZoneInfo("America/Los_Angeles")

BROADCAST_TEMPLATES = {
    "tour": [
        {
            "name": "tour_cancelled",
            "label": "Tour cancelled",
            "body": "Hi {first_name}, your National Park Express tour on {tour_date} has been cancelled. Please contact us at 702-948-4190 for assistance.",
        },
        {
            "name": "time_changed",
            "label": "Pickup time updated",
            "body": "Hi {first_name}, your pickup time for your National Park Express tour on {tour_date} has been updated. Please contact us at 702-948-4190 for details.",
        },
        {
            "name": "weather_delay",
            "label": "Weather delay",
            "body": "Hi {first_name}, due to weather conditions your National Park Express tour on {tour_date} may experience delays. We will keep you updated.",
        },
        {
            "name": "custom",
            "label": "Custom message",
            "body": "",
        },
    ],
    "morning": [
        {
            "name": "pickup_changed",
            "label": "Pickup time updated",
            "body": "Hi {first_name}, your morning pickup time for {tour_date} has been updated. Please contact us at 702-948-4190 for details.",
        },
        {
            "name": "tour_cancelled",
            "label": "Tour cancelled",
            "body": "Hi {first_name}, your National Park Express tour on {tour_date} has been cancelled. Please contact us at 702-948-4190 for assistance.",
        },
        {
            "name": "weather_delay",
            "label": "Weather delay",
            "body": "Hi {first_name}, due to weather conditions your tour on {tour_date} may experience delays. We will keep you updated.",
        },
        {
            "name": "custom",
            "label": "Custom message",
            "body": "",
        },
    ],
    "tickets": [
        {
            "name": "tour_cancelled",
            "label": "Tour cancelled",
            "body": "Hi {first_name}, your Antelope Canyon ticket for {tour_date} has been cancelled. Please contact us at 702-948-4190 for assistance.",
        },
        {
            "name": "time_changed",
            "label": "Session time updated",
            "body": "Hi {first_name}, your Antelope Canyon session time for {tour_date} has been updated. Please contact us at 702-948-4190 for details.",
        },
        {
            "name": "weather_delay",
            "label": "Weather / access delay",
            "body": "Hi {first_name}, due to conditions at the canyon your session on {tour_date} may be affected. We will keep you updated.",
        },
        {
            "name": "custom",
            "label": "Custom message",
            "body": "",
        },
    ],
}


# ── Schemas ───────────────────────────────────────────────────────────────────

class NoteCreate(BaseModel):
    body: str
    direction: str = "staff_note"   # 'staff_note' | 'sms_out' | 'email_out' | 'guest_reply'
    send_sms: bool = False
    send_email: bool = False

class BroadcastSend(BaseModel):
    module: str                     # 'tour' | 'morning' | 'tickets'
    group_filter: str               # 'general' | 'mtlv'
    status_filter: str              # 'all' | 'pending' | 'yes' | 'modify'
    tour_date: date
    template_name: Optional[str] = None
    message_body: str
    recipients: List[dict]          # [{order_number, customer_name, first_name, phone, email}]
    send_sms: bool = True
    send_email: bool = True


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_la():
    return datetime.now(LA)

def _fmt_direction(direction: str, sms_status: str = None, email_status: str = None) -> str:
    labels = {
        "staff_note":  "Note",
        "sms_out":     "SMS sent",
        "email_out":   "Email sent",
        "guest_reply": "Guest reply",
    }
    return labels.get(direction, direction)

def _serialize_note(n: BookingNote) -> dict:
    return {
        "id":              n.id,
        "booking_id":      n.booking_id,
        "author_username": n.author_username,
        "direction":       n.direction,
        "body":            n.body,
        "sms_status":      n.sms_status,
        "email_status":    n.email_status,
        "created_at":      n.created_at.astimezone(LA).strftime("%Y-%m-%d %H:%M") if n.created_at else None,
    }


# ── GET templates ─────────────────────────────────────────────────────────────

@router.get("/templates/{module}")
async def get_templates(module: str, user=Depends(require_staff)):
    if module not in BROADCAST_TEMPLATES:
        raise HTTPException(status_code=400, detail="Invalid module")
    return {"templates": BROADCAST_TEMPLATES[module]}


# ── GET notes for a booking ───────────────────────────────────────────────────

@router.get("/{booking_id}")
async def get_notes(
    booking_id: int,
    source: str = Query(default="tour"),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_staff),
):
    result = await db.execute(
        select(BookingNote)
        .where(BookingNote.booking_id == booking_id)
        .order_by(BookingNote.created_at.asc())
    )
    notes = result.scalars().all()

    # Update handler on booking (only for tour/morning, not tickets)
    if source != "tickets":
        await db.execute(
            update(Booking)
            .where(Booking.id == booking_id)
            .values(
                notes_handler=user.username,
                notes_handled_at=_now_la(),
            )
        )
    await db.commit()

    return {"notes": [_serialize_note(n) for n in notes]}


# ── POST new note ─────────────────────────────────────────────────────────────

@router.post("/{booking_id}")
async def add_note(
    booking_id: int,
    payload: NoteCreate,
    source: str = Query(default="tour"),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_staff),
):
    # Fetch booking for SMS/email
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    sms_status = None
    email_status = None

    # Send SMS if requested
    if payload.send_sms and booking.phone:
        try:
            await send_sms_async(booking.phone, payload.body)
            sms_status = "sent"
        except Exception:
            sms_status = "failed"

    # Send Email if requested
    if payload.send_email and booking.customer_email:
        try:
            subject = f"Update on your National Park Express tour — Order {booking.order_number}"
            html = f"""
            <p>Hi {booking.first_name},</p>
            <p>{payload.body}</p>
            <p>If you have any questions, please contact us at 702-948-4190.</p>
            <p>National Park Express</p>
            """
            await send_email(booking.customer_email, subject, html)
            email_status = "sent"
        except Exception:
            email_status = "failed"

    # Determine direction
    direction = payload.direction
    if payload.send_sms and payload.send_email:
        direction = "sms_out"   # primary direction; email_out logged separately below
    elif payload.send_sms:
        direction = "sms_out"
    elif payload.send_email:
        direction = "email_out"

    # Write note
    note = BookingNote(
        booking_id=booking_id,
        author_username=user.username,
        direction=direction,
        body=payload.body,
        sms_status=sms_status,
        email_status=email_status,
        created_at=_now_la(),
    )
    db.add(note)

    # Update handler (only for tour/morning, not tickets)
    if source != "tickets":
        await db.execute(
            update(Booking)
            .where(Booking.id == booking_id)
            .values(
                notes_handler=user.username,
                notes_handled_at=_now_la(),
            )
        )

    # ── Clear action_taken_by for inbound guest messages ─────────────────
    inbound_directions = {"sms_in", "email_in", "guest_reply"}
    if direction in inbound_directions:
        if source == "tickets":
            await db.execute(
                text("UPDATE tickets_reminders SET action_taken_by=NULL, action_taken_at=NULL WHERE id=:id"),
                {"id": booking_id}
            )
        else:
            from sqlalchemy import update as sa_update
            await db.execute(
                sa_update(Booking)
                .where(Booking.id == booking_id)
                .values(action_taken_by=None, action_taken_at=None)
            )

    await db.commit()
    await db.refresh(note)

    return {"note": _serialize_note(note)}


# ── GET broadcast counts (for dropdown display) ───────────────────────────────

@router.get("/broadcast/counts")
async def broadcast_counts(
    module: str,
    tour_date: date,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_staff),
):
    """
    Returns counts per group_filter + status_filter for the dropdown.
    Data comes from bookings table (all three modules store data there via webhook/upload).
    For morning/tickets where status may differ, we use the confirmation field.
    """
    if module not in ("tour", "morning", "tickets"):
        raise HTTPException(status_code=400, detail="Invalid module")

    # Map module to product_type
    type_map = {
        "tour":    "bus_tour",
        "morning": "bus_tour",
        "tickets": "self_drive",
    }
    product_type = type_map[module]

    base_q = (
        select(
            Booking.confirmation,
            Booking.mtlv_eligible,
            func.count(Booking.id).label("cnt"),
        )
        .where(Booking.tour_date == tour_date)
        .where(Booking.product_type == product_type)
        .group_by(Booking.confirmation, Booking.mtlv_eligible)
    )

    result = await db.execute(base_q)
    rows = result.all()

    counts = {
        "general": {"all": 0, "pending": 0, "yes": 0, "modify": 0},
        "mtlv":    {"all": 0, "pending": 0, "yes": 0},
    }

    for row in rows:
        status = row.confirmation or "pending"
        is_mtlv = row.mtlv_eligible

        grp = "mtlv" if is_mtlv else "general"
        counts[grp]["all"] += row.cnt
        if status in counts[grp]:
            counts[grp][status] += row.cnt

    return {"counts": counts, "tour_date": str(tour_date), "module": module}


# ── POST broadcast send ───────────────────────────────────────────────────────

@router.post("/broadcast/send")
async def broadcast_send(
    payload: BroadcastSend,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_staff),
):
    if not payload.recipients:
        raise HTTPException(status_code=400, detail="No recipients")

    sms_sent = sms_failed = email_sent = email_failed = 0
    recipient_rows = []

    for r in payload.recipients:
        first_name  = r.get("first_name") or r.get("customer_name", "Guest").split()[0]
        tour_date_str = payload.tour_date.strftime("%B %d, %Y")

        # Personalise message
        msg = (
            payload.message_body
            .replace("{first_name}", first_name)
            .replace("{tour_date}", tour_date_str)
        )

        rec_sms_status = None
        rec_email_status = None

        # SMS
        if payload.send_sms and r.get("phone"):
            try:
                await send_sms_async(r["phone"], msg)
                rec_sms_status = "sent"
                sms_sent += 1
            except Exception:
                rec_sms_status = "failed"
                sms_failed += 1
        elif payload.send_sms:
            rec_sms_status = "skipped"

        # Email
        if payload.send_email and r.get("email"):
            try:
                subject = f"Important update — National Park Express {tour_date_str}"
                html = f"<p>Hi {first_name},</p><p>{msg}</p><p>National Park Express<br>702-948-4190</p>"
                await send_email(r["email"], subject, html)
                rec_email_status = "sent"
                email_sent += 1
            except Exception:
                rec_email_status = "failed"
                email_failed += 1
        elif payload.send_email:
            rec_email_status = "skipped"

        recipient_rows.append({
            "order_number":  r.get("order_number"),
            "customer_name": r.get("customer_name"),
            "phone":         r.get("phone"),
            "email":         r.get("email"),
            "sms_status":    rec_sms_status,
            "email_status":  rec_email_status,
        })

    # Write broadcast_log
    blog = BroadcastLog(
        sent_by=user.username,
        module=payload.module,
        group_filter=payload.group_filter,
        status_filter=payload.status_filter,
        tour_date=payload.tour_date,
        template_name=payload.template_name,
        message_body=payload.message_body,
        recipient_count=len(payload.recipients),
        sms_sent=sms_sent,
        sms_failed=sms_failed,
        email_sent=email_sent,
        email_failed=email_failed,
        created_at=_now_la(),
    )
    db.add(blog)
    await db.flush()

    for rec in recipient_rows:
        db.add(BroadcastRecipient(broadcast_id=blog.id, **rec, created_at=_now_la()))

    await db.commit()

    return {
        "broadcast_id":   blog.id,
        "recipient_count": len(payload.recipients),
        "sms_sent":       sms_sent,
        "sms_failed":     sms_failed,
        "email_sent":     email_sent,
        "email_failed":   email_failed,
    }
