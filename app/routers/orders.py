"""
Orders Log API (System/Rezdy events)
GET  /admin/operations/orders   — HTML page
GET  /api/operations/orders     — JSON data
"""
from datetime import datetime, date as date_type
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
LA = ZoneInfo("America/Los_Angeles")

EVENT_LABELS = {
    "booking_created": "Booking Created",
    "booking_updated": "Booking Updated",
}

EVENT_COLORS = {
    "booking_created": "#185FA5",
    "booking_updated": "#5f5e5a",
}


@router.get("/admin/operations/orders", response_class=HTMLResponse)
async def orders_page(
    request: Request,
    current_user=Depends(get_current_user),
):
    today = datetime.now(LA).strftime("%Y-%m-%d")
    return templates.TemplateResponse("admin/orders.html", {
        "request":      request,
        "current_user": current_user,
        "active_page":  "orders",
        "today":        today,
    })


@router.get("/api/operations/orders")
async def orders_api(
    date:         Optional[str] = Query(None),
    event_type:   Optional[str] = Query(None),
    order_number: Optional[str] = Query(None),
    page:         int           = Query(1, ge=1),
    page_size:    int           = Query(50, ge=1, le=200),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    filters = ["actor_type = 'system'"]
    params  = {}

    if date:
        try:
            parsed_date = date_type.fromisoformat(date)
            filters.append("DATE(created_at AT TIME ZONE 'America/Los_Angeles') = :date")
            params["date"] = parsed_date
        except ValueError:
            pass
    if event_type:
        filters.append("event_type = :event_type")
        params["event_type"] = event_type
    if order_number:
        filters.append("order_number ILIKE :order_number")
        params["order_number"] = f"%{order_number}%"

    where = " AND ".join(filters)
    offset = (page - 1) * page_size

    # Total count
    count_res = await db.execute(
        text(f"SELECT COUNT(*) FROM activity_log WHERE {where}"), params
    )
    total = count_res.scalar()

    # Rows
    rows_res = await db.execute(
        text(f"""
            SELECT id, order_number, event_type, detail, actor, actor_type, created_at
            FROM activity_log
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        {**params, "limit": page_size, "offset": offset}
    )
    rows = rows_res.mappings().all()

    # Stats — all / created / updated
    stats_res = await db.execute(
        text(f"""
            SELECT event_type, COUNT(*) as cnt
            FROM activity_log
            WHERE {where}
            GROUP BY event_type
        """),
        params
    )
    stats_raw = stats_res.all()
    stats = {r[0]: r[1] for r in stats_raw}

    records = []
    for r in rows:
        created_la = r["created_at"].astimezone(LA) if r["created_at"] else None
        records.append({
            "id":           r["id"],
            "order_number": r["order_number"],
            "event_type":   r["event_type"],
            "event_label":  EVENT_LABELS.get(r["event_type"], r["event_type"]),
            "event_color":  EVENT_COLORS.get(r["event_type"], "#888"),
            "detail":       r["detail"] or "",
            "actor":        r["actor"] or "—",
            "created_at":   created_la.strftime("%-m/%-d/%Y %-I:%M %p") if created_la else "—",
        })

    return JSONResponse({
        "total":   total,
        "page":    page,
        "stats":   stats,
        "records": records,
    })