from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import uvicorn
import os

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(
    title="NPE Confirmation Service",
    description="National Park Express — Booking & Notification Platform",
    version="2.0.0",
    lifespan=lifespan
)

# ── Docs IP Whitelist ─────────────────────────────────────────────────────────
# Railway 环境变量 DOCS_ALLOWED_IPS 设置允许访问 /docs 的 IP，逗号分隔
# 例如：DOCS_ALLOWED_IPS=1.2.3.4,5.6.7.8
# 留空或不设置 → /docs 对所有人关闭（生产上线后用）
_raw_ips = os.getenv("DOCS_ALLOWED_IPS", "")
DOCS_ALLOWED_IPS = {ip.strip() for ip in _raw_ips.split(",") if ip.strip()}

@app.middleware("http")
async def protect_docs(request: Request, call_next):
    if request.url.path in ("/docs", "/redoc", "/openapi.json"):
        # Railway 经过代理，真实 IP 在 x-forwarded-for 第一位
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

@app.get("/")
def home():
    return {"status": "NPE Confirmation Service v2.0"}

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
