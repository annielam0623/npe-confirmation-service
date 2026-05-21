from fastapi import APIRouter, Request, Depends, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import os, httpx

from app.auth import require_staff

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

CLICKUP_TOKEN   = os.getenv("CLICKUP_TOKEN", "")
CLICKUP_LIST_ID = os.getenv("CLICKUP_LIST_ID", "901814891310")

HEADERS = {"Authorization": CLICKUP_TOKEN}

# ── Page ──────────────────────────────────────────────────────────────────────

@router.get("/admin/system/bug-reports", response_class=HTMLResponse)
async def bug_reports_page(request: Request, current_user=Depends(require_staff)):
    return templates.TemplateResponse("admin/bug_reports.html", {
        "request": request,
        "current_user": current_user,
        "active_page": "bug_reports",
    })

# ── Proxy: GET tasks ──────────────────────────────────────────────────────────

@router.get("/api/bug-reports/tasks")
async def get_tasks(current_user=Depends(require_staff)):
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"https://api.clickup.com/api/v2/list/{CLICKUP_LIST_ID}/task"
            "?include_closed=true&subtasks=true",
            headers=HEADERS,
        )
    return JSONResponse(content=resp.json(), status_code=resp.status_code)

# ── Proxy: POST task (new bug) ────────────────────────────────────────────────

@router.post("/api/bug-reports/tasks")
async def create_task(request: Request, current_user=Depends(require_staff)):
    body = await request.json()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"https://api.clickup.com/api/v2/list/{CLICKUP_LIST_ID}/task",
            headers={**HEADERS, "Content-Type": "application/json"},
            json=body,
        )
    return JSONResponse(content=resp.json(), status_code=resp.status_code)

# ── Proxy: GET comments ───────────────────────────────────────────────────────

@router.get("/api/bug-reports/task/{task_id}/comment")
async def get_comments(task_id: str, current_user=Depends(require_staff)):
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"https://api.clickup.com/api/v2/task/{task_id}/comment",
            headers=HEADERS,
        )
    return JSONResponse(content=resp.json(), status_code=resp.status_code)

# ── Proxy: POST comment ───────────────────────────────────────────────────────

@router.post("/api/bug-reports/task/{task_id}/comment")
async def post_comment(task_id: str, request: Request, current_user=Depends(require_staff)):
    body = await request.json()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"https://api.clickup.com/api/v2/task/{task_id}/comment",
            headers={**HEADERS, "Content-Type": "application/json"},
            json={"comment_text": body.get("comment_text", "")},
        )
    return JSONResponse(content=resp.json(), status_code=resp.status_code)

# ── Proxy: POST attachment ────────────────────────────────────────────────────

@router.post("/api/bug-reports/task/{task_id}/attachment")
async def post_attachment(task_id: str, file: UploadFile = File(...), current_user=Depends(require_staff)):
    content = await file.read()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"https://api.clickup.com/api/v2/task/{task_id}/attachment",
            headers=HEADERS,
            files={"attachment": (file.filename, content, file.content_type)},
        )
    return JSONResponse(content=resp.json(), status_code=resp.status_code)
