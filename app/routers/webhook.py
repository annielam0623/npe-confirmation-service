"""
NPE Webhook Router
Receives Rezdy order webhooks.
"""

import json
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

router = APIRouter()


@router.post("/rezdy")
async def rezdy_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        payload = await request.json()
    except Exception:
        payload = await request.body()
        payload = payload.decode("utf-8")

    print(f"[rezdy webhook] payload received:")
    print(json.dumps(payload, indent=2, ensure_ascii=False) if isinstance(payload, dict) else payload)

    return {"status": "received"}
