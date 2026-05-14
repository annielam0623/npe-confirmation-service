"""
app/routers/settings_teams.py
Team management: list, create, update, delete.
Admin only.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from pydantic import BaseModel

from app.auth import require_admin
from app.database import get_db
from app.models import AdminUser, Team, UserTeam

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class TeamCreate(BaseModel):
    name: str
    color: str = "#4285F4"
    description: str = ""

class TeamUpdate(BaseModel):
    name: str
    color: str = "#4285F4"
    description: str = ""


# ── GET /admin/settings/teams ─────────────────────────────────────────────────

@router.get("/admin/settings/teams", response_class=HTMLResponse)
async def settings_teams_page(
    request: Request,
    current_user: AdminUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Team).order_by(Team.id))
    teams = result.scalars().all()

    # member count per team
    counts_result = await db.execute(
        select(UserTeam.team_id, func.count(UserTeam.user_id).label("cnt"))
        .group_by(UserTeam.team_id)
    )
    counts = {row.team_id: row.cnt for row in counts_result}

    teams_data = [
        {
            "id": t.id,
            "name": t.name,
            "color": t.color,
            "description": getattr(t, "description", ""),
            "member_count": counts.get(t.id, 0),
            "created_at": t.created_at,
        }
        for t in teams
    ]

    return templates.TemplateResponse(
        "admin/settings_teams.html",
        {
            "request": request,
            "current_user": current_user,
            "teams": teams_data,
            "active_page": "settings_teams",
        },
    )


# ── POST /api/teams — create ──────────────────────────────────────────────────

@router.post("/api/teams")
async def create_team(
    payload: TeamCreate,
    current_user: AdminUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Team name is required")

    # duplicate check
    dup = await db.execute(select(Team).filter(Team.name == name))
    if dup.scalars().first():
        raise HTTPException(status_code=400, detail="A team with that name already exists")

    team = Team(
        name=name,
        color=payload.color or "#4285F4",
    )
    # store description in a notes-style field if column exists, else skip
    if hasattr(team, "description"):
        team.description = payload.description

    db.add(team)
    await db.commit()
    await db.refresh(team)
    return JSONResponse({"ok": True, "id": team.id, "name": team.name, "color": team.color})


# ── PUT /api/teams/{team_id} — update ────────────────────────────────────────

@router.put("/api/teams/{team_id}")
async def update_team(
    team_id: int,
    payload: TeamUpdate,
    current_user: AdminUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Team).filter(Team.id == team_id))
    team = result.scalars().first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Team name is required")

    # duplicate check (exclude self)
    dup = await db.execute(select(Team).filter(Team.name == name, Team.id != team_id))
    if dup.scalars().first():
        raise HTTPException(status_code=400, detail="A team with that name already exists")

    team.name  = name
    team.color = payload.color or "#4285F4"
    if hasattr(team, "description"):
        team.description = payload.description

    await db.commit()
    return JSONResponse({"ok": True})


# ── DELETE /api/teams/{team_id} — delete ─────────────────────────────────────

@router.delete("/api/teams/{team_id}")
async def delete_team(
    team_id: int,
    current_user: AdminUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Team).filter(Team.id == team_id))
    team = result.scalars().first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    await db.delete(team)
    await db.commit()
    return JSONResponse({"ok": True})
