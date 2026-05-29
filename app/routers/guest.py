"""
app/routers/guest.py
Guest-facing confirmation form — full port from PHP tour-confirmation.php
GET  /confirm/{token}  — show form
POST /confirm/{token}  — handle submission
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text as _sql_text

from app.database import get_db
from app.models import Booking, BookingNote
from app.services.tour_config import TOUR_TYPES
from app.services.sendgrid import send_staff_notification

router = APIRouter()
BASE_URL = "https://confirm.nationalparkexpress.com"
LA = ZoneInfo("America/Los_Angeles")


async def _fetch_pickup_info(pickup_location: str, db: AsyncSession):
    """Fetch instruction, photo_url, photo_label from pickup_locations table."""
    if not pickup_location:
        return "", "", ""
    loc_res = await db.execute(_sql_text(
        "SELECT instruction, photo_url, hotel_name FROM pickup_locations WHERE hotel_name ILIKE :n LIMIT 1"
    ), {"n": f"%{pickup_location}%"})
    row = loc_res.fetchone()
    if not row:
        return "", "", f"{pickup_location} Pickup Photos"
    return (row[0] or ""), (row[1] or ""), ((row[2] or pickup_location) + " Pickup Photos")


# ── CSS ───────────────────────────────────────────────────────────────────────

GUEST_CSS = """*{box-sizing:border-box;margin:0;padding:0;}
body{background:#f0f4f8;font-family:"Helvetica Neue",Arial,sans-serif;color:#333;padding:16px;}
.gf-wrap{max-width:580px;margin:0 auto;padding:10px 0 40px;}
.gf-card{background:#fff;border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,.10);overflow:hidden;}
.gf-header{background:#1a3a5c;color:#fff;padding:22px 26px;display:flex;align-items:center;gap:20px;}
.gf-header-logo{flex-shrink:0;width:20%;}
.gf-header-logo img{width:90px;height:auto;display:block;}
.gf-header-text{flex:1;text-align:center;overflow:hidden;}
.gf-header h1{font-size:20px;margin:0 0 8px;font-weight:bold;white-space:nowrap;}
.gf-tour-badge{background:rgba(255,255,255,.15);border-radius:6px;padding:4px 14px;display:inline-block;font-size:13px;font-weight:bold;margin-bottom:8px;white-space:nowrap;}
.gf-date{font-size:17px;font-weight:bold;color:#fff;margin:0 0 4px;white-space:nowrap;}
.gf-meta{font-size:12px;color:#a8c4e0;margin:0;white-space:nowrap;}
.gf-pickup-box,.gf-fee-box{padding:16px 22px;font-size:13px;line-height:1.6;}
.gf-pickup-box{background:#eef6ff;border-bottom:1px solid #d0e6ff;}
.gf-fee-box{background:#fffbf0;border-bottom:1px solid #f0d080;}
.gf-box-title{font-weight:bold;color:#1a3a5c;margin-bottom:10px;}
.gf-fee-box .gf-box-title{color:#8a6000;}
.gf-row{display:flex;gap:10px;align-items:flex-start;margin-bottom:8px;}
.gf-row span:first-child{flex-shrink:0;width:20px;text-align:center;}
.gf-fee-box ul{padding-left:18px;} .gf-fee-box li{margin-bottom:4px;}
.gf-section{padding:18px 22px;border-bottom:1px solid #eee;}
.gf-section h2{font-size:15px;color:#1a3a5c;margin-bottom:12px;}
.gf-opt{font-weight:normal;font-size:12px;color:#aaa;}
.gf-yn-row{display:flex;gap:10px;flex-wrap:wrap;}
.gf-yn{display:flex;flex-direction:column;align-items:center;gap:6px;border:2px solid #ddd;border-radius:10px;padding:14px;cursor:pointer;flex:1;transition:all .2s;text-align:center;}
.gf-yn input{display:none;}
.gf-yn-icon{font-size:26px;} .gf-yn-label{font-size:14px;font-weight:bold;color:#333;}
.gf-yn-label small{font-weight:normal;font-size:12px;color:#888;}
.gf-yn.yes:has(input:checked){border-color:#27ae60;background:#f0fff4;}
.gf-yn.no:has(input:checked){border-color:#e74c3c;background:#fff5f5;}
.gf-yn:hover{border-color:#1a3a5c;}
.gf-hint{font-size:13px;color:#666;margin-bottom:12px;}
.gf-lunch-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;}
.gf-lunch-item{border:1px solid #e0e0e0;border-radius:10px;padding:12px;text-align:center;}
.gf-lunch-icon{font-size:26px;margin-bottom:4px;}
.gf-lunch-name{font-size:11px;font-weight:bold;color:#555;margin-bottom:8px;line-height:1.3;}
.gf-counter{display:flex;align-items:center;justify-content:center;gap:5px;}
.gf-counter button{width:28px;height:28px;border:1px solid #ccc;border-radius:6px;background:#f5f5f5;font-size:16px;cursor:pointer;}
.gf-counter button:hover{background:#ddd;}
.gf-counter input{width:36px;text-align:center;border:1px solid #ccc;border-radius:6px;padding:3px;font-size:15px;font-weight:bold;}
.gf-lunch-total{text-align:center;margin-top:10px;font-size:13px;color:#555;}
.gf-reminders{background:#f9f9f9;border-top:1px solid #eee;padding:14px 22px;font-size:13px;}
.gf-reminders ul{padding-left:18px;line-height:1.9;color:#555;}
.gf-section textarea{width:100%;border:1px solid #ddd;border-radius:8px;padding:10px;font-size:13px;resize:vertical;}
.gf-submit{padding:18px 22px;text-align:center;}
.gf-btn{width:100%;background:#1a3a5c;color:#fff;border:none;padding:15px;border-radius:10px;font-size:16px;font-weight:bold;cursor:pointer;}
.gf-btn:hover{background:#0f2440;}
.gf-small{font-size:12px;color:#888;margin-top:10px;}
.gf-error{background:#f8d7da;color:#721c24;border:1px solid #f5c6cb;border-radius:8px;padding:12px 18px;margin:10px 22px;font-size:13px;}
.gf-info{background:#d4edda;color:#155724;border-radius:8px;padding:10px 18px;margin:10px 22px;font-size:13px;}
.gf-card.gf-thanks{text-align:center;padding:40px 30px;}
.gf-thanks h1{color:#1a3a5c;margin-bottom:12px;}
.gf-thanks p{color:#555;margin-bottom:8px;line-height:1.7;}
.gf-mtlv-box{background:#f5f0ff;border:1.5px solid #b39ddb;border-radius:12px;padding:16px 18px;margin-top:4px;}
.gf-mtlv-title{font-size:14px;font-weight:bold;color:#512da8;margin-bottom:4px;}
.gf-mtlv-hint{font-size:12px;color:#7e57c2;margin-bottom:12px;}
.gf-mtlv-counter{display:flex;align-items:center;gap:10px;}
.gf-mtlv-counter button{width:34px;height:34px;border:1.5px solid #b39ddb;border-radius:8px;background:#ede7f6;font-size:20px;line-height:1;cursor:pointer;color:#512da8;font-weight:bold;}
.gf-mtlv-counter button:hover{background:#d1c4e9;}
.gf-mtlv-counter input{width:44px;text-align:center;border:1.5px solid #b39ddb;border-radius:8px;padding:4px;font-size:18px;font-weight:bold;color:#512da8;background:#fff;}
@media(max-width:440px){.gf-lunch-grid{grid-template-columns:1fr 1fr;}.gf-yn-row{flex-direction:column;}}"""


def _page(title: str, body: str) -> str:
    return (
        f'<!DOCTYPE html><html><head><meta charset="UTF-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{title}</title><style>{GUEST_CSS}</style></head><body>{body}</body></html>'
    )


def _expired() -> HTMLResponse:
    body = """<div style="display:flex;align-items:center;justify-content:center;min-height:100vh;">
    <div style="background:#fff;border-radius:16px;padding:40px;max-width:480px;text-align:center;box-shadow:0 4px 20px rgba(0,0,0,.1);">
    <div style="font-size:56px;margin-bottom:16px;">⏰</div>
    <h1 style="color:#1a3a5c;">Link Expired</h1>
    <p style="color:#555;line-height:1.7;">This confirmation link has expired or is invalid.</p>
    <p style="color:#555;line-height:1.7;">Please contact us at
    <a href="mailto:reservations@nationalparkexpress.com" style="color:#1a3a5c;">reservations@nationalparkexpress.com</a>
    or call <strong>702-948-4190</strong>.</p>
    </div></div>"""
    return HTMLResponse(_page("Link Expired", body), status_code=404)


def _thanks(booking) -> HTMLResponse:
    body = f"""<div class="gf-wrap"><div class="gf-card gf-thanks">
    <div style="font-size:56px;margin-bottom:12px;">🎉</div>
    <h1>Thank You, {booking.first_name}!</h1>
    <p>Your confirmation has been received. We look forward to seeing you on your tour!</p>
    <p style="margin-top:16px;font-size:13px;color:#888;">
    Questions? <a href="mailto:reservations@nationalparkexpress.com">reservations@nationalparkexpress.com</a>
    | 702-948-4190</p>
    </div></div>"""
    return HTMLResponse(_page("Confirmed!", body))


def _render(booking, tour_config: dict, error_msg: str = "",
            pickup_instruction: str = "", pickup_photo_url: str = "", pickup_photo_label: str = "",
            is_last_minute: bool = False) -> HTMLResponse:
    tour_date  = booking.tour_date
    date_fmt   = tour_date.strftime("%A, %B %-d, %Y") if tour_date else "—"
    qty        = int(booking.quantities or 1)
    has_lunch  = tour_config.get("has_lunch", False)
    has_beef   = tour_config.get("has_beef", False)
    mtlv_eligible = bool(getattr(booking, "mtlv_eligible", False))
    mtlv_qty_val  = getattr(booking, "mtlv_qty", None)  # None = not yet replied
    already       = booking.submitted_at and booking.confirmation != "pending"
    # v4.17.14: YES locked only when already YES; modify_req state can still click YES to cancel
    yes_locked    = booking.confirmation == "yes"
    is_modify_req = booking.confirmation == "modify_req"
    # Modify locked from 11:59 PM LA time, two days before tour date
    modify_locked = False
    if booking.tour_date:
        from datetime import timedelta
        deadline = datetime(
            booking.tour_date.year,
            booking.tour_date.month,
            booking.tour_date.day,
            23, 59, 0,
            tzinfo=LA
        ) - timedelta(days=2)  # 11:59 PM LA time, two days before tour
        if datetime.now(LA) >= deadline:
            modify_locked = True
    # v4.17.14: Count modify submissions for 2-attempt limit
    modify_count    = (booking.notes_history or "").count("] Modify requested")
    modify_maxed    = modify_count >= 2
    modify_disabled = modify_locked or modify_maxed

    # Pickup box
    ploc = booking.pickup_location or ""
    pickup_html = ""
    pickup_html = ""
    pickup_html += (
        f'<div class="gf-row"><span>📱</span>'
        f'<span>You will receive a morning reminder SMS with a check-in link and real-time vehicle tracking on the day of your tour.</span></div>'
    )
    if ploc:
        instruction_display = pickup_instruction if pickup_instruction else f"Please arrive at <strong>{ploc}</strong>"
        pickup_html += f'<div class="gf-row"><span>📍</span><span>{instruction_display}</span></div>'
    if booking.pickup_time:
        pickup_html += (
            f'<div class="gf-row"><span>⏰</span><span>Arrive by '
            f'<strong>{booking.pickup_time}</strong> for check-in. '
            f'Departs promptly — vehicle cannot wait for late arrivals.</span></div>'
        )
    if pickup_photo_url:
        pickup_html += (
            f'<div class="gf-row"><span>🗺️</span>'
            f'<a href="{pickup_photo_url}" target="_blank" style="color:#1a3a5c;">{pickup_photo_label}</a></div>'
        )

    fee_html = ""
    if tour_config.get("has_park_fee"):
        fee_html = """<div class="gf-fee-box">
        <div class="gf-box-title">ℹ️ National Park Entry Fee</div>
        <ul>
          <li><strong>Non-U.S. Residents fee (ages 16+):</strong> $100/person or $250 America the Beautiful Annual Pass (up to 4 people).</li>
          <li><strong>Legal U.S. residents:</strong> Present valid government-issued ID to waive the $100 fee.</li>
        </ul></div>"""

    banners = ""
    if error_msg:
        banners += f'<div class="gf-error">{error_msg}</div>'
    if already:
        banners += '<div class="gf-info">Response already submitted. You can update it below.</div>'

    # v4.17.14: YES button states
    if yes_locked:
        yes_btn = """<div class="gf-yn yes" style="opacity:0.5;cursor:not-allowed;border-color:#27ae60;background:#f0fff4;">
          <span class="gf-yn-icon">✅</span>
          <span class="gf-yn-label">YES<br><small>Already confirmed</small></span>
        </div>"""
    elif is_modify_req:
        yes_btn = """<label class="gf-yn yes" style="border-color:#e67e22;">
          <input type="radio" name="confirmation" value="yes" onchange="onYN(this)">
          <span class="gf-yn-icon">✅</span>
          <span class="gf-yn-label">YES<br><small style="color:#e67e22;">Cancel date change &amp; confirm original date</small></span>
        </label>"""
    else:
        yes_btn = """<label class="gf-yn yes">
          <input type="radio" name="confirmation" value="yes" onchange="onYN(this)">
          <span class="gf-yn-icon">✅</span>
          <span class="gf-yn-label">YES<br><small>I'm attending</small></span>
        </label>"""

    modify_style_attr = "cursor:not-allowed;opacity:0.5;" if modify_disabled else ""
    modify_dis_attr   = "disabled" if modify_disabled else ""
    if modify_locked:
        modify_sub = "No longer available"
    elif modify_maxed:
        modify_sub = "Max requests reached"
    else:
        from datetime import timedelta
        _deadline_day = booking.tour_date - timedelta(days=2) if booking.tour_date else None
        _deadline_str = _deadline_day.strftime("%b %-d") if _deadline_day else "2 days before tour"
        modify_sub = f"Available until {_deadline_str}, 11:59 PM"

    # Lunch section
    lunch_html = ""
    if has_lunch:
        items = [
            ("turkey", "🦃", "Turkey Sandwich", int(booking.lunch_turkey or 0)),
            ("veggie", "🥗", "Veggie Sandwich",  int(booking.lunch_veggie or 0)),
        ]
        if has_beef:
            items.append(("beef", "🥩", "Beef Sandwich", int(booking.lunch_beef or 0)))

        items_html = "".join(
            f"""<div class="gf-lunch-item">
              <div class="gf-lunch-icon">{icon}</div>
              <div class="gf-lunch-name">{name}</div>
              <div class="gf-counter">
                <button type="button" onclick="adj('{k}',-1)">−</button>
                <input type="number" name="lunch_{k}" id="c-{k}" value="{val}" min="0" max="{qty}" readonly>
                <button type="button" onclick="adj('{k}',1)">+</button>
              </div>
            </div>"""
            for k, icon, name, val in items
        )
        lunch_show = "" if (booking.confirmation == "yes" or is_last_minute) else "display:none"
        lunch_html = f"""<div class="gf-section" id="lunch-section" style="{lunch_show}">
          <h2>🥪 Lunch Selection</h2>
          <p class="gf-hint">Select for all <strong>{qty}</strong> guest(s). Total must equal your party size.</p>
          <div class="gf-lunch-grid">{items_html}</div>
          <div class="gf-lunch-total">Total: <span id="ltotal" style="font-weight:bold;">0</span> / {qty}</div>
          <p class="gf-small" style="text-align:center;margin-top:6px;">Default is Turkey Sandwich if no selection received.</p>
        </div>"""

    reminders_html = "".join(f"<li>{r}</li>" for r in (tour_config.get("extra_reminders") or []))
    reminders_html += """<li>Dress appropriately for the weather and stay hydrated.</li>
    <li>Vehicles are air-conditioned; in extreme heat, cooling may take a moment.</li>
    <li>You may bring small items like personal fans or ice packs.</li>"""

    # MTLV — Madame Tussauds ticket selection (only when mtlv_eligible)
    mtlv_html = ""
    if mtlv_eligible:
        current_mtlv = int(mtlv_qty_val) if mtlv_qty_val is not None else 0
        mtlv_locked_status = getattr(booking, "mtlv_ticket_status", None)
        mtlv_locked = mtlv_locked_status in ("sent", "cancel")
        if mtlv_locked:
            if mtlv_locked_status == "cancel":
                lock_msg = "Your Madame Tussauds ticket selection has been cancelled."
                lock_style = "color:#999;"
            else:
                lock_msg = "Your Madame Tussauds ticket selection has been confirmed and can no longer be changed."
                lock_style = "color:#2F7851;font-weight:600;"
            mtlv_html = f"""<div class="gf-section">
          <div class="gf-mtlv-box" style="opacity:0.7;">
            <div class="gf-mtlv-title">🏛️ Madame Tussauds Las Vegas Ticket</div>
            <div style="font-size:13px;{lock_style}margin-top:6px;">{lock_msg}</div>
            <input type="hidden" name="mtlv_qty" value="{current_mtlv}">
          </div>
        </div>"""
        else:
            mtlv_html = f"""<div class="gf-section">
          <div class="gf-mtlv-box">
            <div class="gf-mtlv-title">🏛️ Madame Tussauds Las Vegas Ticket</div>
            <div class="gf-mtlv-hint">Your package includes the option to add Madame Tussauds tickets. Please select the number of tickets for your party (0–{qty}). Enter 0 if you do not need any tickets.</div>
            <div class="gf-mtlv-counter">
              <button type="button" onclick="adjMtlv(-1)">−</button>
              <input type="number" name="mtlv_qty" id="c-mtlv" value="{current_mtlv}" min="0" max="{qty}" readonly>
              <button type="button" onclick="adjMtlv(1)">+</button>
              <span style="font-size:13px;color:#7e57c2;margin-left:6px;">/ {qty} guests</span>
            </div>
          </div>
        </div>"""

    # v4.17.14: min date = today + 1 day (current time + 24h)
    from datetime import timedelta
    tomorrow = (datetime.now(LA) + timedelta(days=1)).strftime("%Y-%m-%d")

    # v4.17.14: Build notes display block (yellow bg, lunch diff coloring)
    last_note = (booking.notes or "").strip()
    if last_note:
        import re as _re2
        note_display = last_note.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        # Try to colorize lunch changes: "Lunch updated: T×N V×N B×N (was T×N V×N B×N)"
        m = _re2.search(r'Lunch updated: T×(\d+) V×(\d+) B×(\d+) \(was T×(\d+) V×(\d+) B×(\d+)\)', last_note)
        if m:
            nt,nv,nb,pt,pv,pb = m.group(1),m.group(2),m.group(3),m.group(4),m.group(5),m.group(6)
            def _fmt(label, new_val, prev_val):
                if new_val == "0" and prev_val != "0":
                    return f"<span style='color:#aaa;'>{label}×{new_val}</span>"
                if new_val != prev_val:
                    return f"<span style='color:#c0392b;font-weight:500;'>{label}×{new_val}</span>"
                return f"{label}×{new_val}"
            colored = "Lunch updated: " + _fmt("T",nt,pt) + " " + _fmt("V",nv,pv) + " " + _fmt("B",nb,pb)
            colored += f" (was T×{pt} V×{pv} B×{pb})"
            prefix_m = _re2.match(r'^(\[.*?\]\s*)', last_note)
            prefix = prefix_m.group(1).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;") if prefix_m else ""
            note_display = prefix + colored
        notes_display_html = f'''<div style="background:#fffbf0;border:1px solid #f0d080;border-radius:8px;padding:12px 16px;margin-bottom:12px;">
          <div style="font-size:12px;font-weight:bold;color:#8a6000;margin-bottom:4px;">📝 Your last update</div>
          <div style="font-size:13px;color:#8a6000;">{note_display}</div>
        </div>'''
    else:
        notes_display_html = ""

    js = f"""
var partySize={qty},hasLunch={'true' if has_lunch else 'false'};
function onYN(el){{if(hasLunch){{var ls=document.getElementById('lunch-section');if(ls)ls.style.display=el.value==='yes'?'':'none';}}var rs=document.getElementById('reschedule-section');if(rs)rs.style.display='none';}}
function onModify(el){{if(hasLunch){{var ls=document.getElementById('lunch-section');if(ls)ls.style.display='none';}}var rs=document.getElementById('reschedule-section');if(rs)rs.style.display='block';var inp=document.getElementById('reschedule-date-input');if(!inp.value)openDateModal();}}
function openDateModal(){{document.getElementById('date-modal').style.display='flex';}}
function closeDateModal(){{document.getElementById('date-modal').style.display='none';var inp=document.getElementById('reschedule-date-input');if(!inp.value){{document.querySelectorAll('input[name="confirmation"]').forEach(function(r){{r.checked=false;}});document.getElementById('reschedule-section').style.display='none';if(hasLunch){{var ls=document.getElementById('lunch-section');if(ls)ls.style.display='none';}}}}}}
function confirmDate(){{var p=document.getElementById('modal-date-picker');if(!p.value){{alert('Please select a date.');return;}}document.getElementById('reschedule-date-input').value=p.value;document.getElementById('reschedule-display').textContent=p.value;document.getElementById('reschedule-selected').style.display='block';document.getElementById('reschedule-prompt').style.display='none';document.getElementById('date-modal').style.display='none';}}
var isYesConfirmed={'true' if yes_locked else 'false'},_lunchConfirmed=false;
document.querySelector('form').addEventListener('submit',function(e){{
  var c=document.querySelector('input[name="confirmation"]:checked');
  if(!c&&!isYesConfirmed){{e.preventDefault();alert('Please select YES or Modify.');return;}}
  if(c&&c.value==='modify_req'){{var d=document.getElementById('reschedule-date-input').value;if(!d){{e.preventDefault();openDateModal();return;}}}}
  var isYes=(isYesConfirmed||(c&&c.value==='yes'));
  if(isYes&&hasLunch&&!_lunchConfirmed){{
    var tot=totL(),diff=partySize-tot;
    if(diff>0){{
      e.preventDefault();
      document.getElementById('lunch-warn-count').textContent=diff;
      document.getElementById('lunch-warn-modal').style.display='flex';
      return;
    }}
  }}
}});
function lunchWarnContinue(){{_lunchConfirmed=true;document.getElementById('lunch-warn-modal').style.display='none';document.querySelector('form').requestSubmit();}}
function lunchWarnBack(){{document.getElementById('lunch-warn-modal').style.display='none';}}
function adj(t,d){{var el=document.getElementById('c-'+t),cur=parseInt(el.value)||0,tot=totL();var nv=cur+d;if(nv<0)return;if(d>0&&tot>=partySize)return;el.value=nv;updT();}}
function totL(){{var t=(parseInt(document.getElementById('c-turkey')?.value)||0)+(parseInt(document.getElementById('c-veggie')?.value)||0);var b=document.getElementById('c-beef');if(b)t+=parseInt(b.value)||0;return t;}}
function updT(){{var t=totL(),el=document.getElementById('ltotal');if(el){{el.textContent=t;el.style.color=t===partySize?'#27ae60':'#e74c3c';}}}}
if(hasLunch)updT();
var ck=document.querySelector('input[name="confirmation"]:checked');if(ck){{if(ck.value==='modify_req')onModify(ck);else onYN(ck);}}
function adjMtlv(d){{var el=document.getElementById('c-mtlv');if(!el)return;var cur=parseInt(el.value)||0,nv=cur+d;if(nv<0||nv>{qty})return;el.value=nv;}}"""

    body = f"""<div class="gf-wrap"><div class="gf-card">
      <div class="gf-header">
        <div class="gf-header-logo">
          <img src="https://nationalparkexpress.com/wp-content/uploads/2026/03/image002.png" />
        </div>
        <div class="gf-header-text">
          <h1>Tour Confirmation</h1>
          <div class="gf-tour-badge">{tour_config['label']}</div>
          <div class="gf-date">{date_fmt}</div>
          <div class="gf-meta">Order #{booking.order_number or ''} &nbsp;·&nbsp; {booking.first_name} &nbsp;·&nbsp; Party of {qty}</div>
        </div>
      </div>

      <div class="gf-pickup-box">
        <div class="gf-box-title">🚌 Your Pickup Information</div>
        {pickup_html}
      </div>

      {fee_html}
      {banners}

      <form method="post">
        <input type="hidden" name="npe_submit" value="1">

        {'<!--last-minute: modify hidden-->' if is_last_minute else f'''
        <div class="gf-section">
          <div style="background:#e8f4fd;border-left:4px solid #1a3a5c;border-radius:6px;padding:14px 16px;margin-bottom:16px;font-size:14px;color:#1a3a5c;">
            <p style="margin:0 0 8px;"><strong>Confirm Your Tour</strong><br>Click <strong>YES</strong> to confirm, then select lunch and click <strong>Submit Confirmation</strong>.</p>
            <p style="margin:0 0 8px;"><strong>Request a Date Change</strong><br>If you would like to change your tour date, click <strong>Modify</strong> — you do not need to click YES first. Choose your preferred new date and click <strong>Submit Confirmation</strong>. Our reservations team will contact you as soon as possible to confirm availability.</p>
            <p style="margin:0;"><strong>Important:</strong> Your reservation is only finalized after you click <strong>Submit Confirmation</strong>.</p>
          </div>
          <div class="gf-yn-row">
            {yes_btn}
            <label class="gf-yn no" style="{modify_style_attr}">
              <input type="radio" name="confirmation" value="modify_req"
                {"checked" if is_modify_req else ""}
                {modify_dis_attr} onchange="onModify(this)">
              <span class="gf-yn-icon">✏️</span>
              <span class="gf-yn-label">Modify<br><small>{modify_sub}</small></span>
            </label>
            <div id="reschedule-section" style="display:none;width:100%;margin-top:12px;">
              <input type="hidden" name="reschedule_date" id="reschedule-date-input" value="">
              <div id="reschedule-selected" style="display:none;background:#f0f5ff;border:1px solid #b3d1f7;border-radius:8px;padding:10px 14px;font-size:13px;color:#1a3a5c;">
                📅 Requested date: <strong id="reschedule-display"></strong>
                <button type="button" onclick="openDateModal()" style="margin-left:10px;font-size:12px;background:none;border:none;color:#1a3a5c;text-decoration:underline;cursor:pointer;">Change</button>
              </div>
              <div id="reschedule-prompt" style="background:#f0f5ff;border:1px solid #b3d1f7;border-radius:8px;padding:10px 14px;font-size:13px;color:#1a3a5c;">
                📅 <button type="button" onclick="openDateModal()" style="background:none;border:none;color:#1a3a5c;font-weight:bold;text-decoration:underline;cursor:pointer;font-size:13px;">Click here to select a new tour date</button>
              </div>
            </div>
          </div>
        </div>'''}

        {lunch_html}

        {mtlv_html}

        <div class="gf-reminders">
          <div class="gf-box-title">📌 Important Reminders</div>
          <ul>{reminders_html}</ul>
        </div>

        <div class="gf-section">
          <div style="background:#f0f6ff;border:1px solid #b3d1f7;border-radius:8px;padding:16px 18px;margin-bottom:16px;font-size:14px;color:#333;line-height:1.7;">
            <p style="margin:0 0 8px;">To ensure a smooth pick-up process, check-in and Bus Track information will be sent to your mobile phone prior to departure.</p>
            <p style="margin:0 0 8px;">Please confirm that the following phone number is correct: <strong>{booking.phone or 'Not on file'}</strong></p>
            <p style="margin:0;">If this number is incorrect, kindly provide the correct number in the Notes section below.</p>
          </div>
          {notes_display_html}
          <h2>📝 Notes <span class="gf-opt">(optional)</span></h2>
          <textarea name="notes" rows="3" placeholder="Special requests, dietary notes...">{booking.notes or ''}</textarea>
        </div>

        <div class="gf-submit">
          <button type="submit" class="gf-btn">Submit Confirmation</button>
          <p class="gf-small">Thank you for choosing National Park Express — we look forward to your adventure! 🏞️</p>
        </div>
      </form>
    </div></div>

    <div id="date-modal" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:9999;align-items:center;justify-content:center;">
      <div style="background:#fff;border-radius:16px;padding:28px 24px;max-width:340px;width:90%;box-shadow:0 8px 32px rgba(0,0,0,0.2);">
        <h3 style="margin:0 0 6px;color:#1a3a5c;font-size:17px;">📅 Select New Tour Date</h3>
        <p style="margin:0 0 16px;font-size:13px;color:#666;">Please select your requested new date below.</p>
        <input type="date" id="modal-date-picker" min="{tomorrow}" style="width:100%;padding:12px;border:1px solid #ddd;border-radius:8px;font-size:16px;margin-bottom:16px;" onclick="try{{this.showPicker();}}catch(e){{}}">
        <div style="display:flex;gap:10px;">
          <button type="button" onclick="closeDateModal()" style="flex:1;padding:12px;border:1px solid #ccc;border-radius:8px;background:#f5f5f5;font-size:14px;cursor:pointer;">← Back</button>
          <button type="button" onclick="confirmDate()" style="flex:1;padding:12px;border:none;border-radius:8px;background:#1a3a5c;color:#fff;font-size:14px;font-weight:bold;cursor:pointer;">Confirm</button>
        </div>
      </div>
    </div>

    <div id="lunch-warn-modal" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:9999;align-items:center;justify-content:center;">
      <div style="background:#fff;border-radius:16px;padding:28px 24px;max-width:340px;width:90%;box-shadow:0 8px 32px rgba(0,0,0,0.2);">
        <h3 style="margin:0 0 10px;color:#b45309;font-size:17px;">&#9888; Lunch Selection Incomplete</h3>
        <p style="margin:0 0 18px;font-size:14px;color:#444;line-height:1.6;">You have <strong><span id="lunch-warn-count"></span> guest(s)</strong> without a lunch selection. Unselected guests will be noted for your guide to arrange on the day.</p>
        <div style="display:flex;gap:10px;">
          <button type="button" onclick="lunchWarnBack()" style="flex:1;padding:12px;border:1px solid #ccc;border-radius:8px;background:#f5f5f5;font-size:14px;cursor:pointer;">&#8592; Go Back</button>
          <button type="button" onclick="lunchWarnContinue()" style="flex:1;padding:12px;border:none;border-radius:8px;background:#2F7851;color:#fff;font-size:14px;font-weight:bold;cursor:pointer;">Continue</button>
        </div>
      </div>
    </div>
    <script>{js}</script>"""

    return HTMLResponse(_page("Tour Confirmation", body))


# ── Tickets Reminder — Guest Confirmation ─────────────────────────────────────
# GET  /confirm/tickets?token=...&npe_tix_autoyes=1&src=...
# POST /confirm/tickets

from app.services.tickets_reminder import (
    TOUR_TYPES          as TIX_TOUR_TYPES,
    verify_token        as tix_verify_token,
    build_staff_email   as tix_build_staff_email,
    render_expired      as tix_render_expired,
    render_thanks       as tix_render_thanks,
    render_form         as tix_render_form,
)
from app.services.sendgrid import send_raw_email as _send_email

_TIX_STAFF = "confirmations@nationalparkexpress.com"


@router.get("/confirm/tickets", response_class=HTMLResponse)
async def tix_confirm_get(request: Request, db: AsyncSession = Depends(get_db)):
    token   = request.query_params.get("token", "")
    autoyes = request.query_params.get("npe_tix_autoyes", "")
    src     = request.query_params.get("src", "")

    err, row = await tix_verify_token(token, db)
    if err:
        return HTMLResponse(tix_render_expired())

    cfg = TIX_TOUR_TYPES.get(row.get("tour_type", ""), next(iter(TIX_TOUR_TYPES.values())))

    # Auto-YES: guest clicked the email CTA button
    if autoyes == "1" and row.get("confirmation") != "yes":
        new_count = int(row.get("submission_count") or 0) + 1
        now_ts = datetime.now(timezone.utc).replace(tzinfo=None)
        order_number = row.get("chd_number") or row.get("order_number", "")
        # Write to tickets_reminders (backward compat)
        await db.execute(
            _sql_text("""UPDATE tickets_reminders
                         SET confirmation='yes', submitted_at=:ts,
                             submission_count=:c, source=:s
                         WHERE id=:id"""),
            {"ts": now_ts, "c": new_count, "s": src, "id": row["id"]},
        )
        # Also sync to bookings table (primary tracking source)
        await db.execute(
            _sql_text("""UPDATE bookings
                         SET confirmation='yes', submitted_at=:ts,
                             submission_count=:c
                         WHERE order_number=:order_number
                           AND module='tickets_reminder'"""),
            {"ts": now_ts, "c": new_count, "order_number": order_number},
        )
        await db.commit()
        result = await db.execute(
            _sql_text("SELECT * FROM tickets_reminders WHERE id=:id"), {"id": row["id"]}
        )
        row = dict(result.mappings().fetchone())
        subj, body = tix_build_staff_email(row, row.get("tour_type", ""), row.get("reschedule_notes", "") or "")
        try:
            await _send_email(_TIX_STAFF, "NPE Staff", subj, body)
        except Exception as exc:
            print(f"[tix_confirm] staff email failed: {exc}")

    already = bool(row.get("submitted_at")) and row.get("confirmation") != "pending"
    return HTMLResponse(tix_render_form(row, cfg, token=token, already=already))


@router.post("/confirm/tickets", response_class=HTMLResponse)
async def tix_confirm_post(
    db: AsyncSession  = Depends(get_db),
    token: str        = Form(""),
    confirmation: str = Form(""),
    notes: str        = Form(""),
):
    err, row = await tix_verify_token(token, db)
    if err:
        return HTMLResponse(tix_render_expired())

    cfg = TIX_TOUR_TYPES.get(row.get("tour_type", ""), next(iter(TIX_TOUR_TYPES.values())))

    if confirmation != "yes":
        return HTMLResponse(tix_render_form(row, cfg, token=token,
                                            error_msg="Please select YES to confirm."))

    new_count = int(row.get("submission_count") or 0) + 1
    now_ts = datetime.now(LA).replace(tzinfo=None)
    order_number = row.get("chd_number") or row.get("order_number", "")
    # Write to tickets_reminders (backward compat)
    await db.execute(
        _sql_text("""UPDATE tickets_reminders
                     SET confirmation='yes', reschedule_notes=:n,
                         submitted_at=:ts, submission_count=:c, source='form'
                     WHERE id=:id"""),
        {"n": notes, "ts": now_ts, "c": new_count, "id": row["id"]},
    )
    # Also sync to bookings table (primary tracking source)
    await db.execute(
        _sql_text("""UPDATE bookings
                     SET confirmation='yes', notes=:n,
                         submitted_at=:ts, submission_count=:c
                     WHERE order_number=:order_number
                       AND module='tickets_reminder'"""),
        {"n": notes, "ts": now_ts, "c": new_count, "order_number": order_number},
    )
    await db.commit()
    result = await db.execute(
        _sql_text("SELECT * FROM tickets_reminders WHERE id=:id"), {"id": row["id"]}
    )
    row = dict(result.mappings().fetchone())

    subj, body = tix_build_staff_email(row, row.get("tour_type", ""), notes)
    try:
        await _send_email(_TIX_STAFF, "NPE Staff", subj, body)
    except Exception as exc:
        print(f"[tix_confirm] staff email failed: {exc}")

    return HTMLResponse(tix_render_thanks(row))


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/confirm/{token}", response_class=HTMLResponse)
async def guest_confirm_page(token: str, db: AsyncSession = Depends(get_db)):
    print(f"[guest] looking up token: {token}")
    result = await db.execute(select(Booking).where(Booking.confirm_token == token))
    booking = result.scalar_one_or_none()
    print(f"[guest] booking found: {booking}")
    
    if not booking:
        return _expired()

    tour_config = TOUR_TYPES.get(booking.tour_type or "", list(TOUR_TYPES.values())[0])
    pu_inst, pu_photo, pu_label = await _fetch_pickup_info(booking.pickup_location, db)
    is_last_minute = bool(booking.is_last_minute)
    return _render(booking, tour_config,
                   pickup_instruction=pu_inst, pickup_photo_url=pu_photo, pickup_photo_label=pu_label,
                   is_last_minute=is_last_minute)


@router.post("/confirm/{token}", response_class=HTMLResponse)
async def guest_confirm_submit(
    token: str,
    db: AsyncSession = Depends(get_db),
    npe_submit:      str = Form(default=""),
    confirmation:    str = Form(default=""),
    lunch_turkey:    int = Form(default=0),
    lunch_veggie:    int = Form(default=0),
    lunch_beef:      int = Form(default=0),
    reschedule_date: str = Form(default=""),
    notes:           str = Form(default=""),
    src:             str = Form(default="email"),
    mtlv_qty:        int = Form(default=0),
):
    if npe_submit != "1":
        return _expired()

    result = await db.execute(select(Booking).where(Booking.confirm_token == token))
    booking = result.scalar_one_or_none()
    if not booking:
        return _expired()

    tour_config = TOUR_TYPES.get(booking.tour_type or "", list(TOUR_TYPES.values())[0])
    qty         = int(booking.quantities or 1)
    has_lunch   = tour_config.get("has_lunch", False)

    # Modify locked from midnight (23:59 PM LA) of 2 day before tour date
    _mod_locked = False
    if booking.tour_date:
        from datetime import timedelta as _td
        _deadline = datetime(
            booking.tour_date.year,
            booking.tour_date.month,
            booking.tour_date.day,
            23, 59, 0,
            tzinfo=LA
        ) - _td(days=2)
        if datetime.now(LA) >= _deadline:
            _mod_locked = True
    _modify_count = (booking.notes_history or "").count("] Modify requested")

    # v4.17.14: Already-YES guest submits without radio — treat as lunch update
    is_yes_confirmed = booking.confirmation == "yes"
    if is_yes_confirmed and not confirmation:
        confirmation = "yes"

    # For already-YES guests: if lunch counters are all 0 (notes-only submit),
    # fall back to existing lunch values so validation is not triggered.
    _lunch_submitted = (lunch_turkey + lunch_veggie + lunch_beef) > 0
    if is_yes_confirmed and not _lunch_submitted:
        lunch_turkey = int(booking.lunch_turkey or 0)
        lunch_veggie = int(booking.lunch_veggie or 0)
        lunch_beef   = int(booking.lunch_beef   or 0)

    # Validation
    error_msg = ""
    ts = datetime.now(LA).strftime("%Y-%m-%d %H:%M")
    is_last_minute = bool(booking.is_last_minute)
    if is_last_minute:
        confirmation = "yes"
    elif not confirmation:
        error_msg = "Please select YES oSr Modify."
    elif confirmation not in ("yes", "modify_req"):
        error_msg = "Please select YES or Modify."
    elif confirmation == "yes" and is_yes_confirmed and _mod_locked:
        error_msg = "Lunch selection is locked. Changes are no longer accepted after 11:59 PM, two days before your tour."
    elif confirmation == "modify_req" and _mod_locked:
        error_msg = "This request is only valid up to 24 hours before your tour."
    elif confirmation == "modify_req" and _modify_count >= 2:
        error_msg = "You have reached the maximum number of date change requests (2). Please contact us at reservations@nationalparkexpress.com or call 702-948-4190."
    elif confirmation == "modify_req" and not reschedule_date:
        error_msg = "Please select a new tour date for your Modify request."
    # Lunch total validation handled client-side with warning modal; no server-side block

    if error_msg:
        pu_inst, pu_photo, pu_label = await _fetch_pickup_info(booking.pickup_location, db)
        return _render(booking, tour_config, error_msg=error_msg,
                       pickup_instruction=pu_inst, pickup_photo_url=pu_photo, pickup_photo_label=pu_label)

    # v4.17.14: Build notes/history with full logging for every action
    new_count   = int(booking.submission_count or 0) + 1
    new_history = (booking.notes_history or "").strip()

    if confirmation == "modify_req":
        entry = (
            f"[{ts}] Modify requested"
            + (f": {reschedule_date}" if reschedule_date else "")
            + (f" — {notes}" if notes else "")
        )
        final_notes = entry
        new_history = (entry + "\n" + new_history).strip() if new_history else entry
    elif confirmation == "yes" and booking.confirmation == "modify_req":
        # Cancel modify_req — log it
        entry = f"[{ts}] Date change request cancelled. Confirmed original tour date." + (f" — {notes}" if notes else "")
        final_notes = entry
        new_history = (entry + "\n" + new_history).strip() if new_history else entry
    elif confirmation == "yes" and is_yes_confirmed:
        # Lunch update or notes-only update
        pt = int(booking.lunch_turkey or 0); pv = int(booking.lunch_veggie or 0); pb = int(booking.lunch_beef or 0)
        # No-op guard: if lunch values are identical and no notes, skip all writes
        if lunch_turkey == pt and lunch_veggie == pv and lunch_beef == pb and not notes:
            return _thanks(booking)
        # Notes-only submit (lunch unchanged): log as notes update, not lunch update
        if lunch_turkey == pt and lunch_veggie == pv and lunch_beef == pb:
            entry = f"[{ts}] Guest note added." + (f" — {notes}" if notes else "")
        else:
            entry = f"[{ts}] Lunch updated: T×{lunch_turkey} V×{lunch_veggie} B×{lunch_beef} (was T×{pt} V×{pv} B×{pb})" + (f" — {notes}" if notes else "")
        final_notes = entry
        new_history = (entry + "\n" + new_history).strip() if new_history else entry
    else:
        # First YES
        entry = f"[{ts}] Confirmed YES." + (f" — {notes}" if notes else "")
        final_notes = notes  # keep plain guest note as notes field for first YES
        new_history = (entry + "\n" + new_history).strip() if new_history else entry

    # Persist
    booking.confirmation     = confirmation
    booking.lunch_turkey     = lunch_turkey
    booking.lunch_veggie     = lunch_veggie
    booking.lunch_beef       = lunch_beef
    booking.notes            = final_notes
    booking.notes_history    = new_history
    booking.submitted_at     = datetime.now(LA).replace(tzinfo=None)
    booking.submission_count = new_count

    # MTLV — only write if eligible and not locked (sent/cancel)
    if getattr(booking, "mtlv_eligible", False):
        _mtlv_locked_status = getattr(booking, "mtlv_ticket_status", None)
        if _mtlv_locked_status not in ("sent", "cancel"):
            clamped = max(0, min(int(mtlv_qty), int(booking.quantities or 1)))
            booking.mtlv_qty = clamped
            # Auto-set ticket status to pending_send on first reply
            booking.mtlv_ticket_status = "pending_send"
    
    # Save guest message to booking_notes if notes were provided
    if notes and notes.strip():
        guest_note = BookingNote(
            booking_id=booking.id,
            author_username="guest",
            direction="guest_reply",
            body=notes.strip(),
            created_at=datetime.now(LA),
        )
        db.add(guest_note)
        await db.commit()

    # Activity log
    try:
        _activity_detail = ""
        _event_type = ""
        if confirmation == "modify_req":
            _event_type = "guest_modify_requested"
            _activity_detail = f"Modify requested: {reschedule_date}" + (f" — {notes}" if notes else "")
        elif confirmation == "yes" and is_yes_confirmed and has_lunch:
            _event_type = "lunch_selected"
            _activity_detail = f"Lunch updated: Turkey×{lunch_turkey} Veggie×{lunch_veggie} Beef×{lunch_beef}"
        else:
            _event_type = "guest_confirmed"
            _activity_detail = "Guest confirmed YES" + (f" — {notes}" if notes else "")

        await db.execute(_sql_text("""
            INSERT INTO activity_log (order_number, event_type, detail, actor, actor_type)
            VALUES (:order_number, :event_type, :detail, :actor, :actor_type)
        """), {
            "order_number": booking.order_number,
            "event_type":   _event_type,
            "detail":       _activity_detail,
            "actor":        booking.first_name,
            "actor_type":   "guest",
        })

        # MTLV qty if eligible
        if getattr(booking, "mtlv_eligible", False) and mtlv_qty > 0:
            await db.execute(_sql_text("""
                INSERT INTO activity_log (order_number, event_type, detail, actor, actor_type)
                VALUES (:order_number, :event_type, :detail, :actor, :actor_type)
            """), {
                "order_number": booking.order_number,
                "event_type":   "mtlv_qty_selected",
                "detail":       f"MTLV ticket qty selected: {mtlv_qty}",
                "actor":        booking.first_name,
                "actor_type":   "guest",
            })

        await db.commit()
    except Exception as exc:
        print(f"[guest] activity log failed: {exc}")
    await db.refresh(booking)

    # Staff notification (best-effort, don't block response)
    try:
        await send_staff_notification(
            booking, confirmation,
            turkey=lunch_turkey, veggie=lunch_veggie, beef=lunch_beef,
            notes=final_notes, submission_count=new_count,
        )
    except Exception as exc:
        print(f"[guest] staff notification failed: {exc}")

    return _thanks(booking)