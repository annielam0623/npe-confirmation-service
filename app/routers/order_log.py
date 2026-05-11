"""
Order Log API
GET  /admin/activities/order-log  — HTML page
GET  /api/activities/order-log    — JSON data

Filtering by tour_date: joins activity_log → bookings on order_number.
Modified time (created_at) is shown as the last column.
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
from app.auth import require_staff

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
LA = ZoneInfo("America/Los_Angeles")

EVENT_LABELS = {
    "booking_created":        "Booking Created",
    "booking_updated":        "Booking Updated",
    "booking_handled":        "Marked as Handled",
    "status_changed":         "Status Changed",
    "guest_confirmed":        "Guest Confirmed",
    "guest_modify_requested": "Modify Requested",
    "lunch_selected":         "Lunch Updated",
    "mtlv_qty_selected":      "MTLV Qty Selected",
    "mtlv_ticket_sent":       "MTLV Ticket Sent",
    "action_taken":           "Action Taken",
}

EVENT_COLORS = {
    "booking_created":        "#185FA5",
    "booking_updated":        "#5f5e5a",
    "booking_handled":        "#3B6D11",
    "status_changed":         "#534AB7",
    "guest_confirmed":        "#3B6D11",
    "guest_modify_requested": "#BA7517",
    "lunch_selected":         "#3B6D11",
    "mtlv_qty_selected":      "#7B1FA2",
    "mtlv_ticket_sent":       "#7B1FA2",
    "action_taken":           "#A32D2D",
}


@router.get("/admin/activities/order-log", response_class=HTMLResponse)
async def order_log_page(
    request: Request,
    current_user=Depends(require_staff),
):
    today = datetime.now(LA).strftime("%Y-%m-%d")
    return templates.TemplateResponse("admin/order_log.html", {
        "request":      request,
        "current_user": current_user,
        "active_page":  "order_log",
        "today":        today,
    })


@router.get("/api/activities/order-log")
async def order_log_api(
    date:         Optional[str] = Query(None),   # tour_date filter
    event_type:   Optional[str] = Query(None),
    actor_type:   Optional[str] = Query(None),
    order_number: Optional[str] = Query(None),
    page:         int           = Query(1, ge=1),
    page_size:    int           = Query(50, ge=1, le=200),
    current_user=Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    # Base: join bookings to get tour_date; exclude system events
    al_filters  = ["al.actor_type != 'system'"]
    bk_filters  = []
    params      = {}

    if date:
        try:
            parsed_date = date_type.fromisoformat(date)
            bk_filters.append("b.tour_date = :tour_date")
            params["tour_date"] = parsed_date
        except ValueError:
            pass

    if event_type:
        al_filters.append("al.event_type = :event_type")
        params["event_type"] = event_type

    if actor_type:
        al_filters.append("al.actor_type = :actor_type")
        params["actor_type"] = actor_type

    if order_number:
        al_filters.append("al.order_number ILIKE :order_number")
        params["order_number"] = f"%{order_number}%"

    al_where = " AND ".join(al_filters)
    bk_where = (" AND " + " AND ".join(bk_filters)) if bk_filters else ""

    join_clause = """
        FROM activity_log al
        LEFT JOIN bookings b ON b.order_number = al.order_number
    """
    where_clause = f"WHERE {al_where}{bk_where}"

    offset = (page - 1) * page_size

    # Total count
    count_res = await db.execute(
        text(f"SELECT COUNT(*) {join_clause} {where_clause}"), params
    )
    total = count_res.scalar()

    # Rows
    rows_res = await db.execute(
        text(f"""
            SELECT
                al.id,
                al.order_number,
                al.event_type,
                al.detail,
                al.actor,
                al.actor_type,
                al.created_at,
                b.tour_date
            {join_clause}
            {where_clause}
            ORDER BY al.created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        {**params, "limit": page_size, "offset": offset}
    )
    rows = rows_res.mappings().all()

    # Stats
    stats_res = await db.execute(
        text(f"""
            SELECT al.event_type, COUNT(*) as cnt
            {join_clause}
            {where_clause}
            GROUP BY al.event_type
        """),
        params
    )
    stats = {r[0]: r[1] for r in stats_res.all()}

    records = []
    for r in rows:
        created_la = r["created_at"].astimezone(LA) if r["created_at"] else None
        tour_date  = r["tour_date"].strftime("%-m/%-d/%Y") if r["tour_date"] else "—"
        records.append({
            "id":           r["id"],
            "order_number": r["order_number"],
            "tour_date":    tour_date,
            "event_type":   r["event_type"],
            "event_label":  EVENT_LABELS.get(r["event_type"], r["event_type"]),
            "event_color":  EVENT_COLORS.get(r["event_type"], "#888"),
            "detail":       r["detail"] or "",
            "actor":        r["actor"] or "—",
            "actor_type":   r["actor_type"] or "—",
            "modified_at":  created_la.strftime("%-m/%-d/%Y %-I:%M %p") if created_la else "—",
        })

    return JSONResponse({
        "total":   total,
        "page":    page,
        "stats":   stats,
        "records": records,
    })
