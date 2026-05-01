from datetime import date, time, datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database import get_db
from app.models import Booking, BookingStatus, BookingSource
from app.auth import get_current_user

router = APIRouter()


# ─── Pydantic Schemas ─────────────────────────────────────────────────────────

class BookingCreate(BaseModel):
    guest_first_name: str
    guest_last_name: str
    guest_email: EmailStr
    guest_phone: Optional[str] = None
    party_size: int = 1
    tour_name: str
    tour_date: date
    pickup_time: time
    pickup_location: str
    dropoff_location: Optional[str] = None
    special_notes: Optional[str] = None
    source: BookingSource = BookingSource.manual
    rezdy_order_id: Optional[str] = None


class BookingOpsUpdate(BaseModel):
    """Staff fills this in before sending confirmation."""
    driver_name: Optional[str] = None
    bus_number: Optional[str] = None
    driver_phone: Optional[str] = None
    special_notes: Optional[str] = None


class BookingOut(BaseModel):
    id: int
    confirm_token: str
    guest_first_name: str
    guest_last_name: str
    guest_email: str
    guest_phone: Optional[str]
    party_size: int
    tour_name: str
    tour_date: date
    pickup_time: time
    pickup_location: str
    dropoff_location: Optional[str]
    driver_name: Optional[str]
    bus_number: Optional[str]
    driver_phone: Optional[str]
    special_notes: Optional[str]
    lunch_option: Optional[str]
    guest_confirmed_at: Optional[datetime]
    status: BookingStatus
    source: BookingSource
    rezdy_order_id: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Rezdy Webhook Payload ─────────────────────────────────────────────────────

class RezdyOrderItem(BaseModel):
    productName: Optional[str] = None
    startTime: Optional[str] = None
    pickupLocation: Optional[str] = None
    quantities: Optional[List[dict]] = []


class RezdyCustomer(BaseModel):
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class RezdyWebhookPayload(BaseModel):
    orderNumber: Optional[str] = None
    customer: Optional[RezdyCustomer] = None
    items: Optional[List[RezdyOrderItem]] = []
    # Add more fields as you discover them from real payloads


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[BookingOut])
async def list_bookings(
    status: Optional[BookingStatus] = None,
    tour_date: Optional[date] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List bookings with optional filters."""
    q = select(Booking).order_by(desc(Booking.tour_date), Booking.pickup_time)
    if status:
        q = q.where(Booking.status == status)
    if tour_date:
        q = q.where(Booking.tour_date == tour_date)
    q = q.limit(limit).offset(offset)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/", response_model=BookingOut, status_code=201)
async def create_booking(
    data: BookingCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Manually create a booking."""
    booking = Booking(**data.model_dump())
    db.add(booking)
    await db.commit()
    await db.refresh(booking)
    return booking


@router.get("/{booking_id}", response_model=BookingOut)
async def get_booking(
    booking_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(404, "Booking not found")
    return booking


@router.patch("/{booking_id}/ops", response_model=BookingOut)
async def update_ops_info(
    booking_id: int,
    data: BookingOpsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Staff updates driver/bus info. Sets status to 'ready' if both filled."""
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(404, "Booking not found")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(booking, field, value)

    if booking.driver_name and booking.bus_number:
        booking.status = BookingStatus.ready

    await db.commit()
    await db.refresh(booking)
    return booking


@router.delete("/{booking_id}", status_code=204)
async def cancel_booking(
    booking_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(404, "Booking not found")
    booking.status = BookingStatus.cancelled
    await db.commit()


# ─── Rezdy Webhook (no auth — public endpoint) ────────────────────────────────

@router.post("/webhook/rezdy", status_code=201)
async def rezdy_webhook(payload: RezdyWebhookPayload, db: AsyncSession = Depends(get_db)):
    """
    Receive Rezdy order webhook. Creates a booking automatically.
    Maps Rezdy fields → NPE Booking fields.
    Adjust field names once you have real Rezdy payload examples.
    """
    customer = payload.customer or RezdyCustomer()
    item = payload.items[0] if payload.items else RezdyOrderItem()

    # Parse pickup time from Rezdy's startTime string (format: "2025-07-04 08:30:00")
    pickup_dt = None
    tour_date_val = None
    pickup_time_val = None
    if item.startTime:
        try:
            pickup_dt = datetime.strptime(item.startTime, "%Y-%m-%d %H:%M:%S")
            tour_date_val = pickup_dt.date()
            pickup_time_val = pickup_dt.time()
        except ValueError:
            pass

    # Calculate party size from quantities
    party_size = sum(q.get("value", 1) for q in (item.quantities or []))
    if party_size == 0:
        party_size = 1

    booking = Booking(
        source=BookingSource.rezdy,
        rezdy_order_id=payload.orderNumber,
        guest_first_name=customer.firstName or "Unknown",
        guest_last_name=customer.lastName or "",
        guest_email=customer.email or "",
        guest_phone=customer.phone,
        party_size=party_size,
        tour_name=item.productName or "NPE Tour",
        tour_date=tour_date_val,
        pickup_time=pickup_time_val,
        pickup_location=item.pickupLocation or "",
        status=BookingStatus.pending,
    )
    db.add(booking)
    await db.commit()
    await db.refresh(booking)
    return {"message": "Booking created", "booking_id": booking.id}
