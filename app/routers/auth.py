"""
app/routers/auth.py
Login / logout routes.
All auth utility functions live in app/auth.py.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import (
    COOKIE_NAME,
    TOKEN_EXPIRE_HOURS,
    authenticate_user,
    create_access_token,
    decode_token,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ── GET /auth/login ───────────────────────────────────────────────────────────
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if token and decode_token(token):
        return RedirectResponse(url="/admin/dashboard", status_code=302)
    registered = request.query_params.get("registered") == "1"
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": None, "registered": registered},
    )


# ── POST /auth/login ──────────────────────────────────────────────────────────
@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))

    user = await authenticate_user(username, password, db)
    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password", "registered": False},
            status_code=400,
        )

    token = create_access_token({"sub": user.username, "role": user.role})
    response = RedirectResponse(url="/admin/dashboard", status_code=302)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=TOKEN_EXPIRE_HOURS * 3600,
        samesite="lax",
    )
    return response


# ── GET /auth/logout ──────────────────────────────────────────────────────────
@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/auth/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response
