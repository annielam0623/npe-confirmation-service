# app/services/short_links.py
"""
Short link service for NPE confirmation URLs.
Converts long token/tracking URLs into clean order-based short codes.

Codes:
  CHDBHURCV-TC  →  Tour Confirmation
  CHDBHURCV-TR  →  Ticket Reminder
  CHDBHURCV-MP  →  Morning Pickup
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

LA = ZoneInfo("America/Los_Angeles")
BASE_URL = "https://confirm.nationalparkexpress.com"


def _module_suffix(module: str) -> str:
    return {"tour_confirmation": "TC", "ticket_reminder": "TR", "morning_pickup": "MP"}[module]


async def upsert_short_link(
    db: AsyncSession,
    order_number: str,
    module: str,          # "tour_confirmation" | "ticket_reminder" | "morning_pickup"
    target_url: str,
    expires_at: datetime,
) -> str:
    """
    Create or overwrite the short link for this order+module.
    Returns the full short URL.
    """
    suffix = _module_suffix(module)
    code = f"{order_number}-{suffix}"

    # Normalize to naive UTC — DB column is timestamp without time zone
    if expires_at.tzinfo is not None:
        expires_at = expires_at.astimezone(timezone.utc).replace(tzinfo=None)

    await db.execute(text("""
        INSERT INTO short_links (code, target_url, module, order_number, expires_at, updated_at)
        VALUES (:code, :target_url, :module, :order_number, :expires_at, NOW())
        ON CONFLICT (code) DO UPDATE SET
            target_url = EXCLUDED.target_url,
            expires_at = EXCLUDED.expires_at,
            updated_at = NOW()
    """), {
        "code":         code,
        "target_url":   target_url.strip(),
        "module":       suffix,
        "order_number": order_number,
        "expires_at":   expires_at,
    })

    return f"{BASE_URL}/c/{code}"


async def resolve_short_link(
    db: AsyncSession,
    code: str,
) -> str | None:
    """
    Look up the target URL for a short code.
    Returns None if not found or expired.
    """
    row = (await db.execute(text("""
        SELECT target_url, expires_at FROM short_links
        WHERE code = :code
    """), {"code": code})).fetchone()

    if not row:
        return None

    # DB stores naive LA time — compare as LA time
    now_la = datetime.now(LA).replace(tzinfo=None)
    expires = row.expires_at
    if hasattr(expires, 'tzinfo') and expires.tzinfo is not None:
        expires = expires.astimezone(LA).replace(tzinfo=None)

    if expires < now_la:
        return None

    return row.target_url
