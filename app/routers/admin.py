from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import date

from app.database import get_db
from app.models import Booking, BookingStatus
from app.auth import get_current_user

router = APIRouter()


@router.get("/dashboard")
async def dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Summary stats for the admin dashboard."""
    today = date.today()

    total = await db.scalar(select(func.count(Booking.id)))
    pending = await db.scalar(select(func.count(Booking.id)).where(Booking.status == BookingStatus.pending))
    ready = await db.scalar(select(func.count(Booking.id)).where(Booking.status == BookingStatus.ready))
    sent = await db.scalar(select(func.count(Booking.id)).where(Booking.status == BookingStatus.sent))
    confirmed = await db.scalar(select(func.count(Booking.id)).where(Booking.status == BookingStatus.confirmed))
    today_count = await db.scalar(select(func.count(Booking.id)).where(Booking.tour_date == today))

    return {
        "total_bookings": total,
        "today": today_count,
        "by_status": {
            "pending": pending,
            "ready": ready,
            "sent": sent,
            "confirmed": confirmed,
        }
    }
