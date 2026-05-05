"""
Send router — POST endpoints for three modules + unified Twilio SMS callback.

Endpoints:
  POST /send/tour-confirmation   multipart: file + tour_type + tour_date
  POST /send/morning-pickup      multipart: file
  POST /send/tickets-reminder    multipart: file + tour_type + service_date
  POST /webhook/sms-status       Twilio StatusCallback (form-encoded)
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.auth import get_current_user
from app.services.excel_parser import parse_excel
from app.services.mailer import send_email
from app.services.sms import send_sms
from app.services import tour_confirmation as tc
from app.services import morning_pickup as mp
from app.services import tickets_reminder as tix

logger = logging.getLogger(__name__)
router = APIRouter()


def _to_date(d: str) -> date:
    """Convert YYYY-MM-DD string to Python date object for asyncpg."""
    if isinstance(d, date):
        return d
    return datetime.strptime(d, "%Y-%m-%d").date()


# ═══════════════════════════════════════════════════════════
# Helper — insert or update booking record, return row id
# ═══════════════════════════════════════════════════════════
async def _upsert_booking(db: AsyncSession, data: dict) -> int:
    """
    Insert booking if not exists (match on order_number + tour_date + module).
    Update if exists. Returns the row id.
    """
    existing = await db.execute(text("""
        SELECT id FROM bookings
        WHERE order_number = :order_number
          AND tour_date    = :tour_date
          AND module       = :module
        LIMIT 1
    """), {"order_number": data["order_number"],
           "tour_date":    data["tour_date"],
           "module":       data["module"]})
    row = existing.fetchone()

    if row:
        await db.execute(text("""
            UPDATE bookings SET
                first_name       = :first_name,
                last_name        = :last_name,
                customer_email   = :customer_email,
                phone            = :phone,
                quantities       = :quantities,
                pickup_time      = :pickup_time,
                pickup_location  = :pickup_location,
                tour_type        = :tour_type,
                token_created    = NOW(),
                email_status     = 'pending',
                sms_status       = 'pending',
                updated_at       = NOW()
            WHERE id = :id
        """), {**data, "id": row.id})
        return row.id

    booking_type = "self_drive" if data.get("module") == "tickets_reminder" else "bus_tour"
    result = await db.execute(text("""
        INSERT INTO bookings
            (order_number, first_name, last_name, customer_email, phone,
             quantities, pickup_time, pickup_location, tour_date, tour_type,
             module, booking_type, confirmation, token_created, email_status, sms_status,
             created_at, updated_at)
        VALUES
            (:order_number, :first_name, :last_name, :customer_email, :phone,
             :quantities, :pickup_time, :pickup_location, :tour_date, :tour_type,
             :module, :booking_type, 'pending', NOW(), 'pending', 'pending',
             NOW(), NOW())
        RETURNING id
    """), {**data, "booking_type": booking_type})
    return result.fetchone().id


async def _update_email_status(db: AsyncSession, booking_id: int, status: str):
    await db.execute(text(
        "UPDATE bookings SET email_status = :s, updated_at = NOW() WHERE id = :id"
    ), {"s": status, "id": booking_id})


async def _update_sms_status(db: AsyncSession, booking_id: int, status: str):
    await db.execute(text(
        "UPDATE bookings SET sms_status = :s, updated_at = NOW() WHERE id = :id"
    ), {"s": status, "id": booking_id})


async def _log_send(db: AsyncSession, data: dict):
    await db.execute(text("""
        INSERT INTO send_log
            (module, order_number, first_name, last_name, email, phone,
             tour_date, tour_type, email_status, sms_status,
             sms_sid, error_msg, sent_at)
        VALUES
            (:module, :order_number, :first_name, :last_name, :email, :phone,
             :tour_date, :tour_type, :email_status, :sms_status,
             :sms_sid, :error_msg, NOW())
    """), data)


# ═══════════════════════════════════════════════════════════
# POST /send/tour-confirmation
# ═══════════════════════════════════════════════════════════
@router.post("/send/tour-confirmation")
async def send_tour_confirmation(
    file:      UploadFile = File(...),
    tour_type: str        = Form(...),
    tour_date: str        = Form(...),   # YYYY-MM-DD
    db:        AsyncSession = Depends(get_db),
    _user = Depends(get_current_user),
):
    if tour_type not in tc.TOUR_TYPES:
        raise HTTPException(400, f"Unknown tour_type: {tour_type}")

    file_bytes = await file.read()
    parsed = parse_excel(file_bytes, "tour_confirmation")
    if "error" in parsed:
        raise HTTPException(400, parsed["error"])

    rows = parsed["rows"]
    results = []

    for row in rows:
        order_num = row["order_number"]
        email     = row["email"]
        phone     = row["phone"]
        first     = row["first_name"]

        if not email:
            results.append({"order": order_num, "status": "skipped", "reason": "no email"})
            continue

        # Upsert booking
        booking_data = {
            "order_number":   order_num,
            "first_name":     first,
            "last_name":      row["last_name"],
            "customer_email": email,
            "phone":          phone,
            "quantities":     int(row.get("quantities") or 1),
            "pickup_time":    row["pickup_time"],
            "pickup_location": row["pickup_location"],
            "tour_date":      _to_date(tour_date),
            "tour_type":      tour_type,
            "module":         "tour_confirmation",
        }
        booking_id = await _upsert_booking(db, booking_data)

        # Generate token + URLs
        token     = tc.make_token(booking_id, email, tour_date)
        email_url = tc.confirm_url(token, src="email")
        sms_url   = tc.confirm_url(token, src="sms")

        # Store token in bookings.confirm_token so guest.py can look it up
        await db.execute(text(
            "UPDATE bookings SET confirm_token = :token WHERE id = :id"
        ), {"token": token, "id": booking_id})

        # Lookup pickup location photo URL
        ploc = row.get('pickup_location', '')
        loc_res = await db.execute(text(
            "SELECT photo_url, instruction FROM pickup_locations WHERE hotel_name ILIKE :name LIMIT 1"
        ), {"name": ploc})
        loc_row = loc_res.fetchone()
        pickup_photo_url   = loc_row[0] if loc_row else ''
        pickup_instruction = loc_row[1] if loc_row else ''

        # Build & send email
        email_html = tc.build_email(row, tour_type, tour_date, email_url,
                                    pickup_instruction=pickup_instruction,
                                    pickup_photo_url=pickup_photo_url,
                                    pickup_photo_label=f"{ploc} Pickup location - click here for detail")
        subject    = f"Tour Confirmation & Lunch Selection – {_fmt_date(tour_date)}"
        email_res  = send_email(email, f"{first} {row['last_name']}", subject, email_html)
        email_status = "sent" if email_res["success"] else f"failed: {email_res.get('error','')}"
        await _update_email_status(db, booking_id, email_status)

        # Send SMS
        sms_status = ""
        sms_sid    = ""
        if phone:
            sms_body = tc.build_sms(first, tour_type, tour_date, sms_url)
            sms_res  = send_sms(phone, sms_body, module="tour_confirmation")
            if sms_res["success"]:
                sms_sid    = sms_res.get("sid", "")
                sms_status = f"sent:{sms_sid}"
            else:
                sms_status = f"failed: {sms_res.get('error','')}"
            await _update_sms_status(db, booking_id, sms_status)

        # Log
        await _log_send(db, {
            "module":       "tour_confirmation",
            "order_number": order_num,
            "first_name":   first,
            "last_name":    row["last_name"],
            "email":        email,
            "phone":        phone,
            "tour_date":    _to_date(tour_date),
            "tour_type":    tour_type,
            "email_status": email_status,
            "sms_status":   sms_status,
            "sms_sid":      sms_sid,
            "error_msg":    "" if email_res["success"] else email_res.get("error", ""),
        })

        results.append({
            "order":        order_num,
            "name":         f"{first} {row['last_name']}",
            "email_status": email_status,
            "sms_status":   sms_status,
        })

        await asyncio.sleep(0.3)  # rate-limit

    await db.commit()
    sent  = sum(1 for r in results if r.get("email_status", "").startswith("sent"))
    return {"total": len(rows), "sent": sent, "results": results}


# ═══════════════════════════════════════════════════════════
# POST /send/morning-pickup
# ═══════════════════════════════════════════════════════════
@router.post("/send/morning-pickup")
async def send_morning_pickup(
    file: UploadFile = File(...),
    db:   AsyncSession = Depends(get_db),
    _user = Depends(get_current_user),
):
    file_bytes = await file.read()
    parsed = parse_excel(file_bytes, "morning_pickup")
    if "error" in parsed:
        raise HTTPException(400, parsed["error"])

    rows    = parsed["rows"]
    results = []
    today   = datetime.now().strftime("%Y-%m-%d")

    for row in rows:
        order_num = row["order_number"]
        phone     = row["phone"]
        email     = row["email"]
        first     = row["first_name"]

        if not phone:
            results.append({"order": order_num, "status": "skipped", "reason": "no phone"})
            continue

        # Upsert
        booking_data = {
            "order_number":    order_num,
            "first_name":      first,
            "last_name":       row["last_name"],
            "customer_email":  email,
            "phone":           phone,
            "quantities":      int(row.get("quantities") or 1),
            "pickup_time":     row["pickup_time"],
            "pickup_location": row["pickup_location"],
            "tour_date":       _to_date(today),
            "tour_type":       "",
            "module":          "morning_pickup",
        }
        booking_id = await _upsert_booking(db, booking_data)

        # SMS
        sms_body   = mp.build_sms(row)
        sms_res    = send_sms(phone, sms_body, module="morning_pickup")
        sms_sid    = sms_res.get("sid", "") if sms_res["success"] else ""
        sms_status = f"sent:{sms_sid}" if sms_res["success"] else f"failed: {sms_res.get('error','')}"
        await _update_sms_status(db, booking_id, sms_status)

        # Email (optional — only if column present)
        email_status = ""
        if email:
            email_html   = mp.build_email(row)
            subject      = mp.email_subject(row)
            email_res    = send_email(email, row.get("name", first), subject, email_html)
            email_status = "sent" if email_res["success"] else f"failed: {email_res.get('error','')}"
            await _update_email_status(db, booking_id, email_status)

        await _log_send(db, {
            "module":       "morning_pickup",
            "order_number": order_num,
            "first_name":   first,
            "last_name":    row["last_name"],
            "email":        email,
            "phone":        phone,
            "tour_date":    _to_date(today),
            "tour_type":    "",
            "email_status": email_status,
            "sms_status":   sms_status,
            "sms_sid":      sms_sid,
            "error_msg":    "" if sms_res["success"] else sms_res.get("error", ""),
        })

        results.append({
            "order":        order_num,
            "name":         row.get("name", first),
            "sms_status":   sms_status,
            "email_status": email_status,
        })

        await asyncio.sleep(0.3)

    await db.commit()
    sent = sum(1 for r in results if r.get("sms_status", "").startswith("sent"))
    return {"total": len(rows), "sent": sent, "results": results}


# ═══════════════════════════════════════════════════════════
# POST /send/tickets-reminder
# ═══════════════════════════════════════════════════════════
@router.post("/send/tickets-reminder")
async def send_tickets_reminder(
    file:         UploadFile = File(...),
    tour_type:    str        = Form(...),
    service_date: str        = Form(...),   # YYYY-MM-DD
    db:           AsyncSession = Depends(get_db),
    _user = Depends(get_current_user),
):
    if tour_type not in tix.TOUR_TYPES:
        raise HTTPException(400, f"Unknown tour_type: {tour_type}")

    file_bytes = await file.read()
    parsed = parse_excel(file_bytes, "tickets_reminder")
    if "error" in parsed:
        raise HTTPException(400, parsed["error"])

    rows    = parsed["rows"]
    results = []

    for row in rows:
        # tickets use CHD# as order_number
        order_num = row["order_number"]
        email     = row["email"]
        phone     = row["phone"]
        first     = row["first_name"]
        last      = row["last_name"]

        if not email and not phone:
            results.append({"order": order_num, "status": "skipped", "reason": "no email or phone"})
            continue

        booking_data = {
            "order_number":    order_num,
            "first_name":      first,
            "last_name":       last,
            "customer_email":  email,
            "phone":           phone,
            "quantities":      int(row.get("quantities") or 1),
            "pickup_time":     row.get("checkin_time", ""),
            "pickup_location": row.get("tour_location", ""),
            "tour_date":       _to_date(service_date),
            "tour_type":       tour_type,
            "module":          "tickets_reminder",
        }
        booking_id = await _upsert_booking(db, booking_data)

        token    = tix.make_token(booking_id, email, service_date)
        form_url = tix.confirm_url(token, src="email")
        sms_url  = tix.confirm_url(token, src="sms")

        # Email
        email_status = ""
        if email:
            email_html   = tix.build_email(row, tour_type, service_date, form_url)
            subject      = f"Tickets Reminder – {tix.TOUR_TYPES[tour_type]['label']} – {_fmt_date(service_date)}"
            email_res    = send_email(email, f"{first} {last}", subject, email_html)
            email_status = "sent" if email_res["success"] else f"failed: {email_res.get('error','')}"
            await _update_email_status(db, booking_id, email_status)

        # SMS
        sms_status = ""
        sms_sid    = ""
        if phone:
            sms_body   = tix.build_sms(row, tour_type, sms_url)
            sms_res    = send_sms(phone, sms_body, module="tickets_reminder")
            sms_sid    = sms_res.get("sid", "") if sms_res["success"] else ""
            sms_status = f"sent:{sms_sid}" if sms_res["success"] else f"failed: {sms_res.get('error','')}"
            await _update_sms_status(db, booking_id, sms_status)

        await _log_send(db, {
            "module":       "tickets_reminder",
            "order_number": order_num,
            "first_name":   first,
            "last_name":    last,
            "email":        email,
            "phone":        phone,
            "tour_date":    _to_date(service_date),
            "tour_type":    tour_type,
            "email_status": email_status,
            "sms_status":   sms_status,
            "sms_sid":      sms_sid,
            "error_msg":    "",
        })

        results.append({
            "order":        order_num,
            "name":         f"{first} {last}",
            "email_status": email_status,
            "sms_status":   sms_status,
        })

        await asyncio.sleep(0.3)

    await db.commit()
    sent = sum(1 for r in results if r.get("email_status", "").startswith("sent"))
    return {"total": len(rows), "sent": sent, "results": results}


# ═══════════════════════════════════════════════════════════
# POST /webhook/sms-status  — Twilio StatusCallback
# ═══════════════════════════════════════════════════════════
@router.post("/webhook/sms-status")
async def sms_status_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Twilio calls this with form-encoded body containing:
      MessageSid, MessageStatus, To, From, etc.
    We find the booking by sms_status LIKE '%<sid>%' and update it.
    Also updates send_log.sms_status for the matching sid.
    """
    form = await request.form()
    sid    = form.get("MessageSid", "")
    status = form.get("MessageStatus", "")

    if not sid or not status:
        return JSONResponse({"ok": True})

    # Update bookings table
    await db.execute(text("""
        UPDATE bookings
        SET sms_status = :new_status, updated_at = NOW()
        WHERE sms_status LIKE :sid_pattern
    """), {
        "new_status":  f"{status}:{sid}",
        "sid_pattern": f"%{sid}%",
    })

    # Update send_log table
    await db.execute(text("""
        UPDATE send_log
        SET sms_status = :new_status
        WHERE sms_sid = :sid
    """), {
        "new_status": status,
        "sid":        sid,
    })

    await db.commit()
    logger.info("SMS callback: %s → %s", sid, status)
    return JSONResponse({"ok": True})


# ═══════════════════════════════════════════════════════════
# Helper
# ═══════════════════════════════════════════════════════════
def _fmt_date(date_str: str) -> str:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%B %-d, %Y")
    except ValueError:
        return date_str
