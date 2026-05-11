"""
app/routers/users.py
User management: list users, generate invite link, deactivate/reactivate,
and the public registration page for invited staff.
Admin only (except /register/{token} which is public).
"""

import secrets
import os


from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.auth import hash_password, require_admin
from app.database import get_db
from app.models import AdminUser

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
print("CWD:", os.getcwd())
print("Templates dir exists:", os.path.exists("app/templates/admin/base.html"))

# ── GET /admin/settings/users ─────────────────────────────────────────────────
@router.get("/admin/settings/users", response_class=HTMLResponse)
async def settings_users_page(
    request: Request,
    current_user: AdminUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AdminUser).order_by(AdminUser.id))
    users = result.scalars().all()
    return templates.TemplateResponse(
        "admin/settings_users.html",
        {
            "request": request,
            "current_user": current_user,
            "users": users,
            "active_page": "settings_users",
        },
    )


# ── POST /admin/settings/users/invite ─────────────────────────────────────────
@router.post("/admin/settings/users/invite")
async def generate_invite(
    request: Request,
    current_user: AdminUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    token = secrets.token_urlsafe(32)

    placeholder = AdminUser(
        username=f"__pending_{token[:8]}",
        password_hash="",
        role="staff",
        invite_token=token,
        invite_used=False,
        is_active=False,
        created_by=current_user.username,
    )
    db.add(placeholder)
    await db.commit()

    base_url = str(request.base_url).rstrip("/")
    invite_url = f"{base_url}/register/{token}"
    return JSONResponse({"invite_url": invite_url})


# ── POST /admin/settings/users/{user_id}/deactivate ──────────────────────────
@router.post("/admin/settings/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: int,
    current_user: AdminUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AdminUser).filter(AdminUser.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.username == current_user.username:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
    user.is_active = False
    await db.commit()
    return JSONResponse({"ok": True})


# ── POST /admin/settings/users/{user_id}/reactivate ──────────────────────────
@router.post("/admin/settings/users/{user_id}/reactivate")
async def reactivate_user(
    user_id: int,
    current_user: AdminUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AdminUser).filter(AdminUser.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = True
    await db.commit()
    return JSONResponse({"ok": True})


# ── DELETE /admin/settings/users/{user_id} ────────────────────────────────────
@router.delete("/admin/settings/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: AdminUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AdminUser).filter(AdminUser.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.username == current_user.username:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    await db.delete(user)
    await db.commit()
    return JSONResponse({"ok": True})


# ── GET /register/{token} — public registration page ─────────────────────────
@router.get("/register/{token}", response_class=HTMLResponse)
async def register_page(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AdminUser).filter(
            AdminUser.invite_token == token,
            AdminUser.invite_used == False,
        )
    )
    user = result.scalars().first()
    if not user:
        return HTMLResponse("<h2>This invite link is invalid or has already been used.</h2>", status_code=400)

    return templates.TemplateResponse(
        "admin/register.html",
        {"request": request, "token": token, "error": None},
    )


# ── POST /register/{token} — complete registration ────────────────────────────
@router.post("/register/{token}", response_class=HTMLResponse)
async def register_submit(
    token: str,
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AdminUser).filter(
            AdminUser.invite_token == token,
            AdminUser.invite_used == False,
        )
    )
    user = result.scalars().first()
    if not user:
        return HTMLResponse("<h2>This invite link is invalid or has already been used.</h2>", status_code=400)

    error = None
    if len(username.strip()) < 3:
        error = "Username must be at least 3 characters."
    elif password != confirm_password:
        error = "Passwords do not match."
    elif len(password) < 8:
        error = "Password must be at least 8 characters."
    else:
        dup = await db.execute(select(AdminUser).filter(AdminUser.username == username))
        existing = dup.scalars().first()
        if existing and existing.id != user.id:
            error = "That username is already taken. Please choose another."

    if error:
        return templates.TemplateResponse(
            "admin/register.html",
            {"request": request, "token": token, "error": error},
        )

    user.username = username.strip()
    user.password_hash = hash_password(password)
    user.invite_used = True
    user.is_active = True
    await db.commit()

    return RedirectResponse("/admin/login?registered=1", status_code=303)
