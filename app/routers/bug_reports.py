from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional
import os, httpx
from datetime import datetime, timezone

from app.database import get_db
from app.auth import require_staff

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

CLICKUP_TOKEN   = os.getenv("CLICKUP_TOKEN", "")
CLICKUP_LIST_ID = os.getenv("CLICKUP_LIST_ID", "")

PRIORITY_MAP = {"urgent": 1, "high": 2, "normal": 3, "low": 4}
MODULE_LABELS = {
    "tour":    "Tour Confirmation",
    "morning": "Morning Pickup",
    "tickets": "Tickets Reminder",
    "general": "General",
}

# ── Page ──────────────────────────────────────────────────────────────────────

@router.get("/admin/system/bug-reports", response_class=HTMLResponse)
async def bug_reports_page(request: Request, current_user=Depends(require_staff)):
    return templates.TemplateResponse("admin/bug_reports.html", {
        "request": request,
        "current_user": current_user,
        "active_page": "bug_reports",
    })

# ── API: list ─────────────────────────────────────────────────────────────────

@router.get("/api/bug-reports")
async def list_bug_reports(
    status: Optional[str]   = None,
    priority: Optional[str] = None,
    module: Optional[str]   = None,
    current_user=Depends(require_staff),
    db=Depends(get_db),
):
    conditions = ["1=1"]
    params: list = []
    i = 1
    if status:
        conditions.append(f"status = ${i}"); params.append(status); i += 1
    if priority:
        conditions.append(f"priority = ${i}"); params.append(priority); i += 1
    if module:
        conditions.append(f"module = ${i}"); params.append(module); i += 1

    where = " AND ".join(conditions)
    rows = await db.fetch(
        f"SELECT * FROM bug_reports WHERE {where} ORDER BY created_at DESC",
        *params,
    )
    return [dict(r) for r in rows]

# ── API: create ───────────────────────────────────────────────────────────────

class BugReportIn(BaseModel):
    title:        str
    description:  Optional[str] = None
    module:       str = "general"
    priority:     str = "normal"
    order_number: Optional[str] = None

@router.post("/api/bug-reports")
async def create_bug_report(
    payload: BugReportIn,
    current_user=Depends(require_staff),
    db=Depends(get_db),
):
    submitted_by = current_user.display_name or current_user.username

    row = await db.fetchrow(
        """INSERT INTO bug_reports
               (title, description, module, priority, status, order_number, submitted_by)
           VALUES ($1,$2,$3,$4,'open',$5,$6)
           RETURNING *""",
        payload.title,
        payload.description,
        payload.module,
        payload.priority,
        payload.order_number,
        submitted_by,
    )
    bug = dict(row)

    # ── Push to ClickUp (best-effort, non-blocking) ───────────────────────────
    if CLICKUP_TOKEN and CLICKUP_LIST_ID:
        try:
            cu_priority = PRIORITY_MAP.get(payload.priority, 3)
            tags_text = f"[{MODULE_LABELS.get(payload.module, payload.module)}]"
            body_text = payload.description or ""
            if payload.order_number:
                body_text += f"\n\nOrder#: {payload.order_number}"
            body_text += f"\n\nSubmitted by: {submitted_by}"

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"https://api.clickup.com/api/v2/list/{CLICKUP_LIST_ID}/task",
                    headers={"Authorization": CLICKUP_TOKEN, "Content-Type": "application/json"},
                    json={
                        "name": f"{tags_text} {payload.title}",
                        "description": body_text,
                        "priority": cu_priority,
                        "status": "new",
                    },
                )
                if resp.status_code == 200:
                    task_id = resp.json().get("id")
                    if task_id:
                        await db.execute(
                            "UPDATE bug_reports SET clickup_task_id=$1 WHERE id=$2",
                            task_id, bug["id"],
                        )
                        bug["clickup_task_id"] = task_id
        except Exception:
            pass  # ClickUp 推送失败不影响本地保存

    return bug

# ── API: update status ────────────────────────────────────────────────────────

class StatusUpdate(BaseModel):
    status: str

@router.patch("/api/bug-reports/{bug_id}/status")
async def update_bug_status(
    bug_id: int,
    payload: StatusUpdate,
    current_user=Depends(require_staff),
    db=Depends(get_db),
):
    if payload.status not in ("open", "in_progress", "fixed"):
        raise HTTPException(400, "Invalid status")
    row = await db.fetchrow(
        "UPDATE bug_reports SET status=$1, updated_at=NOW() WHERE id=$2 RETURNING *",
        payload.status, bug_id,
    )
    if not row:
        raise HTTPException(404, "Bug not found")
    return dict(row)
