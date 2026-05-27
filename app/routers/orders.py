"""
app/routers/orders.py
Orders — live feed from bookings table (Rezdy + Excel)
GET  /admin/operations/orders  — HTML page
GET  /api/operations/orders    — JSON data
"""
from datetime import datetime, date as date_type, timedelta
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


@router.get("/admin/operations/orders", response_class=HTMLResponse)
async def orders_page(
    request: Request,
    current_user=Depends(get_current_user),
):
    return templates.TemplateResponse("admin/orders.html", {
        "request":      request,
        "current_user": current_user,
        "active_page":  "orders",
    })


@router.get("/api/operations/orders")
async def orders_api(
    q:         Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
    status:    Optional[str] = Query("confirmed"),   # confirmed | processing | all
    page:      int           = Query(1, ge=1),
    page_size: int           = Query(50, ge=1, le=200),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    filters = ["1=1", "b.source = 'rezdy'"]
    params: dict = {}

    # Status filter — cast enum to text first to avoid invalid enum value error
    if status == "confirmed":
        filters.append("UPPER(b.status::text) = 'CONFIRMED'")
    elif status == "processing":
        filters.append("UPPER(b.status::text) IN ('PROCESSING','ON_HOLD','PENDING','PENDING_SUPPLIER','PENDING_CUSTOMER')")

    if q:
        filters.append("""(
            b.order_number ILIKE :q OR
            b.first_name   ILIKE :q OR
            b.last_name    ILIKE :q OR
            b.customer_email ILIKE :q OR
            b.phone        ILIKE :q OR
            b.product_name ILIKE :q
        )""")
        params["q"] = f"%{q}%"

    if date_from:
        try:
            params["date_from"] = date_type.fromisoformat(date_from)
            filters.append("b.tour_date >= :date_from")
        except ValueError:
            pass
    if date_to:
        try:
            params["date_to"] = date_type.fromisoformat(date_to)
            filters.append("b.tour_date <= :date_to")
        except ValueError:
            pass

    where = " AND ".join(filters)
    offset = (page - 1) * page_size

    count_res = await db.execute(
        text(f"SELECT COUNT(*) FROM bookings b WHERE {where}"), params
    )
    total = count_res.scalar()

    rows_res = await db.execute(
        text(f"""
            SELECT
                b.id,
                b.order_number,
                b.first_name,
                b.last_name,
                b.customer_email,
                b.phone,
                b.product_name,
                b.tour_type,
                b.tour_date,
                b.pickup_time,
                b.pickup_location,
                b.quantities,
                b.agent_name,
                b.source,
                b.status,
                b.created_at,
                b.updated_at
            FROM bookings b
            WHERE {where}
            ORDER BY GREATEST(b.created_at, COALESCE(b.updated_at, b.created_at)) DESC
            LIMIT :limit OFFSET :offset
        """),
        {**params, "limit": page_size, "offset": offset}
    )
    rows = rows_res.mappings().all()

    def fmt_dt(dt):
        if not dt:
            return "—"
        if hasattr(dt, 'astimezone'):
            dt = dt.astimezone(LA)
        return dt.strftime("%-m/%-d/%Y %-I:%M %p")

    def fmt_date(d):
        if not d:
            return "—"
        if isinstance(d, str):
            return d
        return d.strftime("%m/%d/%Y")

    records = []
    for r in rows:
        name = " ".join(filter(None, [r["first_name"], r["last_name"]])) or "—"
        records.append({
            "id":              r["id"],
            "order_number":    r["order_number"],
            "name":            name,
            "email":           r["customer_email"] or "—",
            "phone":           r["phone"] or "—",
            "product_name":    r["product_name"] or "—",
            "product_type":    r["tour_type"] or "—",
            "tour_date":       fmt_date(r["tour_date"]),
            "pickup_time":     r["pickup_time"] or "—",
            "pickup_location": r["pickup_location"] or "—",
            "quantities":      r["quantities"] or "—",
            "agent_name":      r["agent_name"] or "—",
            "source":          r["source"] or "—",
            "status":          r["status"] or "—",
            "created_at":      fmt_dt(r["created_at"]),
            "updated_at":      fmt_dt(r["updated_at"]),
        })

    return JSONResponse({
        "total":   total,
        "page":    page,
        "pages":   (total + page_size - 1) // page_size,
        "records": records,
    })
