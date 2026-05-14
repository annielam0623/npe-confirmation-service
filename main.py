from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import uvicorn

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

@app.get("/")
def home():
    return {"status": "NPE Confirmation Service v2.0", "docs": "/docs"}

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
