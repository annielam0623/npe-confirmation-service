"""
app/routers/template_settings.py

GET  /admin/settings/templates          — page (admin/superadmin only)
GET  /api/template-settings             — return all tmpl__ keys as JSON
POST /api/template-settings/save        — save one key
"""
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import require_admin
from app.models import AdminUser
from app.services.template_copy import invalidate_cache

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ── Page ──────────────────────────────────────────────────────────────────────
@router.get("/admin/settings/templates", response_class=HTMLResponse)
async def template_settings_page(
    request: Request,
    current_user: AdminUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return templates.TemplateResponse(
        "admin/settings_templates.html",
        {
            "request": request,
            "current_user": current_user,
            "active_page": "settings_templates",
        },
    )


# ── API: list all template keys ───────────────────────────────────────────────
@router.get("/api/template-settings")
async def list_template_settings(
    current_user: AdminUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text("SELECT key, value, label FROM settings WHERE key LIKE 'tmpl__%' ORDER BY key")
    )
    rows = result.fetchall()
    return [{"key": r[0], "value": r[1], "label": r[2]} for r in rows]


# ── API: save one key ─────────────────────────────────────────────────────────
@router.post("/api/template-settings/save")
async def save_template_setting(
    request: Request,
    current_user: AdminUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    body = await request.json()
    key   = str(body.get("key", "")).strip()
    value = str(body.get("value", ""))

    if not key.startswith("tmpl__"):
        raise HTTPException(status_code=400, detail="Invalid key prefix")

    await db.execute(
        text("""
            UPDATE settings SET value = :v, updated_at = NOW()
            WHERE key = :k
        """),
        {"v": value, "k": key},
    )
    await db.commit()
    invalidate_cache(key)

    return {"ok": True, "key": key}
