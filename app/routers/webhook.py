"""
NPE Webhook Router
Receives Rezdy order webhooks. Kept separate so it never breaks other modules.
Will be expanded when Rezdy webhook integration begins.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

router = APIRouter()


@router.post("/rezdy")
async def rezdy_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Placeholder for Rezdy webhook.
    Will parse Rezdy order payload and create bookings automatically.
    """
    payload = await request.json()
    # TODO: implement when Rezdy webhook is ready
    return {"status": "received", "message": "Rezdy webhook not yet implemented"}
