"""
app/routers/tracking.py

Morning Pickup guest-facing tracking page.
Migrated from WordPress Van Tracking Page.

Routes:
  GET  /tracking          → render guest tracking page (Samsara link + I'm Here button)
  POST /tracking/checkin  → record check-in, redirect back to tracking page
"""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlencode, quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

LA = ZoneInfo("America/Los_Angeles")

# ── Van registry ──────────────────────────────────────────────────────────────
# Migrated from WordPress Morning - Van Tracking Page.txt
# key = bus number string, value = Samsara public viewer URL
# Tracking window: 4:00 AM – 7:00 AM LA time (matches WordPress)

TRACKING_WINDOW_START = (4, 0)   # 4:00 AM
TRACKING_WINDOW_END   = (19, 0)  # 7:00 PM

VANS: dict[str, str] = {
    "768":  "https://cloud.samsara.com/o/7070/fleet/viewer/hBJOM3WXRp5zRit3mk6Z",
    "956":  "https://cloud.samsara.com/o/7070/fleet/viewer/V9q6RNKODmvjlVYA7FGz",
    "1056": "https://cloud.samsara.com/o/7070/fleet/viewer/nkYw6c2xsHP3LojmRjBL",
    "1156": "https://cloud.samsara.com/o/7070/fleet/viewer/akAUuYduUfTfV4lvcjpb",
    "1328": "https://cloud.samsara.com/o/7070/fleet/viewer/goH3K1fDHFbkMykfJY3I",
    "1456": "https://cloud.samsara.com/o/7070/fleet/viewer/uXjJnH4d5EcpBRkCr8af",
    "1556": "https://cloud.samsara.com/o/7070/fleet/viewer/1XBLdXJdR8k06pJ53naj",
    "1640": "https://cloud.samsara.com/o/7070/fleet/viewer/F7BsWcqUWrdUoEXOaLLI",
    "1641": "https://cloud.samsara.com/o/7070/fleet/viewer/ZfgqDRyv9EAab9gOSoAs",
    "1656": "https://cloud.samsara.com/o/7070/fleet/viewer/YYhbUrzflia7CxiKxyXU",
    "1724": "https://cloud.samsara.com/o/7070/fleet/viewer/OW05oaCNHtH8MGFFhzos",
    "1725": "https://cloud.samsara.com/o/7070/fleet/viewer/cbmfIuhOykDGadKhX1dx",
    "1756": "https://cloud.samsara.com/o/7070/fleet/viewer/N8SgEK3Vr0beXGKsssa1",
    "1840": "https://cloud.samsara.com/o/7070/fleet/viewer/7Oes9ZccXyatsIdVPkoF",
    "1841": "https://cloud.samsara.com/o/7070/fleet/viewer/AGh0WixXpeXZKav8KDT1",
    "1855": "https://cloud.samsara.com/o/7070/fleet/viewer/wjOpcvjlfZXwUXm344Sm",
    "1888": "https://cloud.samsara.com/o/7070/fleet/viewer/XmwfBvnyq9qmawnfjetN",
    "1955": "https://cloud.samsara.com/o/7070/fleet/viewer/kk6O17d9EBiONfmd949Y",
    "1956": "https://cloud.samsara.com/o/7070/fleet/viewer/qQ8lTyZo00yeSU5YTtXQ",
    "1957": "https://cloud.samsara.com/o/7070/fleet/viewer/sZFQLy8I1DPhGQdB2BCB",
    "1960": "https://cloud.samsara.com/o/7070/fleet/viewer/6XEWYwpLpVsqkBCbAHKn",
    "2016": "https://cloud.samsara.com/o/7070/fleet/viewer/W0InKh9Iv30UYqA1a0SS",
    "2017": "https://cloud.samsara.com/o/7070/fleet/viewer/gmLzXfn9Uiaqh7ndbHhG",
    "2056": "https://cloud.samsara.com/o/7070/fleet/viewer/69uMXPrCTA5GYjuYLvO2",
    "2355": "https://cloud.samsara.com/o/7070/fleet/viewer/rWzR6InMpPKpBlPuZOua",
    "2356": "https://cloud.samsara.com/o/7070/fleet/viewer/LonCsM1Ou8N0zdhs40Vw",
    "2357": "https://cloud.samsara.com/o/7070/fleet/viewer/iueLbwyOpFYYyPDCULt5",
    "2415": "https://cloud.samsara.com/o/7070/fleet/viewer/kttjdEWxQUSDVinxYESp",
    "2456": "https://cloud.samsara.com/o/7070/fleet/viewer/z0CMcyl1VF12C9EDEQQw",
    "2457": "https://cloud.samsara.com/o/7070/fleet/viewer/fuUvBmdMqqJtkBgymMLa",
    "2555": "https://cloud.samsara.com/o/7070/fleet/viewer/QM6uFqSeVb7hfoHorRVf",
    "2556": "https://cloud.samsara.com/o/7070/fleet/viewer/SFJ9PB8vGvfDsfs7poO7",
    "2621": "https://cloud.samsara.com/o/7070/fleet/viewer/jmjapn0e5gTIOvpW6piy",
    "2622": "https://cloud.samsara.com/o/7070/fleet/viewer/RLXWsocmRjVGkbiPBf8L",
    "2655": "https://cloud.samsara.com/o/7070/fleet/viewer/hsaxxifQPl9xqpIjrb54",
    "2656": "https://cloud.samsara.com/o/7070/fleet/viewer/yBP18kSSqymT4ifNITVE",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _window_status(now_la: datetime) -> str:
    """Return 'before' | 'in' | 'after' relative to tracking window."""
    total = now_la.hour * 60 + now_la.minute
    start = TRACKING_WINDOW_START[0] * 60 + TRACKING_WINDOW_START[1]
    end   = TRACKING_WINDOW_END[0]   * 60 + TRACKING_WINDOW_END[1]
    if total < start:
        return "before"
    if total < end:
        return "in"
    return "after"


async def _already_checked_in(db: AsyncSession, order_number: str, today: str) -> bool:
    if not order_number or order_number == "N/A":
        return False
    from datetime import datetime
    window_start = datetime.strptime(f"{today} 04:00:00", "%Y-%m-%d %H:%M:%S").replace(tzinfo=LA)
    window_end   = datetime.strptime(f"{today} 16:00:00", "%Y-%m-%d %H:%M:%S").replace(tzinfo=LA)
    result = await db.execute(
        text("""
            SELECT id FROM checkin_log
             WHERE order_number = :order
               AND checkin_time >= :window_start
               AND checkin_time <  :window_end
        """),
        {
            "order":        order_number,
            "window_start": window_start,
            "window_end":   window_end,
        },
    )
    return result.first() is not None


# ── GET /tracking ─────────────────────────────────────────────────────────────

@router.get("/tracking", response_class=HTMLResponse)
async def tracking_page(
    request: Request,
    van: str = "",
    order: str = "N/A",
    name: str = "",
    phone: str = "",
    agent: str = "",
    db: AsyncSession = Depends(get_db),
):
    van_id      = van.strip()
    samsara_url = VANS.get(van_id)

    # Unknown van — show generic error
    if not samsara_url:
        return templates.TemplateResponse(
            "guest/tracking.html",
            {
                "request":      request,
                "van_id":       van_id,
                "van_name":     f"Bus #{van_id}" if van_id else "Unknown",
                "order_number": order,
                "customer_name": name,
                "phone":        phone,
                "agent_name":   agent,
                "window":       "unknown",
                "samsara_url":  "",
                "already_checked_in": False,
                "hours_label":  "4:00 AM – 7:00 AM",
            },
        )

    now_la  = datetime.now(LA)
    today   = now_la.strftime("%Y-%m-%d")
    window  = _window_status(now_la)

    # No order + in window → redirect straight to Samsara (staff/driver use)
    if window == "in" and (not order or order == "N/A"):
        return RedirectResponse(samsara_url)

    already_checked = await _already_checked_in(db, order, today) if order != "N/A" else False

    return templates.TemplateResponse(
        "guest/tracking.html",
        {
            "request":           request,
            "van_id":            van_id,
            "van_name":          f"Bus #{van_id}",
            "order_number":      order,
            "customer_name":     name,
            "phone":             phone,
            "agent_name":        agent,
            "window":            window,      # "before" | "in" | "after"
            "samsara_url":       samsara_url,
            "already_checked_in": already_checked,
            "hours_label":       "4:00 AM – 7:00 AM",
        },
    )


# ── POST /tracking/checkin ────────────────────────────────────────────────────

@router.post("/tracking/checkin")
async def tracking_checkin(
    van_id:        str = Form(""),
    order_number:  str = Form(""),
    customer_name: str = Form(""),
    phone:         str = Form(""),
    agent_name:    str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """
    Record guest check-in.
    De-duplicates: one check-in per order per day (4AM–4PM LA window).
    Redirects back to the tracking page so guest sees the confirmed state.
    """
    now_la = datetime.now(LA)
    today  = now_la.strftime("%Y-%m-%d")

    already = await _already_checked_in(db, order_number, today)
    if not already and order_number and order_number != "N/A":
        await db.execute(
            text("""
                INSERT INTO checkin_log
                    (van_id, order_number, customer_name, phone, agent_name, checkin_time, module)
                VALUES
                    (:van_id, :order, :name, :phone, :agent, NOW(), 'morning_pickup')
            """),
            {
                "van_id": van_id,
                "order":  order_number,
                "name":   customer_name,
                "phone":  phone,
                "agent":  agent_name,
            },
        )
        await db.commit()
        print(f"[tracking/checkin] order={order_number} van={van_id} checked in")
    else:
        print(f"[tracking/checkin] order={order_number} already checked in, skipped")

    # Redirect back to tracking page with same params
    params = urlencode({
        "van":   van_id,
        "order": order_number,
        "name":  customer_name,
        "phone": phone,
        "agent": agent_name,
    })
    return RedirectResponse(f"/tracking?{params}", status_code=303)


