"""
app/routers/guest.py
Guest-facing confirmation form — full port from PHP tour-confirmation.php
GET  /confirm/{token}  — show form
POST /confirm/{token}  — handle submission
"""

from datetime import datetime
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Booking
from app.services.tour_config import TOUR_TYPES
from app.services.sendgrid import send_staff_notification

router = APIRouter()

BASE_URL = "https://confirm.nationalparkexpress.com"


# ── CSS ───────────────────────────────────────────────────────────────────────

GUEST_CSS = """*{box-sizing:border-box;margin:0;padding:0;}
body{background:#f0f4f8;font-family:"Helvetica Neue",Arial,sans-serif;color:#333;padding:16px;}
.gf-wrap{max-width:580px;margin:0 auto;padding:10px 0 40px;}
.gf-card{background:#fff;border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,.10);overflow:hidden;}
.gf-header{background:#1a3a5c;color:#fff;padding:26px;text-align:center;}
.gf-header h1{font-size:20px;margin:8px 0 4px;}
.gf-tour-badge{background:rgba(255,255,255,.15);border-radius:6px;padding:5px 14px;display:inline-block;font-size:13px;font-weight:bold;margin-bottom:6px;}
.gf-date{font-size:17px;font-weight:bold;color:#fff;margin:4px 0;}
.gf-meta{font-size:12px;color:#a8c4e0;margin-top:4px;}
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


def _render(booking, tour_config: dict, error_msg: str = "") -> HTMLResponse:
    from datetime import date as date_type
    tour_date  = booking.tour_date
    date_fmt   = tour_date.strftime("%A, %B %-d, %Y") if tour_date else "—"
    qty        = int(booking.quantities or 1)
    has_lunch  = tour_config.get("has_lunch", False)
    has_beef   = tour_config.get("has_beef", False)
    already    = booking.submitted_at and booking.confirmation != "pending"
    hide_yes   = booking.confirmation in ("yes", "modify_req")
    modify_locked = (
        booking.submitted_at and
        (datetime.now() - booking.submitted_at).total_seconds() < 43200
    ) if booking.submitted_at else False

    # Pickup box — photo_url stored in pickup_location if it starts with http,
    # otherwise just show the location name
    ploc = booking.pickup_location or ""
    pickup_html = ""
    if ploc:
        pickup_html += f'<div class="gf-row"><span>📍</span><span>Please arrive at <strong>{ploc}</strong></span></div>'
    if booking.pickup_time:
        pickup_html += (
            f'<div class="gf-row"><span>⏰</span><span>Arrive by '
            f'<strong>{booking.pickup_time}</strong> for check-in. '
            f'Departs promptly — vehicle cannot wait for late arrivals.</span></div>'
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

    # YES button
    if not hide_yes:
        yes_btn = f"""<label class="gf-yn yes">
          <input type="radio" name="confirmation" value="yes"
            {'checked' if booking.confirmation == 'yes' else ''} required onchange="onYN(this)">
          <span class="gf-yn-icon">✅</span>
          <span class="gf-yn-label">YES<br><small>I'm attending</small></span>
        </label>"""
    else:
        yes_btn = """<div class="gf-yn yes" style="opacity:0.5;cursor:not-allowed;border-color:#27ae60;background:#f0fff4;">
          <span class="gf-yn-icon">✅</span>
          <span class="gf-yn-label">YES<br><small>Already confirmed</small></span>
        </div>"""

    modify_style    = "cursor:not-allowed;opacity:0.5;" if modify_locked else ""
    modify_disabled = "disabled" if modify_locked else ""
    modify_sub      = "Locked (within 12h)" if modify_locked else "my booking"

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
        lunch_show = "" if booking.confirmation == "yes" else "display:none"
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
    <li>You may bring small items like personal fans or ice packs.</li>
    <li>If you don't see the shuttle 10 min before departure, call <strong>702-948-4190</strong>.</li>"""

    tomorrow = (date_type.today().__class__.fromordinal(date_type.today().toordinal() + 1)).isoformat()

    js = f"""
var partySize={qty},hasLunch={'true' if has_lunch else 'false'};
function onYN(el){{if(hasLunch){{var ls=document.getElementById('lunch-section');if(ls)ls.style.display=el.value==='yes'?'':'none';}}var rs=document.getElementById('reschedule-section');if(rs)rs.style.display='none';}}
function onModify(el){{if(hasLunch){{var ls=document.getElementById('lunch-section');if(ls)ls.style.display='none';}}var rs=document.getElementById('reschedule-section');if(rs)rs.style.display='block';var inp=document.getElementById('reschedule-date-input');if(!inp.value)openDateModal();}}
function openDateModal(){{document.getElementById('date-modal').style.display='flex';}}
function closeDateModal(){{document.getElementById('date-modal').style.display='none';var inp=document.getElementById('reschedule-date-input');if(!inp.value){{document.querySelectorAll('input[name="confirmation"]').forEach(function(r){{r.checked=false;}});document.getElementById('reschedule-section').style.display='none';if(hasLunch){{var ls=document.getElementById('lunch-section');if(ls)ls.style.display='none';}}}}}}
function confirmDate(){{var p=document.getElementById('modal-date-picker');if(!p.value){{alert('Please select a date.');return;}}document.getElementById('reschedule-date-input').value=p.value;document.getElementById('reschedule-display').textContent=p.value;document.getElementById('reschedule-selected').style.display='block';document.getElementById('reschedule-prompt').style.display='none';document.getElementById('date-modal').style.display='none';}}
document.querySelector('form').addEventListener('submit',function(e){{var c=document.querySelector('input[name="confirmation"]:checked');if(!c){{e.preventDefault();alert('Please select YES or Modify.');return;}}if(c.value==='modify_req'){{var d=document.getElementById('reschedule-date-input').value;if(!d){{e.preventDefault();openDateModal();return;}}}}}});
function adj(t,d){{var el=document.getElementById('c-'+t),cur=parseInt(el.value)||0,tot=totL();var nv=cur+d;if(nv<0)return;if(d>0&&tot>=partySize)return;el.value=nv;updT();}}
function totL(){{var t=(parseInt(document.getElementById('c-turkey')?.value)||0)+(parseInt(document.getElementById('c-veggie')?.value)||0);var b=document.getElementById('c-beef');if(b)t+=parseInt(b.value)||0;return t;}}
function updT(){{var t=totL(),el=document.getElementById('ltotal');if(el){{el.textContent=t;el.style.color=t===partySize?'#27ae60':'#e74c3c';}}}}
if(hasLunch)updT();
var ck=document.querySelector('input[name="confirmation"]:checked');if(ck){{if(ck.value==='modify_req')onModify(ck);else onYN(ck);}}"""

    body = f"""<div class="gf-wrap"><div class="gf-card">
      <div class="gf-header">
        <img src="https://nationalparkexpress.com/wp-content/uploads/2026/03/image002.png" style="width:100px;height:auto;" />
        <div class="gf-tour-badge">{tour_config['label']}</div>
        <h1>Tour Confirmation</h1>
        <div class="gf-date">{date_fmt}</div>
        <div class="gf-meta">Order #{booking.order_number or ''} &nbsp;·&nbsp; {booking.first_name} {booking.last_name} &nbsp;·&nbsp; Party of {qty}</div>
      </div>

      <div class="gf-pickup-box">
        <div class="gf-box-title">🚌 Your Pickup Information</div>
        {pickup_html}
      </div>

      {fee_html}
      {banners}

      <form method="post">
        <input type="hidden" name="npe_submit" value="1">

        <div class="gf-section">
          <div style="background:#e8f4fd;border-left:4px solid #1a3a5c;border-radius:6px;padding:14px 16px;margin-bottom:16px;font-size:14px;color:#1a3a5c;">
            <p style="margin:0 0 8px;"><strong>Confirm Your Tour</strong><br>Click <strong>YES</strong> to confirm, then select lunch and click <strong>Submit Confirmation</strong>.</p>
            <p style="margin:0 0 8px;"><strong>Request a Date Change</strong><br>Click <strong>Modify</strong> and choose your preferred new date.</p>
            <p style="margin:0;"><strong>Important:</strong> Your reservation is only finalized after you click <strong>Submit Confirmation</strong>.</p>
          </div>
          <div class="gf-yn-row">
            {yes_btn}
            <label class="gf-yn no" style="{modify_style}">
              <input type="radio" name="confirmation" value="modify_req"
                {'checked' if booking.confirmation == 'modify_req' else ''}
                {modify_disabled} onchange="onModify(this)">
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
        </div>

        {lunch_html}

        <div class="gf-reminders">
          <div class="gf-box-title">📌 Important Reminders</div>
          <ul>{reminders_html}</ul>
        </div>

        <div class="gf-section">
          <div style="background:#f0f6ff;border:1px solid #b3d1f7;border-radius:8px;padding:16px 18px;margin-bottom:16px;font-size:14px;color:#333;line-height:1.7;">
            <p style="margin:0 0 8px;">Check-in and Bus Track information will be sent to your mobile phone prior to departure.</p>
            <p style="margin:0 0 8px;">Please confirm your phone number is correct: <strong>{booking.phone or 'Not on file'}</strong></p>
            <p style="margin:0;">If incorrect, please enter your correct number in the Notes box below.</p>
          </div>
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
    <script>{js}</script>"""

    return HTMLResponse(_page("Tour Confirmation", body))


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/confirm/{token}", response_class=HTMLResponse)
async def guest_confirm_page(token: str):
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Booking).where(Booking.confirm_token == token))
        booking = result.scalar_one_or_none()

    if not booking:
        return _expired()

    tour_config = TOUR_TYPES.get(booking.tour_type or "", list(TOUR_TYPES.values())[0])
    return _render(booking, tour_config)


@router.post("/confirm/{token}", response_class=HTMLResponse)
async def guest_confirm_submit(
    token: str,
    npe_submit:      str = Form(default=""),
    confirmation:    str = Form(default=""),
    lunch_turkey:    int = Form(default=0),
    lunch_veggie:    int = Form(default=0),
    lunch_beef:      int = Form(default=0),
    reschedule_date: str = Form(default=""),
    notes:           str = Form(default=""),
    src:             str = Form(default="email"),
):
    if npe_submit != "1":
        return _expired()

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Booking).where(Booking.confirm_token == token))
        booking = result.scalar_one_or_none()
        if not booking:
            return _expired()

        tour_config = TOUR_TYPES.get(booking.tour_type or "", list(TOUR_TYPES.values())[0])
        qty         = int(booking.quantities or 1)
        has_lunch   = tour_config.get("has_lunch", False)

        # Validation
        error_msg = ""
        if confirmation not in ("yes", "modify_req"):
            error_msg = "Please select YES or Modify."
        elif confirmation == "yes" and has_lunch and (lunch_turkey + lunch_veggie + lunch_beef) != qty:
            error_msg = f"Lunch total must equal your party size of {qty}."

        if error_msg:
            return _render(booking, tour_config, error_msg=error_msg)

        # Build notes/history
        new_count   = int(booking.submission_count or 0) + 1
        final_notes = notes
        new_history = booking.notes_history or ""

        if confirmation == "modify_req":
            ts    = datetime.now().strftime("%Y-%m-%d %H:%M")
            entry = (
                f"[{ts}] Modify requested"
                + (f": {reschedule_date}" if reschedule_date else "")
                + (f" — {notes}" if notes else "")
            )
            final_notes = entry
            new_history = (entry + "\n" + new_history).strip() if new_history else entry

        # Persist
        booking.confirmation     = confirmation
        booking.lunch_turkey     = lunch_turkey
        booking.lunch_veggie     = lunch_veggie
        booking.lunch_beef       = lunch_beef
        booking.notes            = final_notes
        booking.notes_history    = new_history
        booking.submitted_at     = datetime.now()
        booking.submission_count = new_count
        booking.source           = src

        await db.commit()
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
