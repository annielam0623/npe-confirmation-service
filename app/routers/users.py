"""
app/routers/users.py
User management: list users, generate invite link, deactivate/reactivate,
team assignment, display name editing, and public registration for invited staff.
Admin only (except /register/{token} which is public).
"""

import secrets
import os

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel
from typing import List

from app.auth import hash_password, require_admin, require_superadmin
from app.database import get_db
from app.models import AdminUser, Team, UserTeam

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ── GET /admin/settings/users ─────────────────────────────────────────────────
@router.get("/admin/settings/users", response_class=HTMLResponse)
async def settings_users_page(
    request: Request,
    current_user: AdminUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AdminUser).order_by(AdminUser.id))
    users = result.scalars().all()

    # all teams
    teams_result = await db.execute(select(Team).order_by(Team.id))
    teams = teams_result.scalars().all()

    # team assignments per user  {user_id: [team_id, ...]}
    ut_result = await db.execute(select(UserTeam))
    user_teams_map: dict[int, list[int]] = {}
    for ut in ut_result.scalars().all():
        user_teams_map.setdefault(ut.user_id, []).append(ut.team_id)

    # team lookup {team_id: team}
    teams_by_id = {t.id: t for t in teams}

    return templates.TemplateResponse(
        "admin/settings_users.html",
        {
            "request": request,
            "current_user": current_user,
            "users": users,
            "teams": teams,
            "user_teams_map": user_teams_map,
            "teams_by_id": teams_by_id,
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
        hashed_password="",
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


# ── PUT /api/users/{user_id}/teams — replace team assignments ─────────────────
class TeamAssignment(BaseModel):
    team_ids: List[int]

@router.put("/api/users/{user_id}/teams")
async def update_user_teams(
    user_id: int,
    payload: TeamAssignment,
    current_user: AdminUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # verify user exists
    result = await db.execute(select(AdminUser).filter(AdminUser.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # delete existing assignments
    existing = await db.execute(select(UserTeam).filter(UserTeam.user_id == user_id))
    for ut in existing.scalars().all():
        await db.delete(ut)

    # insert new assignments
    for team_id in payload.team_ids:
        db.add(UserTeam(user_id=user_id, team_id=team_id))

    await db.commit()
    return JSONResponse({"ok": True})


# ── PUT /api/users/{user_id}/display-name ─────────────────────────────────────
class DisplayNameUpdate(BaseModel):
    display_name: str

@router.put("/api/users/{user_id}/display-name")
async def update_display_name(
    user_id: int,
    payload: DisplayNameUpdate,
    current_user: AdminUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AdminUser).filter(AdminUser.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    name = payload.display_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Display name cannot be empty")

    user.display_name = name
    await db.commit()
    return JSONResponse({"ok": True, "display_name": name})


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




# ── POST /admin/settings/users/{user_id}/role — superadmin only ───────────────
@router.post("/admin/settings/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    request: Request,
    current_user: AdminUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    body = await request.json()
    new_role = body.get("role", "").strip()
    if new_role not in ("staff", "admin"):
        raise HTTPException(status_code=400, detail="Role must be 'staff' or 'admin'")

    result = await db.execute(select(AdminUser).where(AdminUser.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.username == current_user.username:
        raise HTTPException(status_code=400, detail="Cannot change your own role")
    if user.role == "superadmin":
        raise HTTPException(status_code=400, detail="Cannot change superadmin role")

    user.role = new_role
    await db.commit()
    return JSONResponse({"ok": True, "role": new_role})

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
    initials: str = Form(...),
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

    user.username     = username.strip()
    user.initials     = initials.upper().strip()
    user.display_name = username.strip()   # default display_name = username
    user.hashed_password = hash_password(password)
    user.invite_used  = True
    user.is_active    = True
    await db.commit()

    return RedirectResponse("/auth/login?registered=1", status_code=303)
