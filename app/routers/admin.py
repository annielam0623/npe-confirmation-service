"""
NPE Admin Router
Serves all HTML pages for the admin interface.
API endpoints are in separate routers (bookings.py, manifests.py, etc.)
"""

from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import require_staff, require_admin
from app.models import Booking, BookingType
from app.models import AdminUser

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# ─── Helpers ──────────────────────────────────────────────────────────────────

PRODUCT_CODE_MAP = {
    # Map product_code prefixes/groups → stat bucket
    # Update these when manifest_products table is populated
    "ant_upper":   ["P_ACU"],   # placeholder — real codes from DB
    "ant_lower":   ["P_ACL"],
    "ant_x":       ["P_ACX"],
    "out_shuttle": ["P_SHUT_OUT"],
    "in_shuttle":  ["P_SHUT_IN"],
}

async def get_dashboard_stats(db: AsyncSession, dates: list[datetime]) -> dict:
    """
    Returns dict keyed by date string 'YYYY-MM-DD' → {ant_total, ant_upper, ...}
    Real implementation queries bookings grouped by product_code + tour_date.
    For now returns structure with zeros (populate once manifest_products is set up).
    """
    stats = {}
    for d in dates:
        key = d.strftime("%Y-%m-%d")

        # Query pax for this date
        result = await db.execute(
            select(Booking.product_code, func.sum(Booking.quantities))
            .where(
                and_(
                    Booking.tour_date == d.date(),
                    Booking.booking_type == BookingType.bus_tour.value,
                )
            )
            .group_by(Booking.product_code)
        )
        rows = result.all()
        pax_by_code = {r[0]: (r[1] or 0) for r in rows}

        # You'll update this mapping once manifest_products is configured
        ant_upper   = 0
        ant_lower   = 0
        ant_x       = 0
        out_shuttle = 0
        in_shuttle  = 0

        # Sum all bus tour pax for ant_total (adjust when codes known)
        total = sum(pax_by_code.values())

        stats[key] = {
            "ant_total":   total,
            "ant_upper":   ant_upper,
            "ant_lower":   ant_lower,
            "ant_x":       ant_x,
            "out_shuttle": out_shuttle,
            "in_shuttle":  in_shuttle,
            "raw":         pax_by_code,
        }
    return stats


# ─── Root redirect ────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def admin_root():
    return RedirectResponse(url="/admin/dashboard", status_code=302)


# ─── Dashboard ────────────────────────────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_staff),
):
    today = date.today()
    # Show 14 days centred around today (offset shifts the window)
    start = today + timedelta(days=offset * 14)
    dates = [datetime.combine(start + timedelta(days=i), datetime.min.time())
             for i in range(14)]
    end_date = dates[-1]

    stats = await get_dashboard_stats(db, dates)

    return templates.TemplateResponse("dashboard.html", {
        "request":    request,
        "current_user": current_user,
        "active_page": "dashboard",
        "today":      today,
        "dates":      dates,
        "start_date": dates[0],
        "end_date":   dates[-1],
        "offset":     offset,
        "stats":      stats,
    })


# ─── 30 Days Forecast ─────────────────────────────────────────────────────────

@router.get("/forecast", response_class=HTMLResponse)
async def forecast(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_staff),
):
    today = date.today()
    dates = [datetime.combine(today + timedelta(days=i), datetime.min.time())
             for i in range(30)]

    stats = await get_dashboard_stats(db, dates)

    return templates.TemplateResponse("forecast.html", {
        "request":    request,
        "current_user": current_user,
        "active_page": "forecast",
        "today":      today,
        "dates":      dates,
        "stats":      stats,
    })


# ─── Manifests ────────────────────────────────────────────────────────────────

@router.get("/manifests", response_class=HTMLResponse)
async def manifests(
    request: Request,
    selected_date: str = Query(None),
    tab: str = Query("tour"),
    pill: str = Query("all"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    if selected_date:
        try:
            view_date = datetime.strptime(selected_date, "%Y-%m-%d").date()
        except ValueError:
            view_date = date.today()
    else:
        view_date = date.today()

    # Fetch bookings for this date
    result = await db.execute(
        select(Booking)
        .where(Booking.tour_date == view_date)
        .order_by(Booking.pickup_time.asc().nullslast(), Booking.created_at.asc())
    )
    bookings = result.scalars().all()

    # Product code pill counts
    pill_counts: dict[str, dict] = {}
    for b in bookings:
        code = b.product_code or "unknown"
        if code not in pill_counts:
            pill_counts[code] = {"pax": 0, "orders": 0}
        pill_counts[code]["pax"]    += b.quantities or 0
        pill_counts[code]["orders"] += 1

    return templates.TemplateResponse("manifests.html", {
        "request":     request,
        "current_user": current_user,
        "active_page": "manifests",
        "view_date":   view_date,
        "today":       date.today(),
        "bookings":    bookings,
        "pill_counts": pill_counts,
        "active_tab":  tab,
        "active_pill": pill,
    })


# ─── Dispatch ─────────────────────────────────────────────────────────────────

@router.get("/dispatch", response_class=HTMLResponse)
async def dispatch(
    request: Request,
    selected_date: str = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_staff),
):
    if selected_date:
        try:
            view_date = datetime.strptime(selected_date, "%Y-%m-%d").date()
        except ValueError:
            view_date = date.today()
    else:
        view_date = date.today()

    result = await db.execute(
        select(Booking)
        .where(
            and_(
                Booking.tour_date == view_date,
                Booking.booking_type == BookingType.bus_tour.value,
            )
        )
        .order_by(Booking.pickup_time.asc().nullslast())
    )
    bookings = result.scalars().all()

    return templates.TemplateResponse("dispatch.html", {
        "request":    request,
        "current_user": current_user,
        "active_page": "dispatch",
        "view_date":  view_date,
        "today":      date.today(),
        "bookings":   bookings,
    })


# ─── Logs ─────────────────────────────────────────────────────────────────────

@router.get("/logs/{log_type}", response_class=HTMLResponse)
async def logs(
    request: Request,
    log_type: str,
    selected_date: str = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_staff),
):
    log_type_map = {
        "tour-confirmation":  ("log_tour",    "Tour Confirmation Log"),
        "morning-reminder":   ("log_morning", "Morning Reminder Log"),
        "ticket-reminder":    ("log_ticket",  "Ticket Reminder Log"),
        "shuttle-confirmation": ("log_shuttle", "Shuttle Confirmation Log"),
    }
    if log_type not in log_type_map:
        return RedirectResponse(url="/admin/logs/tour-confirmation")

    page_key, page_label = log_type_map[log_type]

    if selected_date:
        try:
            view_date = datetime.strptime(selected_date, "%Y-%m-%d").date()
        except ValueError:
            view_date = date.today()
    else:
        view_date = date.today()

    # Fetch notification logs for this date + type
    from app.models import NotificationLog, NotificationType
    ntype_map = {
        "tour-confirmation": NotificationType.tour_confirmation.value,
        "morning-reminder":  NotificationType.morning_reminder.value,
        "ticket-reminder":   NotificationType.ticket_reminder.value,
        "shuttle-confirmation": NotificationType.tour_confirmation.value,  # extend later
    }

    result = await db.execute(
        select(NotificationLog)
        .where(NotificationLog.notification_type == ntype_map[log_type])
        .order_by(NotificationLog.sent_at.desc().nullslast())
        .limit(200)
    )
    logs_data = result.scalars().all()

    return templates.TemplateResponse("logs.html", {
        "request":    request,
        "current_user": current_user,
        "active_page": page_key,
        "log_type":   log_type,
        "page_label": page_label,
        "view_date":  view_date,
        "today":      date.today(),
        "logs":       logs_data,
    })


# ─── Settings (admin only) ────────────────────────────────────────────────────

@router.get("/settings", response_class=HTMLResponse)
async def settings(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):

    from app.models import Manifest, Setting
    manifests_result = await db.execute(select(Manifest).order_by(Manifest.sort_order))
    manifests_list = manifests_result.scalars().all()

    settings_result = await db.execute(select(Setting).order_by(Setting.key))
    settings_list = settings_result.scalars().all()

    return templates.TemplateResponse("settings.html", {
        "request":    request,
        "current_user": current_user,
        "active_page": "settings",
        "manifests":  manifests_list,
        "settings":   settings_list,
    })



# ─── Notifications — Page routes ──────────────────────────────────────────────

@router.get("/notifications/tour-confirmation/send", response_class=HTMLResponse)
async def notif_tour_send(
    request: Request,
    current_user=Depends(require_staff),
):
    return templates.TemplateResponse("admin/send_tour.html", {
        "request": request,
        "current_user": current_user,
        "active_page": "tour_send",
    })


@router.get("/notifications/tour-confirmation/tracking", response_class=HTMLResponse)
async def notif_tour_tracking(
    request: Request,
    current_user=Depends(require_staff),
):
    return templates.TemplateResponse("admin/tracking_tour.html", {
        "request": request,
        "current_user": current_user,
        "active_page": "tour_tracking",
    })


@router.get("/notifications/tour-confirmation/utilities", response_class=HTMLResponse)
async def notif_tour_utilities(
    request: Request,
    current_user=Depends(require_staff),
):
    return templates.TemplateResponse("admin/utilities_tour.html", {
        "request": request,
        "current_user": current_user,
        "active_page": "tour_utilities",
    })


@router.get("/notifications/morning-pickup/send", response_class=HTMLResponse)
async def notif_morning_send(
    request: Request,
    current_user=Depends(require_staff),
):
    return templates.TemplateResponse("admin/send_morning.html", {
        "request": request,
        "current_user": current_user,
        "active_page": "morning_send",
    })


@router.get("/notifications/morning-pickup/tracking", response_class=HTMLResponse)
async def notif_morning_tracking(
    request: Request,
    current_user=Depends(require_staff),
):
    return templates.TemplateResponse("admin/tracking_morning.html", {
        "request": request,
        "current_user": current_user,
        "active_page": "morning_tracking",
    })


@router.get("/notifications/morning-pickup/utilities", response_class=HTMLResponse)
async def notif_morning_utilities(
    request: Request,
    current_user=Depends(require_staff),
):
    return templates.TemplateResponse("admin/utilities_morning.html", {
        "request": request,
        "current_user": current_user,
        "active_page": "morning_utilities",
    })


@router.get("/notifications/tickets-reminder/send", response_class=HTMLResponse)
async def notif_tickets_send(
    request: Request,
    current_user=Depends(require_staff),
):
    return templates.TemplateResponse("admin/send_tickets.html", {
        "request": request,
        "current_user": current_user,
        "active_page": "tickets_send",
    })


@router.get("/notifications/tickets-reminder/tracking", response_class=HTMLResponse)
async def notif_tickets_tracking(
    request: Request,
    current_user=Depends(require_staff),
):
    return templates.TemplateResponse("admin/tracking_tickets.html", {
        "request": request,
        "current_user": current_user,
        "active_page": "tickets_tracking",
    })


@router.get("/notifications/tickets-reminder/utilities", response_class=HTMLResponse)
async def notif_tickets_utilities(
    request: Request,
    current_user=Depends(require_staff),
):
    return templates.TemplateResponse("admin/utilities_tickets.html", {
        "request": request,
        "current_user": current_user,
        "active_page": "tickets_utilities",
    })


@router.get("/notifications/send-log", response_class=HTMLResponse)
async def notif_send_log(
    request: Request,
    current_user=Depends(require_staff),
):
    today = date.today().strftime("%Y-%m-%d")
    return templates.TemplateResponse("admin/send_log.html", {
        "request": request,
        "current_user": current_user,
        "active_page": "send_log",
        "today": today,
    })

# ── Coming Soon ───────────────────────────────────────────────────────────────
@router.get("/coming-soon", response_class=HTMLResponse)
async def coming_soon(
    request: Request,
    module: str = "Coming Soon",
    current_user: AdminUser = Depends(require_staff),
):
    return templates.TemplateResponse("admin/coming_soon.html", {
        "request": request,
        "current_user": current_user,
        "module": module,
        "active_page": "",
    })

# ─── Orders ───────────────────────────────────────────────────────────────────

@router.get("/orders", response_class=HTMLResponse)
async def orders(
    request: Request,
    current_user=Depends(require_staff),
):
    return templates.TemplateResponse("admin/orders.html", {
        "request": request,
        "current_user": current_user,
        "active_page": "orders",
    })


# ─── Settings — Pickup Locations ─────────────────────────────────────────────

@router.get("/settings/pickup-locations", response_class=HTMLResponse)
async def settings_pickup_locations(
    request: Request,
    current_user=Depends(require_admin),
):
    return templates.TemplateResponse("admin/pickup_locations.html", {
        "request": request,
        "current_user": current_user,
        "active_page": "pickup_locations",
    })
