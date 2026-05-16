# app/routers/broadcasting_log.py

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from datetime import date
from typing import Optional
from zoneinfo import ZoneInfo

from app.database import get_db
from app.auth import require_staff
from app.models import BroadcastLog, BroadcastRecipient

router = APIRouter(tags=["broadcasting_log"])
templates = Jinja2Templates(directory="app/templates")
LA = ZoneInfo("America/Los_Angeles")


# ── Page ─────────────────────────────────────────────────────────────────────

@router.get("/admin/activities/broadcasting-log", response_class=HTMLResponse)
async def broadcasting_log_page(
    request: Request,
    user=Depends(require_staff),
):
    return templates.TemplateResponse(
        "admin/broadcasting_log.html",
        {"request": request, "current_user": user, "active_page": "broadcasting_log"},
    )


# ── API: list broadcast_log ───────────────────────────────────────────────────

@router.get("/api/broadcasting-log")
async def get_broadcasting_log(
    date: Optional[str] = None,
    module: Optional[str] = None,
    group: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_staff),
):
    q = select(BroadcastLog).order_by(desc(BroadcastLog.created_at))

    if date:
        try:
            tour_date = date
            q = q.where(BroadcastLog.tour_date == tour_date)
        except Exception:
            pass
    if module:
        q = q.where(BroadcastLog.module == module)
    if group:
        q = q.where(BroadcastLog.group_filter == group)

    result = await db.execute(q)
    rows = result.scalars().all()

    def _fmt(r):
        return {
            "id":              r.id,
            "sent_by":         r.sent_by,
            "module":          r.module,
            "group_filter":    r.group_filter,
            "status_filter":   r.status_filter,
            "tour_date":       str(r.tour_date) if r.tour_date else None,
            "template_name":   r.template_name,
            "message_body":    r.message_body,
            "recipient_count": r.recipient_count,
            "sms_sent":        r.sms_sent,
            "sms_failed":      r.sms_failed,
            "email_sent":      r.email_sent,
            "email_failed":    r.email_failed,
            "created_at":      r.created_at.astimezone(LA).strftime("%Y-%m-%d %H:%M") if r.created_at else None,
        }

    return {"rows": [_fmt(r) for r in rows]}


# ── API: recipients for one broadcast ────────────────────────────────────────

@router.get("/api/broadcasting-log/{broadcast_id}/recipients")
async def get_broadcast_recipients(
    broadcast_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_staff),
):
    result = await db.execute(
        select(BroadcastRecipient)
        .where(BroadcastRecipient.broadcast_id == broadcast_id)
        .order_by(BroadcastRecipient.id)
    )
    recs = result.scalars().all()

    return {
        "recipients": [
            {
                "order_number":  r.order_number,
                "customer_name": r.customer_name,
                "phone":         r.phone,
                "email":         r.email,
                "sms_status":    r.sms_status,
                "email_status":  r.email_status,
            }
            for r in recs
        ]
    }
