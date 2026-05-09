from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import date
from typing import Optional
from app.database import get_db
from app.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/admin/send-log", response_class=HTMLResponse)
async def send_log_page(request: Request, current_user=Depends(get_current_user)):
    return templates.TemplateResponse("admin/send_log.html", {
        "request": request,
        "user": current_user
    })


@router.get("/api/send-log")
async def send_log_api(
    request: Request,
    date_filter: Optional[str] = Query(None, alias="date"),
    module: Optional[str] = Query(None),
    type_filter: Optional[str] = Query(None, alias="type"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    filters = []
    params = {}

    if date_filter:
        filters.append("DATE(sent_at AT TIME ZONE 'America/Los_Angeles') = :date_filter")
        params["date_filter"] = date_filter
    else:
        filters.append("DATE(sent_at AT TIME ZONE 'America/Los_Angeles') = CURRENT_DATE AT TIME ZONE 'America/Los_Angeles'")

    if module and module != "all":
        filters.append("module = :module")
        params["module"] = module

    if type_filter and type_filter != "all":
        if type_filter == "combined":
            filters.append("email_status IS NOT NULL AND sms_status IS NOT NULL")
        elif type_filter == "sms":
            filters.append("sms_status IS NOT NULL AND email_status IS NULL")
        elif type_filter == "email":
            filters.append("email_status IS NOT NULL AND sms_status IS NULL")

    where_clause = "WHERE " + " AND ".join(filters) if filters else ""

    query = text(f"""
        SELECT
            id,
            sent_at AT TIME ZONE 'America/Los_Angeles' AS sent_at,
            module,
            order_number,
            first_name,
            last_name,
            email,
            phone,
            tour_date,
            tour_type,
            email_status,
            sms_status,
            sms_sid,
            error_msg,
            email_message_id,
            delivered_at,
            sent_by
        FROM send_log
        {where_clause}
        ORDER BY sent_at DESC
    """)

    rows = db.execute(query, params).mappings().all()

    # Stats
    total = len(rows)
    sms_sent = sum(1 for r in rows if r["sms_status"] == "sent")
    email_sent = sum(1 for r in rows if r["email_status"] == "sent")
    sms_failed = sum(1 for r in rows if r["sms_status"] == "failed")
    email_failed = sum(1 for r in rows if r["email_status"] == "failed")

    records = []
    for r in rows:
        # determine send type
        has_sms = r["sms_status"] is not None
        has_email = r["email_status"] is not None
        if has_sms and has_email:
            send_type = "combined"
        elif has_sms:
            send_type = "sms"
        elif has_email:
            send_type = "email"
        else:
            send_type = "—"

        records.append({
            "id": r["id"],
            "sent_at": r["sent_at"].strftime("%-m/%-d/%Y %-I:%M %p") if r["sent_at"] else "—",
            "module": r["module"] or "—",
            "send_type": send_type,
            "order_number": r["order_number"] or "—",
            "name": f"{r['first_name'] or ''} {r['last_name'] or ''}".strip() or "—",
            "email": r["email"] or "",
            "phone": r["phone"] or "",
            "tour_date": str(r["tour_date"]) if r["tour_date"] else "—",
            "email_status": r["email_status"] or "",
            "sms_status": r["sms_status"] or "",
            "error_msg": r["error_msg"] or "",
            "sent_by": r["sent_by"] or "—",
        })

    return JSONResponse({
        "stats": {
            "total": total,
            "sms_sent": sms_sent,
            "email_sent": email_sent,
            "sms_failed": sms_failed,
            "email_failed": email_failed,
        },
        "records": records
    })