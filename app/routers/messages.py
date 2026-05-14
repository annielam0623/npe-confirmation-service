"""
messages.py — Team message board API
Handles team messages, unread counts, and read status
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text as _text
from pydantic import BaseModel
from typing import Optional
import pytz

from app.database import get_db
from app.auth import require_staff

router = APIRouter()

LA = pytz.timezone("America/Los_Angeles")


# ── GET /api/messages — fetch messages for current user's teams ───────────────

@router.get("/api/messages")
async def get_messages(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_staff),
):
    """Return messages visible to current user (their teams + global),
    ordered by created_at DESC (newest first)."""

    rows = await db.execute(_text("""
        SELECT
            m.id,
            m.text,
            m.source,
            m.booking_id,
            m.created_at,
            t.name  AS team_name,
            t.color AS team_color,
            u.username  AS author_name,
            u.initials  AS author_initials,
            EXISTS (
                SELECT 1 FROM message_reads mr
                WHERE mr.message_id = m.id AND mr.user_id = :user_id
            ) AS is_read
        FROM messages m
        LEFT JOIN teams       t ON t.id = m.team_id
        LEFT JOIN admin_users u ON u.id = m.author_id
        WHERE
            m.team_id IS NULL
            OR m.team_id IN (
                SELECT team_id FROM user_teams WHERE user_id = :user_id
            )
        ORDER BY m.created_at DESC
        LIMIT 100
    """), {"user_id": current_user.id})

    messages = []
    for r in rows.fetchall():
        messages.append({
            "id":             r[0],
            "text":           r[1],
            "source":         r[2],
            "booking_id":     r[3],
            "created_at":     r[4].astimezone(LA).strftime("%-m/%-d, %-I:%M %p"),
            "team_name":      r[5],
            "team_color":     r[6],
            "author_name":    r[7],
            "author_initials": r[8] or (r[7][:2].upper() if r[7] else "?"),
            "is_read":        r[9],
        })
    return messages


# ── GET /api/messages/unread-count ────────────────────────────────────────────

@router.get("/api/messages/unread-count")
async def get_unread_count(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_staff),
):
    """Return count of unread messages for current user."""
    row = await db.execute(_text("""
        SELECT COUNT(*) FROM messages m
        WHERE (
            m.team_id IS NULL
            OR m.team_id IN (
                SELECT team_id FROM user_teams WHERE user_id = :user_id
            )
        )
        AND NOT EXISTS (
            SELECT 1 FROM message_reads mr
            WHERE mr.message_id = m.id AND mr.user_id = :user_id
        )
    """), {"user_id": current_user.id})
    count = row.scalar() or 0
    return {"unread": count}


# ── POST /api/messages — post a new manual message ────────────────────────────

class MessageIn(BaseModel):
    text: str
    team_id: Optional[int] = None   # None = global (all teams)

@router.post("/api/messages")
async def post_message(
    body: MessageIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_staff),
):
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")

    result = await db.execute(_text("""
        INSERT INTO messages (author_id, team_id, text, source)
        VALUES (:author_id, :team_id, :text, 'manual')
        RETURNING id, created_at
    """), {
        "author_id": current_user.id,
        "team_id":   body.team_id,
        "text":      text,
    })
    row = result.fetchone()
    await db.commit()

    return {
        "ok":         True,
        "id":         row[0],
        "created_at": row[1].astimezone(LA).strftime("%-m/%-d, %-I:%M %p"),
    }


# ── POST /api/messages/{id}/read — mark message as read ──────────────────────

@router.post("/api/messages/{message_id}/read")
async def mark_read(
    message_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_staff),
):
    await db.execute(_text("""
        INSERT INTO message_reads (user_id, message_id)
        VALUES (:user_id, :message_id)
        ON CONFLICT DO NOTHING
    """), {"user_id": current_user.id, "message_id": message_id})
    await db.commit()
    return {"ok": True}


# ── POST /api/messages/read-all — mark all visible messages as read ───────────

@router.post("/api/messages/read-all")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_staff),
):
    await db.execute(_text("""
        INSERT INTO message_reads (user_id, message_id)
        SELECT :user_id, m.id
        FROM messages m
        WHERE (
            m.team_id IS NULL
            OR m.team_id IN (
                SELECT team_id FROM user_teams WHERE user_id = :user_id
            )
        )
        AND NOT EXISTS (
            SELECT 1 FROM message_reads mr
            WHERE mr.message_id = m.id AND mr.user_id = :user_id
        )
        ON CONFLICT DO NOTHING
    """), {"user_id": current_user.id})
    await db.commit()
    return {"ok": True}


# ── DELETE /api/messages/{id} — delete own message (admin can delete any) ─────

@router.delete("/api/messages/{message_id}")
async def delete_message(
    message_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_staff),
):
    row = await db.execute(_text("""
        SELECT author_id FROM messages WHERE id = :id
    """), {"id": message_id})
    r = row.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Message not found")

    # Only author or admin can delete
    if r[0] != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not allowed")

    await db.execute(_text("DELETE FROM messages WHERE id = :id"), {"id": message_id})
    await db.commit()
    return {"ok": True}


# ── GET /api/teams — list all teams (for compose dropdown) ───────────────────

@router.get("/api/teams")
async def get_teams(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_staff),
):
    rows = await db.execute(_text("""
        SELECT id, name, color FROM teams ORDER BY id
    """))
    return [{"id": r[0], "name": r[1], "color": r[2]} for r in rows.fetchall()]
