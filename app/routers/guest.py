from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Booking, BookingStatus

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


class GuestConfirmRequest(BaseModel):
    token: str
    lunch_option: str = "standard"  # "standard" | "vegetarian" | "vegan" | "gluten_free"


@router.get("/confirm/{token}", response_class=HTMLResponse)
async def guest_confirm_page(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Guest-facing confirmation page."""
    result = await db.execute(select(Booking).where(Booking.confirm_token == token))
    booking = result.scalar_one_or_none()

    if not booking:
        return HTMLResponse("<h1>Invalid or expired confirmation link.</h1>", status_code=404)

    return templates.TemplateResponse("confirm.html", {
        "request": request,
        "booking": booking,
        "already_confirmed": booking.guest_confirmed_at is not None,
    })


@router.post("/api/guest/confirm")
async def guest_confirm_submit(data: GuestConfirmRequest, db: AsyncSession = Depends(get_db)):
    """Process guest confirmation form submission."""
    result = await db.execute(select(Booking).where(Booking.confirm_token == data.token))
    booking = result.scalar_one_or_none()

    if not booking:
        raise HTTPException(404, "Invalid token")
    if booking.status == BookingStatus.cancelled:
        raise HTTPException(400, "This booking has been cancelled")

    booking.lunch_option = data.lunch_option
    booking.guest_confirmed_at = datetime.utcnow()
    booking.status = BookingStatus.confirmed

    await db.commit()
    return {"message": "Thank you! Your spot is confirmed.", "lunch_option": data.lunch_option}
