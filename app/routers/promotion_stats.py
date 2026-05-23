"""
app/routers/promotion_stats.py
Promotion Stats — MTLV eligible tracking
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.database import get_db
from app.auth import require_staff

router = APIRouter()
templates = Jinja2Templates(directory="app/templates/admin")


@router.get("/admin/system/promotion-stats", response_class=HTMLResponse)
async def promotion_stats_page(request: Request, _user=Depends(require_staff)):
    return templates.TemplateResponse("promotion_stats.html", {
        "request": request,
        "current_user": _user,
        "active_page": "promotion_stats",
    })


@router.get("/api/promotion-stats/summary")
async def get_promotion_summary(
    date_from: str = None,
    date_to:   str = None,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_staff),
):
    where_date = ""
    params = {}
    if date_from and date_to:
        where_date = "AND b.tour_date BETWEEN :date_from AND :date_to"
        params = {"date_from": date_from, "date_to": date_to}

    rows = await db.execute(text(f"""
        SELECT
            COUNT(*) FILTER (WHERE b.mtlv_eligible = TRUE)                                          AS total_eligible,
            COUNT(*) FILTER (WHERE b.mtlv_eligible = TRUE AND b.mtlv_qty > 0)                       AS selected_qty,
            COUNT(*) FILTER (WHERE b.mtlv_eligible = TRUE AND b.confirmation = 'yes'
                              AND (b.mtlv_qty IS NULL OR b.mtlv_qty = 0))                            AS yes_no_ticket,
            COUNT(*) FILTER (WHERE b.mtlv_eligible = TRUE
                              AND b.mtlv_ticket_status = 'pending_send')                             AS pending_send,
            COUNT(*) FILTER (WHERE b.mtlv_eligible = TRUE
                              AND b.mtlv_ticket_status = 'sent')                                     AS sent,
            COUNT(*) FILTER (WHERE b.mtlv_eligible = TRUE
                              AND b.mtlv_ticket_status = 'cancel')                                   AS cancelled
        FROM bookings b
        WHERE b.mtlv_eligible = TRUE
        {where_date}
    """), params)
    r = rows.mappings().fetchone()
    return {k: int(v or 0) for k, v in r.items()}


@router.get("/api/promotion-stats/detail")
async def get_promotion_detail(
    status: str = "all",   # all | selected | yes_no_ticket | pending
    date_from: str = None,
    date_to:   str = None,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_staff),
):
    where_date = ""
    params: dict = {}
    if date_from and date_to:
        where_date = "AND b.tour_date BETWEEN :date_from AND :date_to"
        params = {"date_from": date_from, "date_to": date_to}

    filters = {
        "selected":      "AND b.mtlv_qty > 0",
        "yes_no_ticket": "AND b.confirmation = 'yes' AND (b.mtlv_qty IS NULL OR b.mtlv_qty = 0)",
        "pending":       "AND b.mtlv_ticket_status = 'pending_send'",
    }
    extra = filters.get(status, "")

    rows = await db.execute(text(f"""
        SELECT
            b.order_number,
            b.first_name,
            b.last_name,
            b.customer_email,
            b.phone,
            b.tour_date,
            b.tour_type,
            b.quantities,
            b.confirmation,
            COALESCE(b.mtlv_qty, 0)           AS mtlv_qty,
            COALESCE(b.mtlv_ticket_status,'—') AS mtlv_ticket_status
        FROM bookings b
        WHERE b.mtlv_eligible = TRUE
        {extra}
        {where_date}
        ORDER BY b.tour_date DESC, b.order_number
        LIMIT 500
    """), params)

    data = rows.mappings().fetchall()
    return [dict(r) for r in data]
