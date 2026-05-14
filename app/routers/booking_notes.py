"""
booking_notes.py — Booking conversation API
Handles staff ↔ guest notes dialog + SMS notification + message board sync
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text as _text
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import pytz

from app.database import get_db
from app.auth import get_current_user, require_staff

router = APIRouter()

LA = pytz.timezone("America/Los_Angeles")

# ── Product type → team name mapping ──────────────────────────────────────────
PRODUCT_TEAM_MAP = {
    "bus_tour":   "Tour Confirmation",
    "self_drive": "Tickets Reminder",
    "morning":    "Morning Pickup",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_team_id(db: AsyncSession, team_name: str) -> Optional[int]:
    row = await db.execute(
        _text("SELECT id FROM teams WHERE name = :name"),
        {"name": team_name}
    )
    r = row.fetchone()
    return r[0] if r else None


async def _push_to_board(
    db: AsyncSession,
    booking_id: int,
    order_number: str,
    guest_name: str,
    note_text: str,
    team_name: str,
    source: str,
    author_id: Optional[int] = None,
):
    """Push a booking note as a message to the team board."""
    team_id = await _get_team_id(db, team_name)
    label = "Guest" if source == "guest_note" else "Staff"
    board_text = f"[{order_number}] {guest_name} — {label}: {note_text}"
    await db.execute(_text("""
        INSERT INTO messages (author_id, team_id, text, source, booking_id)
        VALUES (:author_id, :team_id, :text, :source, :booking_id)
    """), {
        "author_id":  author_id,
        "team_id":    team_id,
        "text":       board_text,
        "source":     source,
        "booking_id": booking_id,
    })


async def _send_sms_to_guest(phone: str, guest_name: str, confirm_token: str):
    """Send SMS to guest notifying of staff reply."""
    try:
        from app.services.sms import send_sms
        confirm_url = f"https://confirm.nationalparkexpress.com/confirm/{confirm_token}"
        message = (
            f"Hi {guest_name}, our team has replied to your message. "
            f"Please visit your confirmation page to view the reply:\n{confirm_url}"
        )
        await send_sms(phone, message)
    except Exception as e:
        print(f"[booking_notes] SMS failed: {e}")


# ── GET /api/booking-notes/{booking_id} ───────────────────────────────────────

@router.get("/api/booking-notes/{booking_id}")
async def get_notes(
    booking_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_staff),
):
    rows = await db.execute(_text("""
        SELECT id, author, text, created_at
        FROM booking_notes
        WHERE booking_id = :booking_id
        ORDER BY created_at ASC
    """), {"booking_id": booking_id})

    notes = []
    for r in rows.fetchall():
        notes.append({
            "id":         r[0],
            "author":     r[1],
            "text":       r[2],
            "created_at": r[3].astimezone(LA).strftime("%-m/%-d, %-I:%M %p"),
        })
    return notes


# ── GET /api/booking-notes/guest/{booking_id} — no auth, for guest polling ────

@router.get("/api/booking-notes/guest/{booking_id}")
async def get_notes_guest(
    booking_id: int,
    token: str,
    db: AsyncSession = Depends(get_db),
):
    # Validate token belongs to this booking
    row = await db.execute(_text("""
        SELECT id FROM bookings
        WHERE id = :booking_id AND confirm_token LIKE :token_prefix
    """), {"booking_id": booking_id, "token_prefix": f"{token}%"})
    if not row.fetchone():
        raise HTTPException(status_code=403, detail="Invalid token")

    rows = await db.execute(_text("""
        SELECT author, text, created_at
        FROM booking_notes
        WHERE booking_id = :booking_id
        ORDER BY created_at ASC
    """), {"booking_id": booking_id})

    notes = []
    for r in rows.fetchall():
        notes.append({
            "author":     r[0],
            "text":       r[1],
            "created_at": r[2].astimezone(LA).strftime("%-m/%-d, %-I:%M %p"),
            "is_staff":   r[0] != "guest",
        })
    return notes


# ── POST /api/booking-notes/{booking_id} — staff reply ────────────────────────

class StaffNoteIn(BaseModel):
    text: str

@router.post("/api/booking-notes/{booking_id}")
async def post_staff_note(
    booking_id: int,
    body: StaffNoteIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_staff),
):
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")

    # Get booking info
    row = await db.execute(_text("""
        SELECT b.id, b.order_number, b.customer_first_name, b.customer_last_name,
               b.phone, b.confirm_token, b.product_type
        FROM bookings b
        WHERE b.id = :booking_id
    """), {"booking_id": booking_id})
    booking = row.fetchone()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    _, order_number, first_name, last_name, phone, confirm_token, product_type = booking
    guest_name = first_name or (last_name or "Guest")
    initials = current_user.initials or current_user.username[:2].upper()

    # Insert note
    await db.execute(_text("""
        INSERT INTO booking_notes (booking_id, author, text)
        VALUES (:booking_id, :author, :text)
    """), {"booking_id": booking_id, "author": initials, "text": text})

    # Push to team board
    team_name = PRODUCT_TEAM_MAP.get(product_type, "Operations")
    await _push_to_board(
        db, booking_id, order_number, guest_name,
        text, team_name, "staff_note", author_id=current_user.id
    )

    await db.commit()

    # SMS guest
    if phone:
        await _send_sms_to_guest(phone, guest_name, confirm_token or "")

    return {"ok": True, "author": initials}


# ── POST /api/booking-notes/guest/{booking_id} — guest submits note ───────────

class GuestNoteIn(BaseModel):
    text: str
    token: str

@router.post("/api/booking-notes/guest/{booking_id}")
async def post_guest_note(
    booking_id: int,
    body: GuestNoteIn,
    db: AsyncSession = Depends(get_db),
):
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")

    # Validate token
    row = await db.execute(_text("""
        SELECT id, order_number, customer_first_name, customer_last_name, product_type
        FROM bookings
        WHERE id = :booking_id AND confirm_token LIKE :token_prefix
    """), {"booking_id": booking_id, "token_prefix": f"{body.token}%"})
    booking = row.fetchone()
    if not booking:
        raise HTTPException(status_code=403, detail="Invalid token")

    _, order_number, first_name, last_name, product_type = booking
    guest_name = first_name or (last_name or "Guest")

    # Insert note
    await db.execute(_text("""
        INSERT INTO booking_notes (booking_id, author, text)
        VALUES (:booking_id, 'guest', :text)
    """), {"booking_id": booking_id, "text": text})

    # Push to team board
    team_name = PRODUCT_TEAM_MAP.get(product_type, "Operations")
    await _push_to_board(
        db, booking_id, order_number, guest_name,
        text, team_name, "guest_note"
    )

    await db.commit()
    return {"ok": True}


# ── POST /api/booking-notes/{booking_id}/action ───────────────────────────────

@router.post("/api/booking-notes/{booking_id}/action")
async def toggle_action(
    booking_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_staff),
):
    row = await db.execute(_text("""
        SELECT notes_action_taken FROM bookings WHERE id = :id
    """), {"id": booking_id})
    r = row.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Booking not found")

    new_val = not r[0]
    await db.execute(_text("""
        UPDATE bookings SET notes_action_taken = :val WHERE id = :id
    """), {"val": new_val, "id": booking_id})
    await db.commit()
    return {"ok": True, "notes_action_taken": new_val}
