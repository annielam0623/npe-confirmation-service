# app/routers/shortlink.py
"""
GET /c/{code}  →  redirect to target URL
No auth required — this is a guest-facing endpoint.
"""

from fastapi import APIRouter
from fastapi.responses import RedirectResponse, HTMLResponse
from app.services.short_links import resolve_short_link

router = APIRouter()


@router.get("/c/{code}")
async def redirect_short_link(code: str):
    target = resolve_short_link(code)

    if not target:
        return HTMLResponse(
            content="""
            <html>
            <head><title>Link Expired</title></head>
            <body style="font-family:sans-serif;text-align:center;padding:60px;color:#555">
                <h2>This link has expired or is invalid.</h2>
                <p>Please contact NPE if you need assistance.</p>
                <p><a href="tel:702-948-4190" style="color:#1a3a5c">702-948-4190</a></p>
            </body>
            </html>
            """,
            status_code=410,
        )

    return RedirectResponse(url=target, status_code=302)
