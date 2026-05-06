"""
NPE — send_tickets router
Mounted at prefix="/api/tickets-reminder"

POST /send-single
POST /send-bulk
POST /check-duplicates
GET  /tour-types
GET  /log
POST /update-notes
POST /update-status
"""

import os
import tempfile
import time
from datetime import datetime

from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import get_current_user
from app.services.sendgrid import send_raw_email
from app.services.sms import send_sms
from app.services.tickets_reminder import (
    TOUR_TYPES, make_token, confirm_url, build_sms, build_email, build_staff_email,
)

router = APIRouter()

STAFF_EMAIL = "confirmations@nationalparkexpress.com"


# ── Helpers ───────────────────────────────────────────────────────────────────
async def _insert_record(db: AsyncSession, d: dict) -> int:
    result = await db.execute(
        text("""INSERT INTO tickets_reminders
               (chd_number,confirmation_no,first_name,last_name,customer_email,
                phone,service_date,tour_type,checkin_time,tour_time,tour_location,no_of_pax,
                token_created,email_sent_at)
               VALUES (:chd,:cfm,:fn,:ln,:em,:ph,:sd,:tt,:ci,:ti,:tl,:pax,NOW(),NOW())
               RETURNING id"""),
        {
            "chd": d.get("chd_number") or d.get("order_number", ""),
            "cfm": d.get("confirmation_no", ""),
            "fn":  d.get("first_name", ""),
            "ln":  d.get("last_name", ""),
            "em":  d.get("customer_email") or d.get("email", ""),
            "ph":  d.get("phone", ""),
            "sd":  d.get("service_date", ""),
            "tt":  d.get("tour_type", ""),
            "ci":  d.get("checkin_time", ""),
            "ti":  d.get("tour_time", ""),
            "tl":  d.get("tour_location", ""),
            "pax": int(d.get("no_of_pax") or d.get("quantities") or 1),
        },
    )
    rid = result.fetchone()[0]
    await db.commit()
    return rid


async def _do_send(d: dict, send_type: str, db: AsyncSession) -> dict:
    tour_cfg   = TOUR_TYPES.get(d.get("tour_type", ""), next(iter(TOUR_TYPES.values())))
    sms_label  = tour_cfg.get("sms_label") or tour_cfg.get("label", "")
    email_addr = d.get("customer_email") or d.get("email", "")
    svc_date   = d.get("service_date", "")

    rid      = await _insert_record(db, d)
    token    = make_token(rid, email_addr, svc_date)
    form_url = confirm_url(token, send_type)

    sms_ok, email_ok = False, False
    if send_type in ("sms", "combined"):
        r      = send_sms(d.get("phone", ""), build_sms(d, d.get("tour_type", ""), form_url))
        sms_ok = r.get("success", False)
    if send_type in ("email", "combined") and email_addr:
        subj     = f"Tickets Reminder — {sms_label} on " + (
            datetime.strptime(svc_date, "%Y-%m-%d").strftime("%B %-d, %Y") if svc_date else "")
        email_ok = await send_raw_email(email_addr, "Guest", subj, build_email(d, d.get("tour_type", ""), svc_date, form_url))

    sms_st = "sent" if sms_ok else ("failed" if send_type in ("sms", "combined") else "")
    em_st  = "sent" if email_ok else ("failed" if send_type in ("email", "combined") else "")
    await db.execute(
        text("UPDATE tickets_reminders SET sms_status=:s, email_status=:e WHERE id=:id"),
        {"s": sms_st, "e": em_st, "id": rid},
    )
    await db.commit()
    return {"record_id": rid, "sms_ok": sms_ok, "email_ok": email_ok,
            "name": f"{d.get('first_name','')} {d.get('last_name','')}".strip()}


# ── POST /send-single ─────────────────────────────────────────────────────────
@router.post("/send-single")
async def send_single(request: Request, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    d         = await request.json()
    send_type = d.get("send_type", "combined")
    return await _do_send(d, send_type, db)


# ── POST /send-bulk ───────────────────────────────────────────────────────────
@router.post("/send-bulk")
async def send_bulk(request: Request, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    body      = await request.json()
    send_type = body.get("send_type", "combined")
    guests    = body.get("guests", [])
    results   = []
    for g in guests:
        results.append(await _do_send(g, send_type, db))
        time.sleep(0.3)
    return {"sent": len(results), "results": results}


# ── POST /check-duplicates ────────────────────────────────────────────────────
@router.post("/check-duplicates")
async def check_duplicates(
    manifest: UploadFile = File(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    chd_numbers, total = [], 0
    if manifest and manifest.filename:
        content = await manifest.read()
        suffix  = os.path.splitext(manifest.filename)[1] or ".xlsx"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content); tmp_path = tmp.name
        try:
            from app.services.excel_parser import parse_excel
            parsed = parse_excel(tmp_path, "tickets_reminder")
        finally:
            os.unlink(tmp_path)
        if "error" in parsed:
            return {"error": parsed["error"], "duplicates": [], "total": 0}
        rows        = parsed.get("rows", [])
        total       = len(rows)
        chd_numbers = [r.get("order_number", "") for r in rows if r.get("order_number")]
    if not chd_numbers:
        return {"duplicates": [], "total": total}
    placeholders = ", ".join(f":c{i}" for i in range(len(chd_numbers)))
    result = await db.execute(
        text(f"SELECT DISTINCT chd_number FROM tickets_reminders WHERE chd_number IN ({placeholders})"),
        {f"c{i}": v for i, v in enumerate(chd_numbers)},
    )
    return {"duplicates": [r[0] for r in result.fetchall()], "total": total}


# ── GET /tour-types ───────────────────────────────────────────────────────────
@router.get("/tour-types")
async def tour_types(_=Depends(get_current_user)):
    return [{"key": k, "label": v["label"], "abbr": v["abbr"]} for k, v in TOUR_TYPES.items()]


# ── GET /log ──────────────────────────────────────────────────────────────────
@router.get("/log")
async def log(date: str = "", db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    if not date:
        date = datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")
    result = await db.execute(
        text("""SELECT id, chd_number, confirmation_no, first_name, last_name,
                       tour_type, service_date, checkin_time, tour_time, no_of_pax,
                       phone, confirmation, reschedule_notes, submitted_at,
                       submission_count, email_status, sms_status
                FROM tickets_reminders
                WHERE service_date = :date
                ORDER BY last_name ASC"""),
        {"date": date},
    )
    return [
        {
            "id":               r["id"],
            "chd_number":       r["chd_number"],
            "confirmation_no":  r["confirmation_no"],
            "name":             f"{r['first_name']} {r['last_name']}".strip(),
            "tour_type":        r["tour_type"],
            "service_date":     str(r["service_date"]),
            "checkin_time":     r["checkin_time"],
            "tour_time":        r["tour_time"],
            "no_of_pax":        r["no_of_pax"],
            "phone":            r["phone"],
            "confirmation":     r["confirmation"],
            "reschedule_notes": r["reschedule_notes"] or "",
            "submitted_at":     r["submitted_at"].isoformat() if r["submitted_at"] else None,
            "resubmitted":      int(r["submission_count"] or 0) > 1,
            "email_status":     r["email_status"],
            "sms_status":       r["sms_status"],
        }
        for r in result.mappings().fetchall()
    ]


# ── POST /update-notes ────────────────────────────────────────────────────────
@router.post("/update-notes")
async def update_notes(request: Request, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    body = await request.json()
    rid  = int(body.get("id", 0))
    if not rid:
        raise HTTPException(status_code=400, detail="id required")
    await db.execute(
        text("UPDATE tickets_reminders SET reschedule_notes=:n WHERE id=:id"),
        {"n": str(body.get("notes", "")), "id": rid},
    )
    await db.commit()
    return {"ok": True}


# ── POST /update-status ───────────────────────────────────────────────────────
@router.post("/update-status")
async def update_status(request: Request, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    body         = await request.json()
    confirmation = str(body.get("confirmation", ""))
    if confirmation not in ("yes", "pending", "reschedule_req"):
        raise HTTPException(status_code=400, detail="Invalid confirmation value")
    await db.execute(
        text("UPDATE tickets_reminders SET confirmation=:c WHERE chd_number=:chd AND service_date=:date"),
        {"c": confirmation, "chd": body.get("chd_number", ""), "date": body.get("service_date", "")},
    )
    await db.commit()
    return {"ok": True}
