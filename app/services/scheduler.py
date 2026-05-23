"""
NPE Scheduler
Processes the email_queue table every 5 minutes (called by APScheduler or Railway cron).
Replaces WordPress wp-cron tconf_email_cron.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import EmailQueue, NotificationChannel
from app.services import sendgrid
from app.services.sms import send_sms_async

logger = logging.getLogger(__name__)


async def process_queue() -> dict:
    """
    Process all pending items in email_queue where scheduled_at <= now.
    Called every 5 minutes.
    Returns summary of processed items.
    """
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("America/Los_Angeles")).replace(tzinfo=None)
    sent = 0
    failed = 0

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(EmailQueue)
            .where(EmailQueue.status == "pending")
            .where(EmailQueue.scheduled_at <= now)
            .order_by(EmailQueue.scheduled_at)
            .limit(50)
        )
        items = result.scalars().all()

        for item in items:
            item.attempts = (item.attempts or 0) + 1
            try:
                if item.channel == NotificationChannel.email:
                    await _send_queued_email(item)
                elif item.channel == NotificationChannel.sms:
                    await _send_queued_sms(item)

                item.status = "sent"
                item.sent_at = datetime.now(timezone.utc)
                sent += 1

            except Exception as e:
                logger.error(f"Queue item {item.id} failed: {e}")
                item.error_msg = str(e)
                if item.attempts >= 3:
                    item.status = "failed"
                # else stays "pending" for retry
                failed += 1

        await db.commit()

    return {"processed": len(items), "sent": sent, "failed": failed}


async def _send_queued_email(item: EmailQueue):
    """Send a pre-rendered email from the queue."""
    if not item.to_email or not item.body:
        raise ValueError("Missing email address or body")
    await sendgrid.send_raw_email(
        to_email=item.to_email,
        to_name=item.to_name or "",
        subject=item.subject or "National Park Express",
        html_body=item.body,
    )


async def _send_queued_sms(item: EmailQueue):
    """Send a pre-rendered SMS from the queue."""
    if not item.to_phone or not item.sms_body:
        raise ValueError("Missing phone or SMS body")
    result = await send_sms_async(item.to_phone, item.sms_body, module="scheduler")
    if not result.get("success"):
        raise RuntimeError(result.get("error", "SMS send failed"))
