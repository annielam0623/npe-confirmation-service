"""
app/routers/sales_report.py
Sales Report — monthly and weekly breakdown by agent
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.database import get_db
from app.auth import require_staff
import calendar

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/admin/system/sales-report", response_class=HTMLResponse)
async def sales_report_page(request: Request, _user=Depends(require_staff)):
    return templates.TemplateResponse("admin/sales_report.html", {
        "request": request,
        "current_user": _user,
        "active_page": "sales_report",
    })


@router.get("/api/sales-report/monthly")
async def get_monthly_data(
    year: int,
    product_type: str,  # bus_tour | self_drive
    metric: str,        # orders | pax
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_staff),
):
    """Agent x Month table for the given year and product type."""
    agg = "SUM(b.quantities)" if metric == "pax" else "COUNT(*)"

    rows = await db.execute(text("""
        SELECT
            COALESCE(b.agent_name, 'Direct') AS agent,
            EXTRACT(MONTH FROM b.tour_date)::int AS month,
            """ + agg + """ AS value
        FROM bookings b
        WHERE b.booking_type = :product_type
          AND EXTRACT(YEAR FROM b.tour_date) = :year
          AND b.status != 'cancelled'
        GROUP BY agent, month
        ORDER BY agent, month
    """), {"product_type": product_type, "year": year})

    data = rows.mappings().fetchall()

    # Build pivot then sort agents by total high to low
    all_agents = sorted(set(r["agent"] for r in data))
    months = list(range(1, 13))
    pivot = {a: {m: 0 for m in months} for a in all_agents}
    for r in data:
        pivot[r["agent"]][r["month"]] = int(r["value"] or 0)
    agents = sorted(all_agents, key=lambda a: sum(pivot[a].values()), reverse=True)

    return {
        "agents": agents,
        "months": months,
        "month_names": [calendar.month_abbr[m] for m in months],
        "data": pivot,
    }


@router.get("/api/sales-report/weekly")
async def get_weekly_data(
    year: int,
    month: int,
    product_type: str,
    metric: str,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_staff),
):
    """Agent x Week table for the given year/month and product type."""
    agg = "SUM(b.quantities)" if metric == "pax" else "COUNT(*)"

    rows = await db.execute(text("""
        SELECT
            COALESCE(b.agent_name, 'Direct') AS agent,
            CEIL(EXTRACT(DAY FROM b.tour_date) / 7.0)::int AS week,
            """ + agg + """ AS value
        FROM bookings b
        WHERE b.booking_type = :product_type
          AND EXTRACT(YEAR FROM b.tour_date) = :year
          AND EXTRACT(MONTH FROM b.tour_date) = :month
          AND b.status != 'cancelled'
        GROUP BY agent, week
        ORDER BY agent, week
    """), {"product_type": product_type, "year": year, "month": month})

    data = rows.mappings().fetchall()

    # Build pivot then sort agents by total high to low
    all_agents = sorted(set(r["agent"] for r in data))
    weeks = [1, 2, 3, 4, 5]
    pivot = {a: {w: 0 for w in weeks} for a in all_agents}
    for r in data:
        w = min(int(r["week"]), 5)
        pivot[r["agent"]][w] += int(r["value"] or 0)

    # Remove week 5 if all zeros
    if all_agents and all(pivot[a][5] == 0 for a in all_agents):
        weeks = [1, 2, 3, 4]
        for a in all_agents:
            del pivot[a][5]

    agents = sorted(all_agents, key=lambda a: sum(pivot[a].values()), reverse=True)

    return {
        "agents": agents,
        "weeks": weeks,
        "week_names": [f"W{w}" for w in weeks],
        "data": pivot,
        "month_name": calendar.month_name[month],
        "year": year,
    }
