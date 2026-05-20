# app/routers/shortlink.py
"""
GET /c/{code}  →  redirect to target URL
No auth required — this is a guest-facing endpoint.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.short_links import resolve_short_link

router = APIRouter()

_NO_CACHE = {"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}


@router.get("/c/{code}")
async def redirect_short_link(code: str, db: AsyncSession = Depends(get_db)):
    target = await resolve_short_link(db, code)

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
            headers=_NO_CACHE,
        )

    return RedirectResponse(url=target.strip(), status_code=302, headers=_NO_CACHE)
