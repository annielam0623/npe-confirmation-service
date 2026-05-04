from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import uvicorn

from app.database import init_db
from app.routers import auth, admin, bookings, notifications, tickets, guest, webhook
from app.routers.send import router as send_router
from app.routers import send

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

app.include_router(auth.router,          prefix="/auth",              tags=["auth"])
app.include_router(admin.router,         prefix="/admin",             tags=["admin"])
app.include_router(bookings.router,      prefix="/api/bookings",      tags=["bookings"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])
app.include_router(tickets.router,       prefix="/api/tickets",       tags=["tickets"])
app.include_router(webhook.router,       prefix="/webhook",           tags=["webhook"])
app.include_router(guest.router,                                      tags=["guest"])
app.include_router(send.router)

@app.get("/")
def home():
    return {"status": "NPE Confirmation Service v2.0", "docs": "/docs"}

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
