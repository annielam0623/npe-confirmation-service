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
from typing import Annotated, Optional
import json
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.auth import require_staff, get_current_user
from app.services.excel_parser import parse_excel
from app.services.sendgrid import send_raw_email as send_email
from app.services.sms import send_sms_async
from app.services import tour_confirmation as tc
from app.services import morning_pickup as mp
from app.services import morning_pickup as morning_pickup
from app.services import tickets_reminder as tix
from app.services import excel_parser

logger = logging.getLogger(__name__)
router = APIRouter()
LA = ZoneInfo("America/Los_Angeles")

def _to_date(d: str) -> date:
    """Convert YYYY-MM-DD string to Python date object for asyncpg."""
    if isinstance(d, date):
        return d
    return datetime.strptime(d, "%Y-%m-%d").date()


def _fmt_date(date_str: str) -> str:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%B %-d, %Y")
    except ValueError:
        return date_str


# ═══════════════════════════════════════════════════════════
# Helper — insert or update booking record, return row id
# ═══════════════════════════════════════════════════════════
async def _upsert_booking(db: AsyncSession, data: dict) -> int:
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

    driver     = data.get("driver")
    vehicle_no = data.get("vehicle_no")

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
                driver           = :driver,
                vehicle_no       = :vehicle_no,
                mtlv_eligible    = :mtlv_eligible,
                token_created    = NOW(),
                email_status     = 'pending',
                sms_status       = 'pending',
                updated_at       = NOW()
            WHERE id = :id
        """), {**data, "driver": driver, "vehicle_no": vehicle_no, "id": row.id})
        return row.id

    booking_type = "self_drive" if data.get("module") == "tickets_reminder" else "bus_tour"
    result = await db.execute(text("""
        INSERT INTO bookings
            (order_number, first_name, last_name, customer_email, phone,
             quantities, pickup_time, pickup_location, tour_date, tour_type,
             driver, vehicle_no, mtlv_eligible,
             module, booking_type, confirmation, token_created, email_status, sms_status,
             created_at, updated_at)
        VALUES
            (:order_number, :first_name, :last_name, :customer_email, :phone,
             :quantities, :pickup_time, :pickup_location, :tour_date, :tour_type,
             :driver, :vehicle_no, :mtlv_eligible,
             :module, :booking_type, 'pending', NOW(), 'pending', 'pending',
             NOW(), NOW())
        RETURNING id
    """), {**data, "driver": driver, "vehicle_no": vehicle_no, "booking_type": booking_type})
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
    try:
        await db.execute(text("""
            INSERT INTO send_log
                (module, order_number, first_name, last_name, email, phone,
                 tour_date, tour_type, email_status, sms_status,
                 sms_sid, email_message_id, error_msg, sent_by, sent_at)
            VALUES
                (:module, :order_number, :first_name, :last_name, :email, :phone,
                 :tour_date, :tour_type, :email_status, :sms_status,
                 :sms_sid, :email_message_id, :error_msg, :sent_by, :sent_at)
        """), {**data, "sent_at": datetime.now(LA)})
        await db.commit()
    except Exception as e:
        logger.error(f"[_log_send] failed for {data.get('order_number')}: {e}")


# ═══════════════════════════════════════════════════════════
# POST /send/tour-confirmation
# ═══════════════════════════════════════════════════════════
@router.post("/send/tour-confirmation")
async def send_tour_confirmation(
    file:      UploadFile = File(...),
    tour_type: str        = Form(...),
    tour_date: str        = Form(...),   # YYYY-MM-DD
    db:        AsyncSession = Depends(get_db),
    user = Depends(require_staff),
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
            "order_number":    order_num,
            "first_name":      first,
            "last_name":       row["last_name"],
            "customer_email":  email,
            "phone":           phone,
            "quantities":      int(row.get("quantities") or 1),
            "pickup_time":     row["pickup_time"],
            "pickup_location": row["pickup_location"],
            "tour_date":       _to_date(tour_date),
            "tour_type":       tour_type,
            "module":          "tour_confirmation",
            "mtlv_eligible":   (row.get("mtlv_promo") or "").strip().upper() == "ELIGIBLE",
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
        ), {"name": f"%{ploc}%"})
        loc_row = loc_res.fetchone()
        pickup_photo_url   = loc_row[0] if loc_row else ''
        pickup_instruction = loc_row[1] if loc_row else ''

        # Build & send email
        email_html = tc.build_email(row, tour_type, tour_date, email_url,
                                    pickup_instruction=pickup_instruction,
                                    pickup_photo_url=pickup_photo_url,
                                    pickup_photo_label=f"{ploc} Pickup location - click here for detail")
        subject = f"Tour Confirmation & Lunch Selection – {_fmt_date(tour_date)}"

        email_message_id = ""
        try:
            email_res        = await send_email(email, f"{first} {row['last_name']}", subject, email_html)
            email_message_id = email_res.get("message_id", "") if isinstance(email_res, dict) else ""
            email_status     = "sent"
        except Exception as e:
            email_status = f"failed: {e}"
            logger.error(f"[tour_confirmation] Email failed — {email} error={e}")
        await _update_email_status(db, booking_id, email_status)

        # Send SMS
        sms_status = ""
        sms_sid    = ""
        if phone:
            sms_body = tc.build_sms(first, tour_type, tour_date, sms_url)
            sms_res  = await send_sms_async(phone, sms_body, module="tour_confirmation")
            if sms_res["success"]:
                sms_sid    = sms_res.get("sid", "")
                sms_status = f"sent:{sms_sid}"
            else:
                sms_status = f"failed: {sms_res.get('error','')}"
                logger.error(f"[tour_confirmation] SMS failed — phone={phone} order={order_num} error={sms_res.get('error','')}")
            await _update_sms_status(db, booking_id, sms_status)

        # Log
        await _log_send(db, {
            "module":           "tour_confirmation",
            "order_number":     order_num,
            "first_name":       first,
            "last_name":        row["last_name"],
            "email":            email,
            "phone":            phone,
            "tour_date":        _to_date(tour_date),
            "tour_type":        tour_type,
            "email_status":     email_status,
            "sms_status":       sms_status,
            "sms_sid":          sms_sid,
            "email_message_id": email_message_id,
            "error_msg":        "" if email_status.startswith("sent") else email_status,
            "sent_by":          user.username,
        })
        results.append({
            "order":        order_num,
            "name":         f"{first} {row['last_name']}",
            "email_status": email_status,
            "sms_status":   sms_status,
        })
        await asyncio.sleep(0.3)

    await db.commit()
    sent = sum(1 for r in results if r.get("email_status", "").startswith("sent"))
    return {"total": len(rows), "sent": sent, "results": results}

# ═══════════════════════════════════════════════════════════
# POST /send/tour-confirmation-bulk  (JSON guest list)
# ═══════════════════════════════════════════════════════════
@router.post("/send/tour-confirmation-bulk")
async def send_tour_confirmation_bulk(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_staff),
):
    body      = await request.json()
    tour_type = body.get("tour_type", "")
    tour_date = body.get("tour_date", "")
    send_type = body.get("send_type", "combined")
    guests    = body.get("guests", [])

    if tour_type not in tc.TOUR_TYPES:
        raise HTTPException(400, f"Unknown tour_type: {tour_type}")

    results = []

    for row in guests:
        order_num = row.get("order_number", "")
        email     = row.get("customer_email", "")
        phone     = row.get("phone", "")
        first     = row.get("first_name", "")
        last      = row.get("last_name", "")

        if not email and send_type in ("email", "combined"):
            results.append({"order": order_num, "name": f"{first} {last}", "email_status": "skipped", "sms_status": ""})
            continue

        booking_data = {
            "order_number":    order_num,
            "first_name":      first,
            "last_name":       last,
            "customer_email":  email,
            "phone":           phone,
            "quantities":      int(row.get("quantities") or 1),
            "pickup_time":     row.get("pickup_time", ""),
            "pickup_location": row.get("pickup_location", ""),
            "tour_date":       _to_date(tour_date),
            "tour_type":       tour_type,
            "module":          "tour_confirmation",
            "mtlv_eligible":   row.get("mtlv_eligible", False),
        }
        booking_id = await _upsert_booking(db, booking_data)

        token     = tc.make_token(booking_id, email, tour_date)
        email_url = tc.confirm_url(token, src="email")
        sms_url   = tc.confirm_url(token, src="sms")

        await db.execute(text(
            "UPDATE bookings SET confirm_token = :token WHERE id = :id"
        ), {"token": token, "id": booking_id})

        ploc = row.get("pickup_location", "")
        loc_res = await db.execute(text(
            "SELECT photo_url, instruction FROM pickup_locations WHERE hotel_name ILIKE :name LIMIT 1"
        ), {"name": f"%{ploc}%"})
        loc_row = loc_res.fetchone()
        pickup_photo_url   = loc_row[0] if loc_row else ""
        pickup_instruction = loc_row[1] if loc_row else ""

        email_status = ""
        email_message_id = ""
        if send_type in ("email", "combined") and email:
            email_html = tc.build_email(row, tour_type, tour_date, email_url,
                                        pickup_instruction=pickup_instruction,
                                        pickup_photo_url=pickup_photo_url,
                                        pickup_photo_label=f"{ploc} Pickup location - click here for detail")
            subject = f"Tour Confirmation & Lunch Selection – {_fmt_date(tour_date)}"
            try:
                email_res        = await send_email(email, f"{first} {last}", subject, email_html)
                email_message_id = email_res.get("message_id", "") if isinstance(email_res, dict) else ""
                email_status     = "sent"
            except Exception as e:
                email_status = f"failed: {e}"
                logger.error(f"[tour_confirmation] Email failed — {email} error={e}")
            await _update_email_status(db, booking_id, email_status)

        sms_status = ""
        sms_sid    = ""
        if send_type in ("sms", "combined") and phone:
            sms_body = tc.build_sms(first, tour_type, tour_date, sms_url)
            sms_res  = await send_sms_async(phone, sms_body, module="tour_confirmation")
            if sms_res["success"]:
                sms_sid    = sms_res.get("sid", "")
                sms_status = f"sent:{sms_sid}"
            else:
                sms_status = f"failed: {sms_res.get('error','')}"
                logger.error(f"[tour_confirmation] SMS failed — phone={phone} order={order_num}")
            await _update_sms_status(db, booking_id, sms_status)

        await _log_send(db, {
            "module":           "tour_confirmation",
            "order_number":     order_num,
            "first_name":       first,
            "last_name":        last,
            "email":            email,
            "phone":            phone,
            "tour_date":        _to_date(tour_date),
            "tour_type":        tour_type,
            "email_status":     email_status,
            "sms_status":       sms_status,
            "sms_sid":          sms_sid,
            "email_message_id": email_message_id,
            "error_msg":        "" if email_status.startswith("sent") else email_status,
            "sent_by":          user.username,
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
    return {"total": len(guests), "sent": sent, "results": results}



# ═══════════════════════════════════════════════════════════
# POST /send/morning-pickup
# ═══════════════════════════════════════════════════════════
@router.post("/send/morning-pickup")
async def send_morning_pickup(
    file: UploadFile = File(...),
    send_type: str = Form("sms"),
    selected_orders: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    user = Depends(require_staff),
):
    contents = await file.read()
    parse_result = parse_excel(contents, "morning_pickup")
    if "error" in parse_result:
        raise HTTPException(status_code=400, detail=parse_result["error"])

    rows = parse_result["rows"]

    # ── Filter to selected orders ──────────────────────────────────────────
    if selected_orders:
        try:
            order_set = set(json.loads(selected_orders))
        except (ValueError, TypeError):
            order_set = None
    else:
        order_set = None  # None = send all (backwards-compatible)

    results = []
    sent_count = 0
    failed_count = 0
    skipped_count = 0

    for row in rows:
        order_num = row.get("order_number", "")

        # Mark skipped if not in selected set
        if order_set is not None and order_num not in order_set:
            results.append({
                "order":        order_num,
                "name":         row.get("name", ""),
                "phone":        row.get("phone", ""),
                "pickup_time":  row.get("pickup_time", ""),
                "sms_status":   "",
                "email_status": "",
                "skipped":      True,
            })
            skipped_count += 1
            continue

# ── Upsert booking ────────────────────────────────────────────────
        today_la = datetime.now(LA).date().isoformat()
        booking_data = {
            "module":          "morning_pickup",
            "order_number":    order_num,
            "first_name":      row.get("first_name", ""),
            "last_name":       row.get("last_name", ""),
            "customer_email":  row.get("email", ""),
            "phone":           row.get("phone", ""),
            "quantities":      int(row.get("quantities") or 1),
            "pickup_time":     row.get("pickup_time", ""),
            "pickup_location": row.get("pickup_location", ""),
            "tour_date":       _to_date(today_la),
            "tour_type":       "",
            "driver":          row.get("driver", ""),
            "vehicle_no":      row.get("vehicle_no", ""),
            "mtlv_eligible":   False,
        }
        booking_id = await _upsert_booking(db, booking_data)


        # ── Send SMS ──────────────────────────────────────────────────────
        sms_status = ""
        sms_sid    = ""
        if send_type in ("sms", "combined"):
            sms_body = morning_pickup.build_sms(row)
            sms_res  = await send_sms_async(row.get("phone", ""), sms_body, module="morning_pickup")
            if sms_res["success"]:
                sms_sid    = sms_res.get("sid", "")
                sms_status = f"sent:{sms_sid}"
                await _update_sms_status(db, booking_id, sms_status)
            else:
                sms_status = f"failed: {sms_res.get('error', '')}"
                logger.error(f"[morning_pickup] SMS failed — phone={row.get('phone')} order={order_num} error={sms_res.get('error','')}")

        # ── Send Email ────────────────────────────────────────────────────
        email_status     = ""
        email_message_id = ""
        if send_type in ("email", "combined") and row.get("email"):
            email_html = morning_pickup.build_email(row)
            subject    = morning_pickup.email_subject(row)
            try:
                email_res        = await send_email(row["email"], row.get("name", ""), subject, email_html)
                email_message_id = email_res.get("message_id", "") if isinstance(email_res, dict) else ""
                email_status     = "sent"
            except Exception as e:
                email_status = f"failed: {e}"
                logger.error(f"[morning_pickup] Email failed — {row.get('email')} error={e}")

        # ── Log to send_log ───────────────────────────────────────────────
        await _log_send(db, {
            "module":           "morning_pickup",
            "order_number":     order_num,
            "first_name":       row.get("name", "").split()[0] if row.get("name") else "",
            "last_name":        " ".join(row.get("name", "").split()[1:]) if row.get("name") else "",
            "email":            row.get("email", ""),
            "phone":            row.get("phone", ""),
            "tour_date":        _to_date(today_la),
            "tour_type":        "",
            "email_status":     email_status,
            "sms_status":       sms_status,
            "sms_sid":          sms_sid,
            "email_message_id": email_message_id,
            "error_msg":        "",
            "sent_by":          user.username,
        })

        if "sent" in (sms_status + email_status):
            sent_count += 1
        elif "failed" in (sms_status + email_status):
            failed_count += 1

        results.append({
            "order":        order_num,
            "name":         row.get("name", ""),
            "phone":        row.get("phone", ""),
            "pickup_time":  row.get("pickup_time", ""),
            "sms_status":   sms_status,
            "email_status": email_status,
            "skipped":      False,
        })

    return {
        "total":         len(rows),
        "sent":          sent_count,
        "failed":        failed_count,
        "skipped":       skipped_count,
        "results":       results,
    }

# ═══════════════════════════════════════════════════════════
# POST /send/tickets-reminder
# ═══════════════════════════════════════════════════════════
@router.post("/send/tickets-reminder")
async def send_tickets_reminder(
    file:         UploadFile = File(...),
    tour_type:    str        = Form(...),
    service_date: str        = Form(...),   # YYYY-MM-DD
    db:           AsyncSession = Depends(get_db),
    user = Depends(require_staff),
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
            "mtlv_eligible":   False,
        }
        booking_id = await _upsert_booking(db, booking_data)

        token    = tix.make_token(booking_id, email, service_date)
        form_url = tix.confirm_url(token, src="email")
        sms_url  = tix.confirm_url(token, src="sms")

        # Email
        email_status     = ""
        email_message_id = ""
        if email:
            email_html = tix.build_email(row, tour_type, service_date, form_url)
            subject    = f"Tickets Reminder – {tix.TOUR_TYPES[tour_type]['label']} – {_fmt_date(service_date)}"
            try:
                email_res        = await send_email(email, f"{first} {last}", subject, email_html)
                email_message_id = email_res.get("message_id", "") if isinstance(email_res, dict) else ""
                email_status     = "sent"
            except Exception as e:
                email_status = f"failed: {e}"
                logger.error(f"[tickets_reminder] Email failed — {email} error={e}")
            await _update_email_status(db, booking_id, email_status)

        # SMS
        sms_status = ""
        sms_sid    = ""
        if phone:
            sms_body = tix.build_sms(row, tour_type, sms_url)
            sms_res  = await send_sms_async(phone, sms_body, module="tickets_reminder")
            sms_sid    = sms_res.get("sid", "") if sms_res["success"] else ""
            sms_status = f"sent:{sms_sid}" if sms_res["success"] else f"failed: {sms_res.get('error','')}"
            if not sms_res["success"]:
                logger.error(f"[tickets_reminder] SMS failed — phone={phone} order={order_num} error={sms_res.get('error','')}")
            await _update_sms_status(db, booking_id, sms_status)

        await _log_send(db, {
            "module":           "tickets_reminder",
            "order_number":     order_num,
            "first_name":       first,
            "last_name":        last,
            "email":            email,
            "phone":            phone,
            "tour_date":        _to_date(service_date),
            "tour_type":        tour_type,
            "email_status":     email_status,
            "sms_status":       sms_status,
            "sms_sid":          sms_sid,
            "email_message_id": email_message_id,
            "error_msg":        "",
            "sent_by":          user.username,
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

