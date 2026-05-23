from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import uvicorn
import os
import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from app.database import init_db
from app.routers import auth, admin, bookings, notifications, guest, webhook
from app.routers import send
from app.routers import pickup_locations
from app.routers import promotions               # PDF upload — 不动
from app.routers import send_tickets             # tickets reminder 发送 API
from app.routers import tracking                 # Morning Pickup guest tracking page
from app.routers import order_log
from app.routers import orders
from app.routers import users
from app.routers import shortlink
from app.routers import booking_notes
from app.routers import messages
from app.routers import settings_teams
from app.routers import broadcasting_log
from app.routers import bug_reports
from app.routers import sales_report
from app.routers import ops_summary
from app.routers import promotion_stats

logger = logging.getLogger(__name__)
LA_TZ = pytz.timezone("America/Los_Angeles")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    # ── APScheduler ───────────────────────────────────────────────────────────
    scheduler = AsyncIOScheduler(timezone=LA_TZ)

    # Daily report: 11:59 PM LA time every day
    from app.services.daily_report import send_daily_report
    scheduler.add_job(
        send_daily_report,
        trigger=CronTrigger(hour=23, minute=59, timezone=LA_TZ),
        id="daily_report",
        name="NPE Daily Operations Report",
        replace_existing=True,
        misfire_grace_time=300,   # 5-minute grace window
    )

    # Existing email queue processor: every 5 minutes
    from app.services.scheduler import process_queue
    scheduler.add_job(
        process_queue,
        trigger=CronTrigger(minute="*/5", timezone=LA_TZ),
        id="process_queue",
        name="Email Queue Processor",
        replace_existing=True,
        misfire_grace_time=60,
    )

    scheduler.start()
    logger.info("APScheduler started — daily report at 23:59 LA, queue every 5 min")

    yield

    scheduler.shutdown(wait=False)
    logger.info("APScheduler stopped")


app = FastAPI(
    title="NPE Confirmation Service",
    description="National Park Express — Booking & Notification Platform",
    version="2.0.0",
    lifespan=lifespan
)

# ── Docs IP Whitelist ─────────────────────────────────────────────────────────
_raw_ips = os.getenv("DOCS_ALLOWED_IPS", "")
DOCS_ALLOWED_IPS = {ip.strip() for ip in _raw_ips.split(",") if ip.strip()}

@app.middleware("http")
async def protect_docs(request: Request, call_next):
    if request.url.path in ("/docs", "/redoc", "/openapi.json"):
        forwarded = request.headers.get("x-forwarded-for", "")
        client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "")
        if client_ip not in DOCS_ALLOWED_IPS:
            return JSONResponse(status_code=404, content={"detail": "Not found"})
    return await call_next(request)
# ─────────────────────────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router,             prefix="/auth",                   tags=["auth"])
app.include_router(admin.router,            prefix="/admin",                  tags=["admin"])
app.include_router(bookings.router,         prefix="/api/bookings",           tags=["bookings"])
app.include_router(notifications.router,    prefix="/api/notifications",      tags=["notifications"])
app.include_router(promotions.router,       prefix="/api/promotions",         tags=["promotions"])
app.include_router(send_tickets.router,     prefix="/api/tickets-reminder",   tags=["tickets-reminder"])
app.include_router(webhook.router,          prefix="/webhook",                tags=["webhook"])
app.include_router(guest.router,                                              tags=["guest"])
app.include_router(send.router)
app.include_router(pickup_locations.router, prefix="/api/pickup-locations",   tags=["pickup_locations"])
app.include_router(tracking.router,                                           tags=["tracking"])
app.include_router(order_log.router)
app.include_router(orders.router)
app.include_router(users.router)
app.include_router(shortlink.router)
app.include_router(booking_notes.router, tags=["booking_notes"])
app.include_router(messages.router, tags=["messages"])
app.include_router(settings_teams.router)
app.include_router(broadcasting_log.router)
app.include_router(bug_reports.router)
app.include_router(sales_report.router)
app.include_router(ops_summary.router)
app.include_router(promotion_stats.router)

@app.get("/")
def home():
    return {"status": "NPE Confirmation Service v2.0"}

@app.get("/health")
def health():
    return {"status": "ok"}

# ── Manual trigger endpoint (for testing) ────────────────────────────────────
@app.post("/api/admin/trigger-daily-report")
async def trigger_daily_report(_user=None):
    """Manually trigger the daily report — for testing only."""
    from app.services.daily_report import send_daily_report
    asyncio.create_task(send_daily_report())
    return {"status": "triggered"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
