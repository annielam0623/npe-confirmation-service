from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Booking, BookingStatus, NotificationLog, NotificationType, NotificationStatus
from app.auth import get_current_user
from app.services import sendgrid, twilio_sms

router = APIRouter()


class SendRequest(BaseModel):
    booking_id: int
    send_email: bool = True
    send_sms: bool = True


async def _log_notification(db, booking_id, ntype, channel, recipient, result: dict):
    log = NotificationLog(
        booking_id=booking_id,
        notification_type=ntype,
        channel=channel,
        recipient=recipient,
        status=NotificationStatus.sent if not result.get("error") else NotificationStatus.failed,
        sent_at=datetime.utcnow() if not result.get("error") else None,
        error_message=result.get("error"),
        external_id=result.get("message_id") or result.get("sid"),
    )
    db.add(log)


@router.post("/send-confirmation")
async def send_confirmation(
    req: SendRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Send tour confirmation to guest (email + SMS).
    Booking must have driver_name and bus_number filled in (status = ready).
    """
    result = await db.execute(select(Booking).where(Booking.id == req.booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(404, "Booking not found")
    if booking.status == BookingStatus.pending:
        raise HTTPException(400, "Booking is still pending — fill in driver and bus number first")
    if booking.status == BookingStatus.cancelled:
        raise HTTPException(400, "Booking is cancelled")

    results = {}

    if req.send_email and booking.guest_email:
        try:
            email_result = await sendgrid.send_confirmation_email(booking)
            results["email"] = email_result
            await _log_notification(db, booking.id, NotificationType.confirmation, "email", booking.guest_email, email_result)
        except Exception as e:
            results["email"] = {"error": str(e)}
            await _log_notification(db, booking.id, NotificationType.confirmation, "email", booking.guest_email, {"error": str(e)})

    if req.send_sms and booking.guest_phone:
        try:
            sms_result = await twilio_sms.send_confirmation_sms(booking)
            results["sms"] = sms_result
            await _log_notification(db, booking.id, NotificationType.confirmation, "sms", booking.guest_phone, sms_result)
        except Exception as e:
            results["sms"] = {"error": str(e)}
            await _log_notification(db, booking.id, NotificationType.confirmation, "sms", booking.guest_phone, {"error": str(e)})

    booking.status = BookingStatus.sent
    await db.commit()
    return {"booking_id": booking.id, "results": results}


@router.post("/send-morning-reminder")
async def send_morning_reminder(
    req: SendRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Send morning pickup reminder (email + SMS)."""
    result = await db.execute(select(Booking).where(Booking.id == req.booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(404, "Booking not found")

    results = {}

    if req.send_email and booking.guest_email:
        try:
            r = await sendgrid.send_morning_reminder_email(booking)
            results["email"] = r
            await _log_notification(db, booking.id, NotificationType.morning_reminder, "email", booking.guest_email, r)
        except Exception as e:
            results["email"] = {"error": str(e)}

    if req.send_sms and booking.guest_phone:
        try:
            r = await twilio_sms.send_morning_reminder_sms(booking)
            results["sms"] = r
            await _log_notification(db, booking.id, NotificationType.morning_reminder, "sms", booking.guest_phone, r)
        except Exception as e:
            results["sms"] = {"error": str(e)}

    await db.commit()
    return {"booking_id": booking.id, "results": results}


@router.post("/send-ticket-reminder")
async def send_ticket_reminder(
    req: SendRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Send ticket reminder SMS (day before tour)."""
    result = await db.execute(select(Booking).where(Booking.id == req.booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(404, "Booking not found")

    results = {}

    if req.send_sms and booking.guest_phone:
        try:
            r = await twilio_sms.send_ticket_reminder_sms(booking)
            results["sms"] = r
            await _log_notification(db, booking.id, NotificationType.ticket_reminder, "sms", booking.guest_phone, r)
        except Exception as e:
            results["sms"] = {"error": str(e)}

    await db.commit()
    return {"booking_id": booking.id, "results": results}


@router.get("/logs/{booking_id}")
async def get_notification_logs(
    booking_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(NotificationLog).where(NotificationLog.booking_id == booking_id)
    )
    logs = result.scalars().all()
    return logs
