"""
Notifications API Router
Handles all data API endpoints for the notifications module.

Endpoints:
  POST /api/notifications/tour-confirmation/preview
  POST /api/notifications/morning-pickup/preview
  POST /api/notifications/tickets-reminder/preview

  GET  /api/notifications/tour-confirmation/tracking
  GET  /api/notifications/morning-pickup/tracking
  GET  /api/notifications/tickets-reminder/tracking

  GET  /api/notifications/send-log
  GET  /api/notifications/send-log/export

  POST /api/notifications/tour-confirmation/resend
  POST /api/notifications/morning-pickup/resend
  POST /api/notifications/tickets-reminder/resend

  GET  /api/notifications/tour-confirmation/lookup
  GET  /api/notifications/tour-confirmation/stats
  GET  /api/notifications/morning-pickup/stats
  GET  /api/notifications/tickets-reminder/stats

  POST /api/notifications/tour-confirmation/delete-by-date
  POST /api/notifications/morning-pickup/delete-by-date
  POST /api/notifications/tickets-reminder/delete-by-date

  GET  /api/notifications/tour-confirmation/export
  GET  /api/notifications/morning-pickup/export
  GET  /api/notifications/tickets-reminder/export
"""

from __future__ import annotations
import io
import csv
from datetime import date, datetime, timezone, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import require_staff
from app.services.excel_parser import parse_excel
from app.services import tour_confirmation as tc
from app.services import morning_pickup as mp
from app.services import tickets_reminder as tix
from app.services.sendgrid import send_raw_email as send_email
from app.services.sms import send_sms

router = APIRouter()
LA = ZoneInfo("America/Los_Angeles")


def _to_la_str(dt) -> str | None:
    """Convert a naive UTC datetime to LA time string MM/DD HH:MM."""
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    la_dt = dt.astimezone(LA)
    return la_dt.strftime("%-m/%-d %-I:%M %p")


def _to_date(d: str) -> date:
    """Convert YYYY-MM-DD string to Python date object for asyncpg."""
    return datetime.strptime(d, "%Y-%m-%d").date()


# ══════════════════════════════════════════════════════════════════════════════
# PREVIEW endpoints — parse Excel, check duplicates, return rows (no send)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/tour-confirmation/preview")
async def preview_tour_confirmation(
    file: UploadFile = File(...),
    tour_type: str   = Form(...),
    tour_date: str   = Form(...),
    db: AsyncSession = Depends(get_db),
    _user = Depends(require_staff),
):
    if tour_type not in tc.TOUR_TYPES:
        raise HTTPException(400, f"Unknown tour_type: {tour_type}")

    file_bytes = await file.read()
    parsed = parse_excel(file_bytes, "tour_confirmation")
    if "error" in parsed:
        raise HTTPException(400, parsed["error"])

    rows = parsed["rows"]

    # Check duplicates against bookings table
    for row in rows:
        result = await db.execute(text("""
            SELECT id FROM bookings
            WHERE order_number = :order_number
              AND tour_date    = :tour_date
              AND module       = 'tour_confirmation'
            LIMIT 1
        """), {"order_number": row["order_number"], "tour_date": _to_date(tour_date)})
        row["duplicate"] = result.fetchone() is not None
        row["name"] = f"{row['first_name']} {row['last_name']}".strip()

    total    = len(rows)
    dup_cnt  = sum(1 for r in rows if r["duplicate"])
    return {
        "total":      total,
        "duplicates": dup_cnt,
        "rows":       rows,
    }


@router.post("/morning-pickup/preview")
async def preview_morning_pickup(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _user = Depends(require_staff),
):
    file_bytes = await file.read()
    parsed = parse_excel(file_bytes, "morning_pickup")
    if "error" in parsed:
        raise HTTPException(400, parsed["error"])

    rows = parsed["rows"]
    today = date.today().strftime("%Y-%m-%d")

    for row in rows:
        result = await db.execute(text("""
            SELECT id FROM bookings
            WHERE order_number = :order_number
              AND tour_date    = :tour_date
              AND module       = 'morning_pickup'
            LIMIT 1
        """), {"order_number": row["order_number"], "tour_date": _to_date(today)})
        row["duplicate"] = result.fetchone() is not None
        row["name"] = f"{row['first_name']} {row['last_name']}".strip()

    return {"total": len(rows), "rows": rows}


@router.post("/tickets-reminder/preview")
async def preview_tickets_reminder(
    file: UploadFile    = File(...),
    tour_type: str      = Form(...),
    service_date: str   = Form(...),
    db: AsyncSession    = Depends(get_db),
    _user = Depends(require_staff),
):
    if tour_type not in tix.TOUR_TYPES:
        raise HTTPException(400, f"Unknown tour_type: {tour_type}")

    file_bytes = await file.read()
    parsed = parse_excel(file_bytes, "tickets_reminder")
    if "error" in parsed:
        raise HTTPException(400, parsed["error"])

    rows = parsed["rows"]

    for row in rows:
        result = await db.execute(text("""
            SELECT id FROM bookings
            WHERE order_number = :order_number
              AND tour_date    = :tour_date
              AND module       = 'tickets_reminder'
            LIMIT 1
        """), {"order_number": row["order_number"], "tour_date": _to_date(service_date)})
        row["duplicate"] = result.fetchone() is not None
        row["name"] = f"{row['first_name']} {row['last_name']}".strip()

    dup_cnt = sum(1 for r in rows if r["duplicate"])
    return {"total": len(rows), "duplicates": dup_cnt, "rows": rows}


# ══════════════════════════════════════════════════════════════════════════════
# TRACKING endpoints — return booking records for Tracking pages
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/tour-confirmation/tracking")
async def tracking_tour_confirmation(
    date: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _user = Depends(require_staff),
):
    result = await db.execute(text("""
        SELECT
            b.id, b.order_number, b.first_name, b.last_name,
            b.customer_email AS email, b.phone,
            b.quantities, b.pickup_time, b.pickup_location,
            b.tour_date, b.tour_type,
            b.email_status, b.sms_status, b.confirmation,
            b.lunch_turkey, b.lunch_veggie, b.lunch_beef,
            b.submitted_at, b.notes, b.notes_history,
            b.submission_count,
            b.mtlv_eligible, b.mtlv_qty, b.mtlv_ticket_status,
            b.action_taken_by
        FROM bookings b
        WHERE b.tour_date = :tour_date
          AND b.module    = 'tour_confirmation'
        ORDER BY b.submitted_at DESC NULLS LAST, b.last_name ASC
    """), {"tour_date": _to_date(date)})

    rows = result.mappings().all()
    return {
        "date": date,
        "rows": [
            {
                "id":                  r["id"],
                "order_number":        r["order_number"],
                "first_name":          r["first_name"] or "",
                "guest_name":          f"{r['first_name']} {r['last_name']}".strip(),
                "email":               r["email"] or "",
                "phone":               r["phone"] or "",
                "quantities":          r["quantities"],
                "pickup_time":         r["pickup_time"] or "",
                "pickup_location":     r["pickup_location"] or "",
                "tour_date":           str(r["tour_date"]) if r["tour_date"] else "",
                "tour_type":           r["tour_type"] or "",
                "email_status":        r["email_status"] or "",
                "sms_status":          r["sms_status"] or "",
                "confirmation_status": r["confirmation"] or "pending",
                "lunch_turkey":        r["lunch_turkey"] or 0,
                "lunch_veggie":        r["lunch_veggie"] or 0,
                "lunch_beef":          r["lunch_beef"] or 0,
                "lunch_selection":     ", ".join(filter(None, [
                    f"Turkey x{r['lunch_turkey']}" if r["lunch_turkey"] else "",
                    f"Veggie x{r['lunch_veggie']}" if r["lunch_veggie"] else "",
                    f"Beef x{r['lunch_beef']}"     if r["lunch_beef"]   else "",
                ])),
                "notes":               r["notes"] or "",
                "notes_history":       r["notes_history"] or "",
                "submission_count":    r["submission_count"] or 0,
                "submitted_at":        _to_la_str(r["submitted_at"]),
                "mtlv_eligible":       bool(r["mtlv_eligible"]) if r["mtlv_eligible"] is not None else False,
                "mtlv_qty":            r["mtlv_qty"],           # None = not replied yet
                "mtlv_ticket_status":  r["mtlv_ticket_status"], # None / "pending_send" / "sent"
                "action_taken_by": r["action_taken_by"] or "",
            }
            for r in rows
        ],
    }


@router.get("/morning-pickup/tracking")
async def tracking_morning_pickup(
    date: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _user = Depends(require_staff),
):
    result = await db.execute(text("""
        SELECT
            b.id, b.order_number, b.first_name, b.last_name,
            b.phone, b.quantities, b.pickup_time, b.pickup_location,
            b.tour_date, b.sms_status,
            b.driver, b.vehicle_no,
            c.checkin_time
        FROM bookings b
        LEFT JOIN checkin_log c ON c.order_number = b.order_number
            AND DATE(c.checkin_time) = :tour_date
        WHERE b.tour_date = :tour_date
          AND b.module    = 'morning_pickup'
        ORDER BY c.checkin_time DESC NULLS LAST, b.pickup_time ASC
    """), {"tour_date": _to_date(date)})

    rows = result.mappings().all()
    return {
        "date": date,
        "rows": [
            {
                "order_number":    r["order_number"],
                "name":            f"{r['first_name']} {r['last_name']}".strip(),
                "phone":           r["phone"] or "",
                "quantities":      r["quantities"] or 0,
                "pickup_time":     r["pickup_time"] or "",
                "pickup_location": r["pickup_location"] or "",
                "driver":          r["driver"] or "",
                "vehicle_no":      r["vehicle_no"] or "",
                "sms_status":      r["sms_status"] or "",
                "checkin_status":  "checked_in" if r["checkin_time"] else "pending",
                "checkin_time":    r["checkin_time"].isoformat() if r["checkin_time"] else None,
                "action_taken_by": r["action_taken_by"] or "",
            }
            for r in rows
        ],
    }


@router.get("/tickets-reminder/tracking")
async def tracking_tickets_reminder(
    date: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _user = Depends(require_staff),
):
    result = await db.execute(text("""
        SELECT
            b.id, b.order_number, b.confirmation_no,
            b.first_name, b.last_name, b.phone,
            b.customer_email AS email,
            b.quantities, b.tour_date, b.tour_type,
            b.pickup_time AS checkin_time,
            b.tour_time,
            b.email_status, b.sms_status,
            b.confirmation, b.submitted_at
            b.action_taken_by
        FROM bookings b
        WHERE b.tour_date = :tour_date
          AND b.module    = 'tickets_reminder'
        ORDER BY b.last_name ASC
    """), {"tour_date": _to_date(date)})

    rows = result.mappings().all()
    return {
        "date": date,
        "rows": [
            {
                "order_number":        r["order_number"],
                "confirmation_no":     r["confirmation_no"] or "",
                "guest_name":          f"{r['first_name']} {r['last_name']}".strip(),
                "phone":               r["phone"] or "",
                "email":               r["email"] or "",
                "quantities":          r["quantities"],
                "tour_date":           str(r["tour_date"]) if r["tour_date"] else "",
                "tour_type":           r["tour_type"] or "",
                "checkin_time":        r["checkin_time"] or "",
                "tour_time":           r["tour_time"] or "",
                "email_status":        r["email_status"] or "",
                "sms_status":          r["sms_status"] or "",
                "confirmation_status": r["confirmation"] or "pending",
                "submitted_at":        r["submitted_at"].isoformat() if r["submitted_at"] else None,
                "action_taken_by":     r["action_taken_by"] or "",
            }
            for r in rows
        ],
    }


# ══════════════════════════════════════════════════════════════════════════════
# SEND LOG endpoint
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/send-log")
async def get_send_log(
    date:      Optional[str] = Query(None),
    module:    Optional[str] = Query(None),
    channel:   Optional[str] = Query(None),   # EMAIL | SMS
    status:    Optional[str] = Query(None),
    page:      int = Query(1),
    page_size: int = Query(50),
    db: AsyncSession = Depends(get_db),
    _user = Depends(require_staff),
):
    conditions = ["1=1"]
    params: dict = {}

    if date:
        try:
            from datetime import date as date_type
            parsed_date = date_type.fromisoformat(date)
            conditions.append("DATE(sent_at) = :date")
            params["date"] = parsed_date
        except ValueError:
           pass
    if module:
        conditions.append("module = :module")
        params["module"] = module
    if channel:
        # EMAIL → has email_status; SMS → has sms_status
        if channel.upper() == "EMAIL":
            conditions.append("email_status != ''")
        elif channel.upper() == "SMS":
            conditions.append("sms_status != ''")
    if status:
        conditions.append(
            "(email_status ILIKE :status OR sms_status ILIKE :status)"
        )
        params["status"] = f"%{status}%"

    where = " AND ".join(conditions)
    offset = (page - 1) * page_size

    total_res = await db.execute(
        text(f"SELECT COUNT(*) FROM send_log WHERE {where}"), params
    )
    total = total_res.scalar() or 0

    rows_res = await db.execute(text(f"""
        SELECT id, sent_at, module, order_number, first_name, last_name,
               email, phone, tour_date, tour_type,
               email_status, sms_status, sms_sid, error_msg, sent_by
        FROM send_log
        WHERE {where}
        ORDER BY sent_at DESC
        LIMIT :limit OFFSET :offset
    """), {**params, "limit": page_size, "offset": offset})

    rows = rows_res.mappings().all()

    # Stats for current filter (by module)
    stats_res = await db.execute(text(f"""
        SELECT module, COUNT(*) AS cnt
        FROM send_log
        WHERE {where}
        GROUP BY module
    """), params)
    stats_raw = stats_res.all()
    stats = {
        "total":              total,
        "tour_confirmation":  0,
        "morning_pickup":     0,
        "tickets_reminder":   0,
    }
    for s in stats_raw:
        if s[0] in stats:
            stats[s[0]] = s[1]

    return {
        "total": total,
        "page":  page,
        "stats": stats,
        "rows": [
            {
                "sent_at":      r["sent_at"].isoformat() if r["sent_at"] else None,
                "module":       r["module"],
                "order_number": r["order_number"],
                "first_name":   r["first_name"],
                "last_name":    r["last_name"],
                "email":        r["email"],
                "phone":        r["phone"],
                "tour_date":    str(r["tour_date"]) if r["tour_date"] else "",
                "tour_type":    r["tour_type"],
                "email_status": r["email_status"],
                "sms_status":   r["sms_status"],
                "error_msg":    r["error_msg"],
                "sent_by":      r["sent_by"],
            }
            for r in rows
        ],
    }


@router.get("/send-log/export")
async def export_send_log(
    date:   Optional[str] = Query(None),
    module: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user = Depends(require_staff),
):
    conditions = ["1=1"]
    params: dict = {}
    if date:   conditions.append("DATE(sent_at) = :date");   params["date"] = date
    if module: conditions.append("module = :module");         params["module"] = module
    where = " AND ".join(conditions)

    res = await db.execute(text(f"""
        SELECT sent_at, module, order_number, first_name, last_name,
               email, phone, tour_date, tour_type,
               email_status, sms_status, error_msg, sent_by
        FROM send_log WHERE {where} ORDER BY sent_at DESC
    """), params)
    rows = res.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Sent At","Module","Order#","First Name","Last Name",
                     "Email","Phone","Tour Date","Tour Type",
                     "Email Status","SMS Status","Error","sent_by"])
    for r in rows:
        writer.writerow([
            r[0], r[1], r[2], r[3], r[4],
            r[5], r[6], r[7], r[8], r[9], r[10], r[11], r[12],
        ])
    output.seek(0)
    filename = f"send_log_{date or 'all'}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ══════════════════════════════════════════════════════════════════════════════
# LOOKUP & RESEND (Utilities)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/{module_name}/lookup")
async def lookup_booking(
    module_name: str,
    order: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _user = Depends(require_staff),
):
    module_map = {
        "tour-confirmation": "tour_confirmation",
        "morning-pickup":    "morning_pickup",
        "tickets-reminder":  "tickets_reminder",
    }
    module = module_map.get(module_name)
    if not module:
        raise HTTPException(404, "Module not found")

    res = await db.execute(text("""
        SELECT id, order_number, first_name, last_name,
               customer_email, phone, tour_date, tour_type,
               email_status, sms_status, pickup_time, quantities
        FROM bookings
        WHERE order_number = :order AND module = :module
        ORDER BY created_at DESC LIMIT 1
    """), {"order": order, "module": module})
    row = res.mappings().fetchone()
    if not row:
        return {"booking": None}
    return {"booking": dict(row)}


@router.post("/{module_name}/resend")
async def resend_booking(
    module_name: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    _user = Depends(require_staff),
):
    module_map = {
        "tour-confirmation": "tour_confirmation",
        "morning-pickup":    "morning_pickup",
        "tickets-reminder":  "tickets_reminder",
    }
    module = module_map.get(module_name)
    if not module:
        raise HTTPException(404, "Module not found")

    booking_id = payload.get("booking_id")
    channel    = payload.get("channel", "both")   # email | sms | both

    res = await db.execute(text("""
        SELECT * FROM bookings WHERE id = :id AND module = :module
    """), {"id": booking_id, "module": module})
    b = res.mappings().fetchone()
    if not b:
        raise HTTPException(404, "Booking not found")

    results = []

    if channel in ("email", "both") and b["customer_email"]:
        # Rebuild email and resend
        if module == "tour_confirmation":
            token = tc.make_token(b["id"], b["customer_email"], str(b["tour_date"]))
            url   = tc.confirm_url(token, src="email")
            html  = tc.build_email(dict(b), b["tour_type"], str(b["tour_date"]), url)
            subj  = f"Tour Confirmation – {b['tour_type']}"
        elif module == "morning_pickup":
            html = mp.build_email(dict(b))
            subj = mp.email_subject(dict(b))
        else:
            token = tix.make_token(b["id"], b["customer_email"], str(b["tour_date"]))
            url   = tix.confirm_url(token, src="email")
            html  = tix.build_email(dict(b), b["tour_type"], str(b["tour_date"]), url)
            subj  = f"Tickets Reminder – {b['tour_type']}"

        er = await send_email(b["customer_email"], f"{b['first_name']} {b['last_name']}", subj, html)
        results.append(f"Email: {'sent' if er['success'] else er.get('error','failed')}")

    if channel in ("sms", "both") and b["phone"]:
        if module == "tour_confirmation":
            token = tc.make_token(b["id"], b["customer_email"] or "", str(b["tour_date"]))
            url   = tc.confirm_url(token, src="sms")
            body  = tc.build_sms(b["first_name"], b["tour_type"], str(b["tour_date"]), url)
        elif module == "morning_pickup":
            body = mp.build_sms(dict(b))
        else:
            token = tix.make_token(b["id"], b["customer_email"] or "", str(b["tour_date"]))
            url   = tix.confirm_url(token, src="sms")
            body  = tix.build_sms(dict(b), b["tour_type"], url)

        sr = send_sms(b["phone"], body, module=module)
        results.append(f"SMS: {'sent' if sr['success'] else sr.get('error','failed')}")

    await db.commit()
    return {"success": True, "message": " | ".join(results)}


# # ══════════════════════════════════════════════════════════════════════════════
# STATS & DELETE (Utilities)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/{module_name}/stats")
async def module_stats(
    module_name: str,
    db: AsyncSession = Depends(get_db),
    _user = Depends(require_staff),
):
    module_map = {
        "tour-confirmation": "tour_confirmation",
        "morning-pickup":    "morning_pickup",
        "tickets-reminder":  "tickets_reminder",
    }
    module = module_map.get(module_name)
    if not module:
        raise HTTPException(404)

    today = date.today().strftime("%Y-%m-%d")
    month = date.today().strftime("%Y-%m")

    res = await db.execute(text("""
        SELECT
            COUNT(*)                                                        AS total,
            COUNT(*) FILTER (WHERE tour_date = :today)                     AS today,
            COUNT(*) FILTER (WHERE TO_CHAR(tour_date,'YYYY-MM') = :month)  AS this_month
        FROM send_log
        WHERE module = :module
    """), {"module": module, "today": today, "month": month})
    row = res.fetchone()
    return {"total": row[0], "today": row[1], "this_month": row[2]}


@router.get("/{module_name}/dates-with-records")
async def dates_with_records(
    module_name: str,
    db: AsyncSession = Depends(get_db),
    _user = Depends(require_staff),
):
    module_map = {
        "tour-confirmation": "tour_confirmation",
        "morning-pickup":    "morning_pickup",
        "tickets-reminder":  "tickets_reminder",
    }
    module = module_map.get(module_name)
    if not module:
        raise HTTPException(404)

    res = await db.execute(text("""
        SELECT tour_date, COUNT(*) as cnt
        FROM send_log
        WHERE module = :module
        GROUP BY tour_date
        ORDER BY tour_date DESC
    """), {"module": module})
    rows = res.fetchall()
    return [{"date": str(r[0]), "count": r[1]} for r in rows]


@router.post("/{module_name}/delete-by-date")
async def delete_by_date(
    module_name: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_staff),
):
    if current_user.role != "admin":
        raise HTTPException(403, "Admin only")

    module_map = {
        "tour-confirmation": "tour_confirmation",
        "morning-pickup":    "morning_pickup",
        "tickets-reminder":  "tickets_reminder",
    }
    module    = module_map.get(module_name)
    tour_date = payload.get("tour_date")
    if not module or not tour_date:
        raise HTTPException(400, "Missing module or tour_date")

    await db.execute(text("""
        DELETE FROM send_log
        WHERE module = :module AND tour_date = :tour_date
    """), {"module": module, "tour_date": _to_date(tour_date)})
    await db.commit()

    return {"success": True, "message": f"Deleted send records for {tour_date}"}


# ══════════════════════════════════════════════════════════════════════════════
# EXPORT (Utilities)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/{module_name}/export")
async def export_module(
    module_name: str,
    date:  Optional[str] = Query(None),
    from_: Optional[str] = Query(None, alias="from"),
    to:    Optional[str] = Query(None),
    type:  Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user = Depends(require_staff),
):
    module_map = {
        "tour-confirmation": "tour_confirmation",
        "morning-pickup":    "morning_pickup",
        "tickets-reminder":  "tickets_reminder",
    }
    module = module_map.get(module_name)
    if not module:
        raise HTTPException(404)

    conditions = ["module = :module"]
    params: dict = {"module": module}

    if date:
        conditions.append("tour_date = :date")
        params["date"] = date
    elif from_ and to:
        conditions.append("tour_date BETWEEN :from_ AND :to")
        params["from_"] = from_
        params["to"]    = to
    if type and type != "all":
        conditions.append("tour_type = :type")
        params["type"] = type

    where = " AND ".join(conditions)
    res = await db.execute(text(f"""
        SELECT order_number, first_name, last_name,
               email, phone, tour_date, tour_type,
               email_status, sms_status, sent_by, sent_at
        FROM send_log WHERE {where}
        ORDER BY tour_date ASC, last_name ASC
    """), params)
    rows = res.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Order#", "First Name", "Last Name", "Email", "Phone",
                     "Tour Date", "Tour Type", "Email Status", "SMS Status",
                     "Sent By", "Sent At"])
    for r in rows:
        writer.writerow(list(r))
    output.seek(0)

    label = date or (f"{from_}_to_{to}" if from_ else "all")
    filename = f"{module_name}_{label}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

# ══════════════════════════════════════════════════════════════════════════════
# EXPORT (Utilities)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/{module_name}/export")
async def export_module(
    module_name: str,
    date:  Optional[str] = Query(None),
    from_: Optional[str] = Query(None, alias="from"),
    to:    Optional[str] = Query(None),
    type:  Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user = Depends(require_staff),
):
    module_map = {
        "tour-confirmation": "tour_confirmation",
        "morning-pickup":    "morning_pickup",
        "tickets-reminder":  "tickets_reminder",
    }
    module = module_map.get(module_name)
    if not module:
        raise HTTPException(404)

    conditions = ["module = :module"]
    params: dict = {"module": module}

    if date:
        conditions.append("tour_date = :date")
        params["date"] = date
    elif from_ and to:
        conditions.append("tour_date BETWEEN :from_ AND :to")
        params["from_"] = from_
        params["to"]    = to
    if type and type != "all":
        conditions.append("tour_type = :type")
        params["type"] = type

    where = " AND ".join(conditions)
    res = await db.execute(text(f"""
        SELECT order_number, first_name, last_name,
               email, phone, tour_date, tour_type,
               email_status, sms_status, sent_by, sent_at
        FROM send_log WHERE {where}
        ORDER BY tour_date ASC, last_name ASC
    """), params)
    rows = res.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Order#", "First Name", "Last Name", "Email", "Phone",
                     "Tour Date", "Tour Type", "Email Status", "SMS Status",
                     "Sent By", "Sent At"])
    for r in rows:
        writer.writerow(list(r))
    output.seek(0)

    label = date or (f"{from_}_to_{to}" if from_ else "all")
    filename = f"{module_name}_{label}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )