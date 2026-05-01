"""
app/routers/bookings.py
Booking CRUD — field names match models.py exactly
"""

from datetime import date, datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database import get_db
from app.models import Booking, BookingStatus, BookingSource, BookingType
from app.auth import get_current_user

router = APIRouter()


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class BookingCreate(BaseModel):
    # Identifiers
    order_number:    str
    confirmation_no: Optional[str] = None

    # Guest
    first_name:     str
    last_name:      str = ""
    customer_email: EmailStr
    phone:          Optional[str] = None
    quantities:     int = 1

    # Tour
    booking_type:    BookingType   = BookingType.bus_tour
    tour_type:       Optional[str] = None
    tour_date:       Optional[date] = None
    pickup_time:     Optional[str] = None
    pickup_location: Optional[str] = None
    tour_time:       Optional[str] = None
    checkin_time:    Optional[str] = None
    tour_location:   Optional[str] = None

    # Meta
    source:         BookingSource = BookingSource.manual
    has_promotion:  bool = False
    mtlv_promo:     Optional[str] = None
    agent_name:     Optional[str] = None
    special_requirements: Optional[str] = None
    notes:          Optional[str] = None
    rezdy_order_id: Optional[str] = None


class BookingOpsUpdate(BaseModel):
    """Staff fills this in before sending Morning Reminder."""
    driver:       Optional[str] = None
    vehicle_no:   Optional[str] = None
    driver_phone: Optional[str] = None
    notes:        Optional[str] = None


class BookingConfirmationUpdate(BaseModel):
    """Staff manually overrides guest confirmation status."""
    confirmation: str  # pending | yes | modify_req | cancelled


class BookingOut(BaseModel):
    id:              int
    confirm_token:   str
    order_number:    str
    confirmation_no: Optional[str]
    first_name:      str
    last_name:       str
    customer_email:  str
    phone:           Optional[str]
    quantities:      int
    booking_type:    BookingType
    tour_type:       Optional[str]
    tour_date:       Optional[date]
    pickup_time:     Optional[str]
    pickup_location: Optional[str]
    tour_time:       Optional[str]
    checkin_time:    Optional[str]
    tour_location:   Optional[str]
    driver:          Optional[str]
    vehicle_no:      Optional[str]
    driver_phone:    Optional[str]
    has_promotion:   bool
    mtlv_promo:      Optional[str]
    lunch_turkey:    int
    lunch_veggie:    int
    lunch_beef:      int
    confirmation:    str
    submitted_at:    Optional[datetime]
    submission_count: int
    email_status:    str
    sms_status:      str
    status:          BookingStatus
    source:          BookingSource
    agent_name:      Optional[str]
    notes:           Optional[str]
    created_at:      datetime

    class Config:
        from_attributes = True


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[BookingOut])
async def list_bookings(
    status:    Optional[BookingStatus] = None,
    tour_date: Optional[date] = None,
    tour_type: Optional[str]  = None,
    limit:  int = Query(50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    q = select(Booking).order_by(desc(Booking.tour_date), Booking.pickup_time)
    if status:
        q = q.where(Booking.status == status)
    if tour_date:
        q = q.where(Booking.tour_date == tour_date)
    if tour_type:
        q = q.where(Booking.tour_type == tour_type)
    q = q.limit(limit).offset(offset)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/", response_model=BookingOut, status_code=201)
async def create_booking(
    data: BookingCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    booking = Booking(**data.model_dump())
    db.add(booking)
    await db.commit()
    await db.refresh(booking)
    return booking


@router.get("/{booking_id}", response_model=BookingOut)
async def get_booking(
    booking_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
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
    current_user = Depends(get_current_user),
):
    """Staff updates driver/vehicle info before Morning Reminder."""
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(404, "Booking not found")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(booking, field, value)

    if booking.driver and booking.vehicle_no:
        booking.status = BookingStatus.scheduled

    await db.commit()
    await db.refresh(booking)
    return booking


@router.patch("/{booking_id}/confirmation", response_model=BookingOut)
async def update_confirmation_status(
    booking_id: int,
    data: BookingConfirmationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Staff manually overrides guest confirmation (e.g. via phone)."""
    allowed = ("pending", "yes", "modify_req", "cancelled")
    if data.confirmation not in allowed:
        raise HTTPException(400, f"confirmation must be one of {allowed}")

    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(404, "Booking not found")

    booking.confirmation = data.confirmation
    if data.confirmation == "cancelled":
        booking.lunch_turkey = 0
        booking.lunch_veggie = 0
        booking.lunch_beef   = 0

    await db.commit()
    await db.refresh(booking)
    return booking


@router.delete("/{booking_id}", status_code=204)
async def cancel_booking(
    booking_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(404, "Booking not found")
    booking.status = BookingStatus.cancelled
    await db.commit()
