"""
app/routers/ops_summary.py
Operations Summary — send stats + guest response stats
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.database import get_db
from app.auth import require_staff

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/admin/system/ops-summary", response_class=HTMLResponse)
async def ops_summary_page(request: Request, _user=Depends(require_staff)):
    return templates.TemplateResponse("admin/ops_summary.html", {
        "request": request,
        "current_user": _user,
        "active_page": "ops_summary",
    })


@router.get("/api/ops-summary/send-stats")
async def get_send_stats(
    range: str = "month",   # today | week | month | custom
    date_from: str = None,
    date_to: str = None,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_staff),
):
    if range == "today":
        where = "DATE(sl.sent_at AT TIME ZONE 'America/Los_Angeles') = (CURRENT_TIMESTAMP AT TIME ZONE 'America/Los_Angeles')::date"
    elif range == "week":
        where = "sl.sent_at >= NOW() - INTERVAL '7 days'"
    elif range == "custom" and date_from and date_to:
        where = f"DATE(sl.sent_at AT TIME ZONE 'America/Los_Angeles') BETWEEN '{date_from}' AND '{date_to}'"
    else:  # month
        where = "sl.sent_at >= DATE_TRUNC('month', NOW())"

    # Derive channel from email_status / sms_status columns
    rows = await db.execute(text(f"""
        SELECT
            sl.module,
            CASE
                WHEN sl.email_status IS NOT NULL AND sl.sms_status IS NOT NULL THEN 'both'
                WHEN sl.email_status IS NOT NULL THEN 'email'
                WHEN sl.sms_status  IS NOT NULL THEN 'sms'
                ELSE 'unknown'
            END AS channel,
            COUNT(*) AS total,
            SUM(CASE
                WHEN sl.email_status IN ('delivered','sent','queued')
                  OR sl.sms_status   IN ('delivered','sent','queued')
                THEN 1 ELSE 0
            END) AS success,
            SUM(CASE
                WHEN sl.email_status = 'failed'
                  OR sl.sms_status   = 'failed'
                THEN 1 ELSE 0
            END) AS failed
        FROM send_log sl
        WHERE {where}
        GROUP BY sl.module, channel
        ORDER BY sl.module, channel
    """))
    data = rows.mappings().fetchall()

    modules = ["tour_confirmation", "morning_pickup", "tickets_reminder"]
    result = {}
    for mod in modules:
        result[mod] = {
            "email": {"total": 0, "success": 0, "failed": 0},
            "sms":   {"total": 0, "success": 0, "failed": 0},
            "both":  {"total": 0, "success": 0, "failed": 0},
        }
    for r in data:
        mod = r["module"]
        ch  = r["channel"]
        if mod in result and ch in result[mod]:
            result[mod][ch] = {
                "total":   int(r["total"] or 0),
                "success": int(r["success"] or 0),
                "failed":  int(r["failed"] or 0),
            }
    return result


@router.get("/api/ops-summary/response-stats")
async def get_response_stats(
    range: str = "month",
    date_from: str = None,
    date_to: str = None,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_staff),
):
    if range == "today":
        where = "DATE(sl.sent_at AT TIME ZONE 'America/Los_Angeles') = (CURRENT_TIMESTAMP AT TIME ZONE 'America/Los_Angeles')::date"
    elif range == "week":
        where = "sl.sent_at >= NOW() - INTERVAL '7 days'"
    elif range == "custom" and date_from and date_to:
        where = f"DATE(sl.sent_at AT TIME ZONE 'America/Los_Angeles') BETWEEN '{date_from}' AND '{date_to}'"
    else:
        where = "sl.sent_at >= DATE_TRUNC('month', NOW())"

    rows = await db.execute(text(f"""
        SELECT
            b.confirmation,
            COUNT(*) AS cnt,
            AVG(CASE
                WHEN b.submitted_at IS NOT NULL AND sl.sent_at IS NOT NULL
                THEN EXTRACT(EPOCH FROM (b.submitted_at - sl.sent_at)) / 3600.0
                ELSE NULL
            END) AS avg_hours
        FROM send_log sl
        JOIN bookings b ON b.order_number = sl.order_number
        WHERE {where}
          AND sl.module = 'tour_confirmation'
        GROUP BY b.confirmation
    """))
    data = rows.mappings().fetchall()

    total = sum(int(r["cnt"]) for r in data)
    result = {"total": total, "yes": 0, "modify": 0, "pending": 0,
              "avg_hours_yes": None, "avg_hours_modify": None}

    for r in data:
        conf = r["confirmation"] or "pending"
        cnt  = int(r["cnt"])
        avg  = round(float(r["avg_hours"]), 1) if r["avg_hours"] else None
        if conf == "yes":
            result["yes"] = cnt
            result["avg_hours_yes"] = avg
        elif conf == "modify_req":
            result["modify"] = cnt
            result["avg_hours_modify"] = avg
        else:
            result["pending"] += cnt

    result["pct_yes"]     = round(result["yes"]    / total * 100, 1) if total else 0
    result["pct_modify"]  = round(result["modify"] / total * 100, 1) if total else 0
    result["pct_pending"] = round(result["pending"]/ total * 100, 1) if total else 0
    return result


@router.get("/api/ops-summary/tickets-response-stats")
async def get_tickets_response_stats(
    range: str = "month",
    date_from: str = None,
    date_to: str = None,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_staff),
):
    if range == "today":
        where = "DATE(sl.sent_at AT TIME ZONE 'America/Los_Angeles') = (CURRENT_TIMESTAMP AT TIME ZONE 'America/Los_Angeles')::date"
    elif range == "week":
        where = "sl.sent_at >= NOW() - INTERVAL '7 days'"
    elif range == "custom" and date_from and date_to:
        where = f"DATE(sl.sent_at AT TIME ZONE 'America/Los_Angeles') BETWEEN '{date_from}' AND '{date_to}'"
    else:
        where = "sl.sent_at >= DATE_TRUNC('month', NOW())"

    rows = await db.execute(text(f"""
        SELECT tr.confirmation, COUNT(*) AS cnt
        FROM send_log sl
        JOIN tickets_reminders tr ON tr.order_number = sl.order_number
        WHERE {where} AND sl.module = 'tickets_reminder'
        GROUP BY tr.confirmation
    """))
    data = rows.mappings().fetchall()

    total = sum(int(r["cnt"]) for r in data if (r["confirmation"] or '') != 'cancel')
    result = {"total": total, "yes": 0, "pending": 0}
    for r in data:
        conf = r["confirmation"] or "pending"
        cnt  = int(r["cnt"])
        if conf == "cancel":
            continue
        if conf == "yes":
            result["yes"] = cnt
        else:
            result["pending"] += cnt

    result["pct_yes"]     = round(result["yes"]     / total * 100, 1) if total else 0
    result["pct_pending"] = round(result["pending"]  / total * 100, 1) if total else 0
    return result


@router.get("/api/ops-summary/morning-response-stats")
async def get_morning_response_stats(
    range: str = "month",
    date_from: str = None,
    date_to: str = None,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_staff),
):
    if range == "today":
        where_sl = "DATE(sl.sent_at AT TIME ZONE 'America/Los_Angeles') = (CURRENT_TIMESTAMP AT TIME ZONE 'America/Los_Angeles')::date"
    elif range == "week":
        where_sl = "sl.sent_at >= NOW() - INTERVAL '7 days'"
    elif range == "custom" and date_from and date_to:
        where_sl = f"DATE(sl.sent_at AT TIME ZONE 'America/Los_Angeles') BETWEEN '{date_from}' AND '{date_to}'"
    else:
        where_sl = "sl.sent_at >= DATE_TRUNC('month', NOW())"

    rows = await db.execute(text(f"""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN cl.checkin_time IS NOT NULL THEN 1 ELSE 0 END) AS checked_in
        FROM send_log sl
        LEFT JOIN checkin_log cl ON cl.order_number = sl.order_number
        WHERE {where_sl} AND sl.module = 'morning_pickup'
    """))
    data = rows.mappings().fetchone()

    total      = int(data["total"] or 0)
    checked_in = int(data["checked_in"] or 0)
    not_yet    = total - checked_in

    return {
        "total":          total,
        "checked_in":     checked_in,
        "not_yet":        not_yet,
        "pct_checked_in": round(checked_in / total * 100, 1) if total else 0,
        "pct_not_yet":    round(not_yet    / total * 100, 1) if total else 0,
    }
