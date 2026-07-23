"""
NPE — Tickets Reminder service layer
Shared by send_tickets.py, tracking_tickets.py, guest.py

Contains:
  - TOUR_TYPES (9 Antelope Canyon operators)
  - Token make/verify
  - SMS / Email builders
  - Staff notification email
  - Guest confirmation page HTML renderer
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import os
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_LA = ZoneInfo("America/Los_Angeles")
from html import escape

from app.services.template_copy import (
    get_copy_many,
    get_copy_value,
    render_copy,
    TIX_KEYS,
    TIX_TOUR_FIELDS,
)

SECRET_KEY       = os.environ.get("TOKEN_SECRET", "npe_tix_secret_fallback")
CONFIRM_BASE_URL = os.environ.get("SERVICE_BASE_URL", "https://confirm.nationalparkexpress.com")

# ── Tour types ────────────────────────────────────────────────────────────────
TOUR_TYPES: dict[str, dict] = {
    "upper_antelope_tsosie": {
        "label":            "Upper Antelope Canyon – Chief Tsosie Tours",
        "sms_label":        "Upper Antelope Canyon Tour",
        "abbr":             "U-TC",
        "checkin_location": "Antelope Slot Canyon Tours, 148 6th Ave, Page, AZ 86040",
        "maps_url":         "https://goo.gl/maps/t8e9E9uioEWG9zHn7",
        "location_photo":   "https://maps.app.goo.gl/DiwJPosKMWNXzrH3A",
        "extra_notes": [
            "★ No children, toddlers or infants (ages 0–5) are permitted due to safety concerns.",
            "The general guidelines for visiting Antelope Canyon:\n1.Bottled water is allowed.\n2.No bags are allowed on the walking tour. Please leave all bags in your vehicle.\n3.Phones and standard cameras are allowed.\n4.Tripods, monopods, large camera equipment, and flash/light equipment are generally NOT permitted.\n\nPlease note that rules may vary slightly depending on the canyon and tour operator. Final instructions will be provided by the guide on site.",
        ],
        "prepare_steps": [],
    },
    "upper_antelope_brenda": {
        "label":            "Upper Antelope Canyon – Brenda (Tse Bighanilini Tours)",
        "sms_label":        "Upper Antelope Canyon Tour",
        "abbr":             "U-BR",
        "checkin_location": "Tse Bighanilini Tours, Highway 98, Milepost 299.8, Page, AZ 86040 (Between 299 and 300)",
        "maps_url":         "https://maps.app.goo.gl/kcixg7Hee9WMMt3h8",
        "location_photo":   "https://maps.app.goo.gl/3meJhQqfCAAt9Ayp7",
        "extra_notes": [
            "Car seats are required for children under 4. Visitors must provide their own car seat or booster seat.",
            "The general guidelines for visiting Antelope Canyon:\n1.Bottled water is allowed.\n2.No bags are allowed on the walking tour. Please leave all bags in your vehicle.\n3.Phones and standard cameras are allowed.\n4.Tripods, monopods, large camera equipment, and flash/light equipment are generally NOT permitted.\n\nPlease note that rules may vary slightly depending on the canyon and tour operator. Final instructions will be provided by the guide on site.",
        ],
        "prepare_steps": [
            {"label": "Sign the required waiver form",
             "url": "https://fareharbor.com/waivers?shortname=tsebighanilini&bookingUuid=4487ab4e-7d05-4cea-860b-b7da6ab47df6&source=copy-link"},
            {"label": "Pay the permit fee using the provided payment link",
             "url": "https://fareharbor.com/embeds/book/navajonationparks/items/691331/calendar/2026/01/",
              "note":  "For all guests, please keep your payment receipt for check-in. Same-day Lower Antelope or Canyon X receipts can waive the Upper Antelope permit fee. If we supplied your tickets, we can provide the receipt — just let us know."},
        ],
    },
     "upper_antelope_brenda_no_fee": {
        "label":            "Upper Antelope Canyon – Brenda (Tse Bighanilini Tours)",
        "sms_label":        "Upper Antelope Canyon Tour",
        "abbr":             "U-BR",
        "checkin_location": "Tse Bighanilini Tours, Highway 98, Milepost 299.8, Page, AZ 86040 (Between 299 and 300)",
        "maps_url":         "https://maps.app.goo.gl/kcixg7Hee9WMMt3h8",
        "location_photo":   "https://maps.app.goo.gl/3meJhQqfCAAt9Ayp7",
        "extra_notes": [
            "Car seats are required for children under 4. Visitors must provide their own car seat or booster seat.",
            "The general guidelines for visiting Antelope Canyon:\n1.Bottled water is allowed.\n2.No bags are allowed on the walking tour. Please leave all bags in your vehicle.\n3.Phones and standard cameras are allowed.\n4.Tripods, monopods, large camera equipment, and flash/light equipment are generally NOT permitted.\n\nPlease note that rules may vary slightly depending on the canyon and tour operator. Final instructions will be provided by the guide on site.",
        ],
        "prepare_steps": [
            {"label": "Sign the required waiver form",
             "url": "https://fareharbor.com/waivers?shortname=tsebighanilini&bookingUuid=4487ab4e-7d05-4cea-860b-b7da6ab47df6&source=copy-link"},
        ],
    },
    "upper_antelope_aact": {
        "label":            "Upper Antelope Canyon – The Adventurous Group (AACT)",
        "sms_label":        "Upper Antelope Canyon Tour",
        "abbr":             "U-AA",
        "checkin_location": "Adventurous Antelope Canyon, Highway 98 Road & Milepost 302, Page, AZ 86040",
        "maps_url":         "https://maps.app.goo.gl/hWXU2JSLSphMda529",
        "location_photo":   "https://maps.app.goo.gl/tZttDC6G3jctLC8E7",
        "extra_notes": [
            "★ Minimum age 8. Guests must be at least 8 years of age to join the walking tour.",
            "★ Pregnant guests are not permitted to participate due to safety concerns.",
            "The general guidelines for visiting Antelope Canyon:\n1.Bottled water is allowed.\n2.No bags are allowed on the walking tour. Please leave all bags in your vehicle.\n3.Phones and standard cameras are allowed.\n4.Tripods, monopods, large camera equipment, and flash/light equipment are generally NOT permitted.\n\nPlease note that rules may vary slightly depending on the canyon and tour operator. Final instructions will be provided by the guide on site.",
        ],
        "prepare_steps": [],
    },
    "upper_antelope_hogan_transport": {
        "label":            "Upper Antelope Canyon – Hogan with Transport",
        "sms_label":        "Upper Antelope Hogan Tour",
        "abbr":             "U-HT",
        "checkin_location": "Antelope Hogan Canyon Tours, LLC, 302 SR-98 (7 miles east of Page), Page, AZ 86040",
        "maps_url":         "https://maps.app.goo.gl/DgmwCEepZbNLRn7A6",
        "location_photo":   "https://maps.app.goo.gl/DztGqAk8b9pUp8EV7",
        "skip_confirmation_no": True,
        "checkin_note": "Please check in under the name on your reservation and let the front desk know how many people are in your group.",
        "extra_notes": [
            "Car seats are required for children under 8. Visitors must provide their own car seat.",
            "★ These entry reservations are non-refundable.",
            "Antelope Canyon does not allow any bags on the walking tour. Please leave them in your vehicle.",
            "If you can't find the check-in location, call: 928-693-9293",
        ],
        "prepare_steps": [
            {"label": "Pay the permit fee using the provided payment link",
             "url":   "https://fareharbor.com/embeds/book/navajonationparks/items/691331/calendar/2026/01/",
             "note":  "For all guests, please keep your payment receipt for check-in. Same-day Lower Antelope or Canyon X receipts can waive the Upper Antelope permit fee. If we supplied your tickets, we can provide the receipt — just let us know."},
        ],
    },
    "upper_antelope_hogan_hiking": {
        "label":            "Upper Antelope Canyon – Hogan Hiking Tour",
        "sms_label":        "Upper Antelope Hiking Tour",
        "abbr":             "U-HH",
        "checkin_location": "Antelope Hogan Canyon Tours, LLC, 302 SR-98 (7 miles east of Page), Page, AZ 86040",
        "maps_url":         "https://maps.app.goo.gl/DgmwCEepZbNLRn7A6",
        "location_photo":   "https://maps.app.goo.gl/DztGqAk8b9pUp8EV7",
        "skip_confirmation_no": True,
        "checkin_note": "Please check in under the name on your reservation and let the front desk know how many people are in your group.",
        "extra_notes": [
            "★ Minimum age 8. Guests must be at least 8 years of age to join the hiking tour.",
            "★ Pregnant guests are not permitted to participate due to safety concerns.",
            "★ These entry reservations are non-refundable.",
            "Prepare for a 2-mile round-trip hike. Bring plenty of water.",
            "The general guidelines for visiting Antelope Canyon:\n1.Bottled water is allowed.\n2.No bags are allowed on the walking tour. Please leave all bags in your vehicle.\n3.Phones and standard cameras are allowed.\n4.Tripods, monopods, large camera equipment, and flash/light equipment are generally NOT permitted.\n\nPlease note that rules may vary slightly depending on the canyon and tour operator. Final instructions will be provided by the guide on site.",
            "If you can't find the check-in location, call: 928-693-9293",
        ],
        "prepare_steps": [
            {"label": "Pay the permit fee using the provided payment link",
             "url":   "https://fareharbor.com/embeds/book/navajonationparks/items/691331/calendar/2026/01/",
             "note":  "For all guests, please keep your payment receipt for check-in. Same-day Lower Antelope or Canyon X receipts can waive the Upper Antelope permit fee. If we supplied your tickets, we can provide the receipt — just let us know."},
        ],
    },
    "lower_antelope_kens": {
        "label":            "Lower Antelope Canyon – Ken's Tours",
        "sms_label":        "Lower Antelope Canyon Tour",
        "abbr":             "L-KT",
        "checkin_location": "Ken's Tours, Indian Rte 222, Page, AZ 86040",
        "maps_url":         "https://maps.app.goo.gl/ZU25jjWDLPGVbKau9",
        "location_photo":   "https://goo.gl/maps/q5tH4CB2LFnNPk2w6",
        "extra_notes": [
            "★ These entry reservations are non-refundable.",
            "The general guidelines for visiting Antelope Canyon:\n1.Bottled water is allowed.\n2.No bags are allowed on the walking tour. Please leave all bags in your vehicle.\n3.Phones and standard cameras are allowed.\n4.Tripods, monopods, large camera equipment, and flash/light equipment are generally NOT permitted.\n\nPlease note that rules may vary slightly depending on the canyon and tour operator. Final instructions will be provided by the guide on site.",
        ],
        "prepare_steps": [],
    },
    "lower_antelope_dixie": {
        "label":            "Lower Antelope Canyon – Dixie's Tours",
        "sms_label":        "Lower Antelope Canyon Tour",
        "abbr":             "L-DX",
        "checkin_location": "Dixie's Lower Antelope Canyon Tours, Indian Rte 222, Page, AZ 86040",
        "maps_url":         "https://goo.gl/maps/BbaUrHrV3aa5Wiw59",
        "location_photo":   "https://goo.gl/maps/QJ28NgUR8iSCf9AC7",
        "extra_notes": [
            "★ These entry reservations are non-refundable.",
            "The general guidelines for visiting Antelope Canyon:\n1.Bottled water is allowed.\n2.No bags are allowed on the walking tour. Please leave all bags in your vehicle.\n3.Phones and standard cameras are allowed.\n4.Tripods, monopods, large camera equipment, and flash/light equipment are generally NOT permitted.\n\nPlease note that rules may vary slightly depending on the canyon and tour operator. Final instructions will be provided by the guide on site.",
        ],
        "prepare_steps": [],
    },
    "canyon_x": {
        "label":            "Antelope Canyon X – Taadidiin Tours",
        "sms_label":        "Canyon X Tour",
        "abbr":             "X-TT",
        "checkin_location": "Antelope Canyon X by Taadidiin Tours, MP 308 SR 98, Page, AZ 86040",
        "maps_url":         "https://goo.gl/maps/pzJmUPtykxCDzUi97",
        "location_photo":   "https://goo.gl/maps/FyBq5gGTs9ZcKebu9",
        "extra_notes": [
            "No entry for children who do not have their own car seat for children under 8 years of age, under 4'9\" (145cm), or under 80 lbs (36.3kg).",
            "The general guidelines for visiting Antelope Canyon:\n1.Bottled water is allowed.\n2.No bags are allowed on the walking tour. Please leave all bags in your vehicle.\n3.Phones and standard cameras are allowed.\n4.Tripods, monopods, large camera equipment, and flash/light equipment are generally NOT permitted.\n\nPlease note that rules may vary slightly depending on the canyon and tour operator. Final instructions will be provided by the guide on site.",
        ],
        "prepare_steps": [],
    },
    "rattlesnake_aact": {
        "label":            "Rattlesnake Canyon Tour – The Adventurous Group",
        "sms_label":        "Rattlesnake Canyon Tour",
        "abbr":             "R-AA",
        "checkin_location": "Adventurous Antelope Canyon, Highway 98 Road & Milepost 302, Page, AZ 86040",
        "maps_url":         "https://maps.app.goo.gl/hWXU2JSLSphMda529",
        "location_photo":   "https://maps.app.goo.gl/tZttDC6G3jctLC8E7",
        "extra_notes": [
            "★ Minimum age 8. Guests must be at least 8 years of age to join the walking tour.",
            "★ Pregnant guests are not permitted to participate due to safety concerns.",
            "The general guidelines for visiting Antelope Canyon:\n1.Bottled water is allowed.\n2.No bags are allowed on the walking tour. Please leave all bags in your vehicle.\n3.Phones and standard cameras are allowed.\n4.Tripods, monopods, large camera equipment, and flash/light equipment are generally NOT permitted.\n\nPlease note that rules may vary slightly depending on the canyon and tour operator. Final instructions will be provided by the guide on site.",
        ],
        "prepare_steps": [],
    },
}

# ── Token ─────────────────────────────────────────────────────────────────────
def make_token(record_id: int, email: str, service_date: str) -> str:
    if service_date:
        try:
            sd = datetime.strptime(service_date, "%Y-%m-%d")
            expires = int(datetime(sd.year, sd.month, sd.day, 23, 59, 59, tzinfo=_LA).timestamp())
        except ValueError:
            expires = int(time.time()) + 7 * 86400
    else:
        expires = int(time.time()) + 7 * 86400
    payload = f"{record_id}|{email}|{expires}"
    sig = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{record_id}:{expires}:{sig}".encode()).decode()


def confirm_url(token: str, src: str = "email") -> str:
    return f"{CONFIRM_BASE_URL}/confirm/tickets?token={token}&src={src}&npe_tix_autoyes=1"


async def verify_token(token: str, db) -> tuple[str | None, dict | None]:
    if not token:
        return "invalid", None
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        record_id_str, expires_str, sig = raw.split(":", 2)
        record_id = int(record_id_str)
        expires   = int(expires_str)
    except Exception:
        return "invalid", None
    if time.time() > expires:
        return "expired", None
    from sqlalchemy import text
    result = await db.execute(text("SELECT * FROM tickets_reminders WHERE id = :id"), {"id": record_id})
    row = result.mappings().fetchone()
    if not row:
        return "invalid", None
    row = dict(row)
    expected = hmac.new(SECRET_KEY.encode(), f"{record_id}|{row['customer_email']}|{expires}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return "invalid", None
    return None, row


# ── SMS builder ───────────────────────────────────────────────────────────────
# ── per-tour DB key helpers ──────────────────────────────────────────────────
def _tix_pertour_keys(tour_type: str) -> list[str]:
    """本 tour 的 per-tour key 全名列表（tmpl__tix__{tour}__{field}）。"""
    if not tour_type:
        return []
    return [f"tmpl__tix__{tour_type}__{f}" for f in TIX_TOUR_FIELDS]


def _tix_pt(tour_copy: dict, tour_type: str):
    """返回一个取值函数 pt(field)，从 tour_copy 里取 per-tour 字段值（空回退 ""）。"""
    prefix = f"tmpl__tix__{tour_type}__"
    def pt(field: str) -> str:
        return get_copy_value(tour_copy, prefix + field, "")
    return pt


# 方案 B：值为空 → 整行不渲染（标签不留空壳）
def _email_row(label: str, value: str, shaded: bool = False, val_style: str = "") -> str:
    """email 表格一行；value 为空则返回空串（整行不渲染）。"""
    if not str(value).strip():
        return ""
    bg = "background:#e8f0ff;" if shaded else ""
    return (
        f'<tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;{bg}">{label}</td>'
        f'<td style="padding:10px 16px;font-size:13px;{val_style}">{value}</td></tr>'
    )


def _guest_row(icon: str, inner: str, value: str) -> str:
    """guest page 一行；value 为空则整行不渲染。"""
    if not str(value).strip():
        return ""
    return f'<div class="gf-row"><span>{icon}</span><span>{inner}</span></div>'


async def build_sms(row: dict, tour_type: str, form_url: str, db=None) -> str:
    cfg       = TOUR_TYPES.get(tour_type, {})
    sms_label = cfg.get("sms_label", cfg.get("label", tour_type))
    first     = row.get("first_name", row.get("name", ""))
    checkin   = row.get("checkin_time", "")
    tour_time = row.get("tour_time", "")
    svc_date  = row.get("service_date", row.get("tour_date", ""))
    try:
        date_fmt = datetime.strptime(svc_date, "%Y-%m-%d").strftime("%B %-d, %Y")
    except ValueError:
        date_fmt = svc_date

    copy = await get_copy_many(db, TIX_KEYS)
    # 变量名以 Content Studio tmpl__global__tix_sms_body 定义为准：
    #   {name} {sms_label} {date} {checkin} {tour_time} {url}
    body = get_copy_value(copy, "tmpl__global__tix_sms_body", "")
    return render_copy(
        body,
        name=first,
        sms_label=sms_label,
        date=date_fmt,
        checkin=checkin,
        tour_time=tour_time,
        url=form_url,
    )


# ── Email builder ─────────────────────────────────────────────────────────────
async def build_email(row: dict, tour_type: str, service_date: str, form_url: str, db=None) -> str:
    cfg        = TOUR_TYPES.get(tour_type, {})
    label      = cfg.get("sms_label") or cfg.get("label", tour_type)
    first      = row.get("first_name", "")
    last       = row.get("last_name", "")
    chd        = row.get("chd_number") or row.get("order_number", "")
    cfm        = row.get("confirmation_no", "")
    pax        = row.get("no_of_pax") or row.get("quantities") or "1"
    checkin    = row.get("checkin_time", "")
    tour_time  = row.get("tour_time", "")
    # 单次 batch 查询：global + per-tour 一起取（每个 handler 只打一次 DB）
    copy           = await get_copy_many(db, TIX_KEYS + _tix_pertour_keys(tour_type))
    pt             = _tix_pt(copy, tour_type)
    checkin_loc    = pt("checkin_location") or cfg.get("checkin_location", "")
    maps_url       = pt("maps_url") or cfg.get("maps_url", "")
    location_photo = pt("location_photo") or cfg.get("location_photo", "")
    try:
        date_fmt = datetime.strptime(service_date, "%Y-%m-%d").strftime("%B %-d, %Y")
    except ValueError:
        date_fmt = service_date

    # 预赋值全部文案变量（Python ≤3.11 f-string 规则：{} 内不放复杂表达式）
    c_intro     = get_copy_value(copy, "tmpl__global__tix_email_intro", "")
    c_warning   = get_copy_value(copy, "tmpl__global__tix_email_warning", "")
    c_cta_desc  = get_copy_value(copy, "tmpl__global__tix_email_cta_desc", "")
    c_cta_btn   = escape(get_copy_value(copy, "tmpl__global__tix_email_cta_btn", ""))
    c_expiry    = get_copy_value(copy, "tmpl__global__tix_email_link_expiry", "")
    c_questions = get_copy_value(copy, "tmpl__global__tix_email_questions", "")
    c_footer    = get_copy_value(copy, "tmpl__global__tix_email_footer", "")
    c_res_weather = get_copy_value(copy, "tmpl__global__tix_email_resource_weather", "")
    c_res_photo   = get_copy_value(copy, "tmpl__global__tix_email_resource_photo", "")

    # 警告框：一行一条（与 render_form 共用同一 key）；空则整块不渲染
    warning_html = ""
    if c_warning:
        warn_lines = "".join(
            f"      {escape(ln)}<br>\n"
            for ln in c_warning.split("\n") if ln.strip()
        )
        warning_html = (
            '<div style="background:#fff5f5;border:1px solid #f5c6c6;border-radius:6px;'
            'padding:8px 14px;margin-bottom:20px;font-size:11px;color:#c0392b;line-height:1.3;">\n'
            f"{warn_lines}    </div>"
        )

    intro_html = (
        f'<p style="color:#555;line-height:1.6;margin:10px 0 20px;">{intro_esc}</p>'
        if (intro_esc := escape(c_intro)) else ""
    )
    cta_desc_html = (
        f'<p style="color:#555;line-height:1.6;margin-bottom:20px;">{ctadesc_esc}</p>'
        if (ctadesc_esc := escape(c_cta_desc)) else ""
    )
    expiry_html = (
        f'<p style="margin:10px 0 0;font-size:12px;color:#aaa;">{expiry_esc}</p>'
        if (expiry_esc := escape(c_expiry)) else ""
    )
    questions_html = (
        f'<p style="color:#999;font-size:12px;text-align:center;margin-top:16px;">{questions_esc}</p>'
        if (questions_esc := escape(c_questions)) else ""
    )
    footer_html = (
        f'<p style="color:#aaa;font-size:12px;margin:0;">{footer_esc}</p>'
        if (footer_esc := escape(c_footer)) else ""
    )

    maps_row = (
        f'<tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;background:#e8f0ff;">🗺️ Maps</td>'
        f'<td style="padding:10px 16px;font-size:13px;"><a href="{maps_url}" style="color:#1a3a5c;" target="_blank">Google Maps GPS</a></td></tr>'
    ) if maps_url else ""

    # cfm 行：与 guest page (render_form) 保持一致
    #  - skip_confirmation_no 的 tour（不需要 confirmation#）→ 该格显示 checkin_note
    #  - 其余 tour → 显示 confirmation# 号码
    _ckn_email = get_copy_value(copy, "tmpl__global__tix_guest_checkin_note", "") or cfg.get("checkin_note", "")
    if cfg.get("skip_confirmation_no"):
        ckn_esc = escape(_ckn_email)
        cfm_row = (
            f'<tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;">🔖 Check-in</td>'
            f'<td style="padding:10px 16px;font-size:13px;">{ckn_esc}</td></tr>'
        )
    else:
        cfm_row = (
            f'<tr><td style="padding:10px 16px;font-size:13px;font-weight:bold;color:#666;">🔖 Confirmation#</td>'
            f'<td style="padding:10px 16px;font-size:13px;font-weight:bold;">{cfm}</td></tr>'
        )

    # 方案 B：值为空的行整行不渲染
    pax_val   = f"{pax} Guest(s)" if str(pax).strip() else ""
    row_chd     = _email_row("📋 CHD#", chd, shaded=True)
    row_pax     = _email_row("👥 Party Size", pax_val, shaded=True)
    row_date    = _email_row("📅 Service Date", date_fmt, val_style="font-weight:bold;color:#1a3a5c;")
    row_checkin = _email_row("⏰ Check-in Time", checkin, shaded=True, val_style="font-weight:bold;")
    row_ttime   = _email_row("🎡 Tour Time", tour_time, val_style="font-weight:bold;")
    row_loc     = _email_row("📍 Check-in Location", checkin_loc, shaded=True)

    # resource_html：链接文字接 DB（weather/photo），URL 仍来自 per-tour cfg
    resource_html = ""
    if location_photo and (c_res_weather or c_res_photo):
        photo_link = (
            f'&nbsp;&nbsp;<a href="{location_photo}" style="color:#1a3a5c;margin-left:16px;" target="_blank">{escape(c_res_photo)}</a>'
            if c_res_photo else ""
        )
        weather_link = (
            f'<a href="https://www.timeanddate.com/worldclock/usa/page" style="color:#1a3a5c;" target="_blank">{escape(c_res_weather)}</a>'
            if c_res_weather else ""
        )
        resource_html = (
            f'<p style="font-size:12px;margin-top:8px;text-align:center;">{weather_link}{photo_link}</p>'
        )


    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f8;padding:30px 0;"><tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">
  <tr><td style="background:#1a3a5c;border-radius:12px 12px 0 0;padding:32px;text-align:center;">
    <img src="https://nationalparkexpress.com/wp-content/uploads/2026/03/image002.png" style="width:120px;height:auto;margin-bottom:12px;" />
    <h1 style="color:#fff;margin:10px 0 4px;font-size:22px;">Tickets Reminder &amp; Reconfirmation</h1>
    <p style="color:#a8c4e0;margin:0;font-size:14px;">{label}</p>
  </td></tr>
  <tr><td style="background:#fff;padding:32px;">
    <p style="font-size:16px;">Hi <strong>{first} {last}</strong>,</p>
    {intro_html}
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f5ff;border-radius:8px;overflow:hidden;margin-bottom:20px;">
      {row_chd}
      {cfm_row}
      {row_pax}
      {row_date}
      {row_checkin}
      {row_ttime}
      {row_loc}
      {maps_row}
    </table>
    {warning_html}
    {cta_desc_html}
    <div style="text-align:center;margin:28px 0;">
      <a href="{form_url}" style="display:inline-block;background:#1a3a5c;color:#fff;text-decoration:none;padding:16px 44px;border-radius:8px;font-size:16px;font-weight:bold;">{c_cta_btn}</a>
      {expiry_html}
    </div>
    {resource_html}
    {questions_html}
  </td></tr>
  <tr><td style="background:#f0f0f0;border-radius:0 0 12px 12px;padding:16px;text-align:center;">
    {footer_html}
  </td></tr>
</table></td></tr></table></body></html>"""


# ── Staff notification email ───────────────────────────────────────────────────
async def build_staff_email(row: dict, tour_type: str, notes: str, db=None) -> tuple[str, str]:
    cfg      = TOUR_TYPES.get(tour_type, {})
    label    = cfg.get("label") or cfg.get("sms_label", tour_type)  # internal: show supplier
    svc_date = str(row.get("service_date", ""))
    try:
        date_str = datetime.strptime(svc_date, "%Y-%m-%d").strftime("%B %-d, %Y")
    except ValueError:
        date_str = svc_date
    notes_html = notes.replace("\n", "<br>") if notes else "-"
    chd        = row.get("chd_number", "")

    # 预赋值 row 字段（Python ≤3.11：{} 内不放带引号的 .get() 调用）
    cfm_no     = row.get("confirmation_no", "")
    first      = row.get("first_name", "")
    last       = row.get("last_name", "")
    email      = row.get("customer_email", "")
    phone      = row.get("phone", "")
    pax        = row.get("no_of_pax", "")

    copy = await get_copy_many(db, TIX_KEYS)
    subj_tmpl = get_copy_value(copy, "tmpl__global__tix_staffmail_subject", "")
    subject   = render_copy(subj_tmpl, chd=chd, label=label, date=date_str)
    title     = get_copy_value(copy, "tmpl__global__tix_staffmail_title", "")

    body = f"""<div style='font-family:Arial,sans-serif;max-width:600px;'>
    <h2 style='color:#1a5276;'>{title}</h2>
    <table style='width:100%;border-collapse:collapse;border:1px solid #ddd;'>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;'>Tour</td><td style='padding:8px 12px;'>{label}</td></tr>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;'>Service Date</td><td style='padding:8px 12px;'>{date_str}</td></tr>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;'>CHD#</td><td style='padding:8px 12px;'>{chd}</td></tr>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;'>Confirmation#</td><td style='padding:8px 12px;'>{cfm_no}</td></tr>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;'>Guest</td><td style='padding:8px 12px;'>{first} {last}</td></tr>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;'>Email</td><td style='padding:8px 12px;'>{email}</td></tr>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;'>Phone</td><td style='padding:8px 12px;'>{phone}</td></tr>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;'>Party Size</td><td style='padding:8px 12px;'>{pax}</td></tr>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;'>Response</td><td style='padding:8px 12px;font-size:22px;font-weight:bold;color:#27ae60;'>YES</td></tr>
    <tr><td style='padding:8px 12px;font-weight:bold;background:#f0f0f0;vertical-align:top;'>Notes</td><td style='padding:8px 12px;'>{notes_html}</td></tr>
    </table></div>"""
    return subject, body


# ── Guest page CSS ────────────────────────────────────────────────────────────
GUEST_CSS = """*{box-sizing:border-box;margin:0;padding:0;}body{background:#f0f4f8;font-family:"Helvetica Neue",Arial,sans-serif;color:#333;padding:16px;}
.gf-wrap{max-width:580px;margin:0 auto;padding:10px 0 40px;}.gf-card{background:#fff;border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,.10);overflow:hidden;}
.gf-header{background:#1a3a5c;color:#fff;padding:26px;text-align:center;}.gf-header h1{font-size:20px;margin:8px 0 4px;}
.gf-tour-badge{background:rgba(255,255,255,.15);border-radius:6px;padding:5px 14px;display:inline-block;font-size:13px;font-weight:bold;margin-bottom:6px;}
.gf-date{font-size:17px;font-weight:bold;color:#fff;margin:4px 0;}.gf-meta{font-size:12px;color:#a8c4e0;margin-top:4px;}
.gf-pickup-box{padding:16px 22px;font-size:13px;line-height:1.6;background:#eef6ff;border-bottom:1px solid #d0e6ff;}
.gf-box-title{font-weight:bold;color:#1a3a5c;margin-bottom:10px;}
.gf-row{display:flex;gap:10px;align-items:flex-start;margin-bottom:8px;}.gf-row span:first-child{flex-shrink:0;width:20px;text-align:center;}
.gf-pickup-box a{color:#1a3a5c;font-weight:bold;}
.gf-section{padding:18px 22px;border-bottom:1px solid #eee;}.gf-section h2{font-size:15px;color:#1a3a5c;margin-bottom:12px;}.gf-opt{font-weight:normal;font-size:12px;color:#aaa;}
.gf-reminders{background:#f9f9f9;border-top:1px solid #eee;padding:14px 22px;font-size:13px;}.gf-reminders ul{padding-left:18px;line-height:1.9;color:#555;}.gf-reminders li{white-space:pre-line;}
.gf-section textarea{width:100%;border:1px solid #ddd;border-radius:8px;padding:10px;font-size:13px;resize:vertical;}
.gf-submit{padding:18px 22px;text-align:center;}.gf-btn{width:100%;background:#1a3a5c;color:#fff;border:none;padding:15px;border-radius:10px;font-size:16px;font-weight:bold;cursor:pointer;}.gf-btn:hover{background:#0f2440;}
.gf-small{font-size:12px;color:#888;margin-top:10px;}.gf-small a{color:#1a3a5c;}
.gf-error{background:#f8d7da;color:#721c24;border:1px solid #f5c6cb;border-radius:8px;padding:12px 18px;margin:10px 22px;font-size:13px;}
.gf-info{background:#d4edda;color:#155724;border-radius:8px;padding:10px 18px;margin:10px 22px;font-size:13px;}
.gf-card.gf-thanks{text-align:center;padding:40px 30px;}.gf-thanks h1{color:#1a3a5c;margin-bottom:12px;}.gf-thanks p{color:#555;margin-bottom:8px;line-height:1.7;}
.gf-tz-note{font-size:11px;color:#c0392b;padding:2px 0 6px 30px;}.gf-note-red{color:#c0392b;font-size:11px;}
.gf-map-link{color:#1a3a5c;font-weight:bold;font-size:13px;}.gf-sub-note{font-size:11px;color:#555;}
.gf-prepare-box{padding:16px 22px;background:#eaf4ff;border-bottom:1px solid #b3d9ff;}
.gf-prepare-intro{font-size:13px;color:#555;margin:8px 0 12px;line-height:1.6;}
.gf-prepare-list{padding-left:18px;font-size:13px;line-height:2.0;color:#1a3a5c;}
.gf-prep-link{color:#1a3a5c;font-weight:bold;font-size:12px;text-decoration:underline;}
.gf-resource-links{margin-top:10px;font-size:12px;}.gf-resource-links a{color:#1a3a5c;margin-right:8px;}
@media(max-width:440px){.gf-yn-row{flex-direction:column;}}"""


# ── Guest page renderers ───────────────────────────────────────────────────────
async def render_expired(db=None) -> str:
    copy    = await get_copy_many(db, TIX_KEYS)
    title   = escape(get_copy_value(copy, "tmpl__global__tix_expired_title", ""))
    message = escape(get_copy_value(copy, "tmpl__global__tix_expired_message", ""))
    # message 多行：DB 存真实换行，用 white-space:pre-line 渲染（与 extra_notes 一致）
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Link Expired</title>
    <style>body{{font-family:Arial,sans-serif;background:#f0f4f8;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;}}
    .box{{background:#fff;border-radius:16px;padding:40px;max-width:480px;text-align:center;box-shadow:0 4px 20px rgba(0,0,0,.1);}}
    h1{{color:#1a3a5c;}} p{{color:#555;line-height:1.7;white-space:pre-line;}} a{{color:#1a3a5c;font-weight:bold;}}</style></head>
    <body><div class="box"><div style="font-size:56px;margin-bottom:16px;">⏰</div><h1>{title}</h1>
    <p>{message}</p>
    </div></body></html>"""


async def render_thanks(row: dict, db=None) -> str:
    first = escape(row.get("first_name", ""))
    try:
        date_fmt = datetime.strptime(str(row.get("service_date", "")), "%Y-%m-%d").strftime("%A, %B %-d, %Y")
    except ValueError:
        date_fmt = str(row.get("service_date", ""))

    copy = await get_copy_many(db, TIX_KEYS)
    # 仅 thanks_message（原 407 行）接线；footer 联系方式 spec 未列，保持硬编码
    msg_tmpl  = get_copy_value(copy, "tmpl__global__tix_thanks_message", "")
    thanks_msg = escape(render_copy(msg_tmpl, date=date_fmt))
    thanks_html = (
        f'<p style="white-space:pre-line;">{thanks_msg}</p>' if thanks_msg else ""
    )
    return f"""<!DOCTYPE html><html lang="en"><head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Tickets Reconfirmation – National Park Express</title>
    <style>{GUEST_CSS}</style></head><body>
    <div class="gf-wrap"><div class="gf-card gf-thanks">
    <div style="font-size:56px;margin-bottom:16px;">✅</div>
    <h1>Thank You, {first}!</h1>
    {thanks_html}
    <p class="gf-small">Questions? <a href="mailto:reservations@nationalparkexpress.com">reservations@nationalparkexpress.com</a> | 702-948-4190</p>
    </div></div></body></html>"""


async def render_form(row: dict, cfg: dict, token: str, error_msg: str = "", already: bool = False, db=None) -> str:
    try:
        date_fmt = datetime.strptime(str(row.get("service_date", "")), "%Y-%m-%d").strftime("%A, %B %-d, %Y")
    except ValueError:
        date_fmt = str(row.get("service_date", ""))
    pax       = int(row.get("no_of_pax") or 1)
    tour_slug = escape(cfg.get("sms_label") or cfg.get("label", ""))
    chd       = escape(row.get("chd_number", ""))
    cfm_no    = escape(row.get("confirmation_no", ""))
    first     = escape(row.get("first_name", ""))
    last      = escape(row.get("last_name", ""))
    checkin   = escape(row.get("checkin_time", ""))
    tourtime  = escape(row.get("tour_time", ""))
    notes_val = escape(row.get("reschedule_notes") or "")

    tour_type = row.get("tour_type", "")

    # ── DB 文案：单次 batch 查询（global + per-tour 一起取）──
    copy      = await get_copy_many(db, TIX_KEYS + _tix_pertour_keys(tour_type))
    pt        = _tix_pt(copy, tour_type)

    # per-tour 字段：DB 优先，cfg 作最终空回退
    db_checkin_loc = pt("checkin_location") or cfg.get("checkin_location", "")
    db_maps_url    = pt("maps_url")         or cfg.get("maps_url", "")
    db_photo       = pt("location_photo")   or cfg.get("location_photo", "")
    db_extra_raw   = pt("extra_notes")  # DB 存纯文本，真实换行分隔

    # 全局文案预赋值（Python ≤3.11：{} 内不放复杂表达式）
    c_warning      = get_copy_value(copy, "tmpl__global__tix_email_warning", "")
    c_cfm_note     = escape(get_copy_value(copy, "tmpl__global__tix_guest_cfm_note", ""))
    # checkin_note：skip_confirmation_no 的 tour 用；global key，cfg 作最终回退
    _ckn           = get_copy_value(copy, "tmpl__global__tix_guest_checkin_note", "") or cfg.get("checkin_note", "")
    db_checkin_note = escape(_ckn)
    c_already      = escape(get_copy_value(copy, "tmpl__global__tix_guest_already_info", ""))
    c_checkbox     = escape(get_copy_value(copy, "tmpl__global__tix_guest_checkbox_text", ""))
    c_submit       = escape(get_copy_value(copy, "tmpl__global__tix_guest_submit_btn", ""))
    c_thanks_small = escape(get_copy_value(copy, "tmpl__global__tix_guest_thanks_small", ""))
    c_prep_title   = escape(get_copy_value(copy, "tmpl__global__tix_guest_prepare_title", ""))
    c_prep_intro   = escape(get_copy_value(copy, "tmpl__global__tix_guest_prepare_intro", ""))
    c_general      = get_copy_value(copy, "tmpl__global__tix_general_reminder", "")
    c_res_weather  = get_copy_value(copy, "tmpl__global__tix_email_resource_weather", "")
    c_res_photo    = get_copy_value(copy, "tmpl__global__tix_email_resource_photo", "")

    # 警告框两行：一行一条（与 email 共用 tmpl__global__tix_email_warning）
    warn_lines = [ln for ln in c_warning.split("\n") if ln.strip()]
    warn_line1 = escape(warn_lines[0]) if len(warn_lines) >= 1 else ""
    warn_line2 = escape(warn_lines[1]) if len(warn_lines) >= 2 else ""
    late_checkin_html = (
        f'<br><span class="gf-note-red">{warn_line1}</span>' if warn_line1 else ""
    )
    az_tz_html = (
        f'<div class="gf-tz-note">{warn_line2}</div>' if warn_line2 else ""
    )

    checkin_loc_esc = escape(db_checkin_loc)

    maps_link = ""
    if db_maps_url:
        maps_link = f'<div class="gf-row"><span></span><a href="{db_maps_url}" target="_blank" class="gf-map-link">🗺️ Google Maps GPS</a></div>'

    # prepare_steps：不接 DB（独立结构化 UI），维持 cfg 硬编码；仅标题/intro 接 DB
    prepare_html = ""
    if cfg.get("prepare_steps"):
        items = ""
        for s in cfg["prepare_steps"]:
            s_note = s.get("note")
            s_label = escape(s["label"])
            s_url = s["url"]
            note_esc = escape(s_note) if s_note else ""
            note_html = f'<br><span style="font-size:12px;color:#555;line-height:1.6;">{note_esc}</span>' if s_note else ""
            items += f'<li>{s_label}&nbsp;<a href="{s_url}" target="_blank" class="gf-prep-link">→ Open Link</a>{note_html}</li>'
        prepare_html = f"""
      <div class="gf-prepare-box">
        <div class="gf-box-title">{c_prep_title}</div>
        <p class="gf-prepare-intro">{c_prep_intro}</p>
        <ul class="gf-prepare-list">{items}</ul>
      </div>"""

    # ── Box 1「Know Before You Go」← tmpl__global__tix_general_reminder（9 tour 共用）──
    general_html = ""
    if c_general:
        gen_lis = "".join(
            f"<li>{escape(ln)}</li>"
            for ln in c_general.split("\n") if ln.strip()
        )
        if gen_lis:
            general_html = f"""
      <div class="gf-reminders">
        <div class="gf-box-title">📌 Know Before You Go</div>
        <ul>{gen_lis}</ul>
      </div>"""

    # ── Box 2「Tour-Specific Information」← per-tour extra_notes + res_block ──
    tourspec_html = ""
    if db_extra_raw:
        extra_lines = [ln for ln in db_extra_raw.split("\n") if ln.strip()]
        lis = "".join(
            f'<li style="color:#c0392b;font-weight:bold;">{escape(n)}</li>' if n.startswith("★")
            else f"<li>{escape(n)}</li>"
            for n in extra_lines
        )
        # res_block 跟 tour 专属字段走，归入本框
        res_links = ""
        if db_maps_url:
            res_links += f'&nbsp;&nbsp;<a href="{db_maps_url}" target="_blank">🗺️ Google Maps GPS</a>'
        if db_photo and c_res_photo:
            res_links += f'&nbsp;&nbsp;<a href="{db_photo}" target="_blank">{escape(c_res_photo)}</a>'
        weather_txt = escape(c_res_weather)
        res_block = (
            f'<div class="gf-resource-links"><a href="https://www.timeanddate.com/worldclock/usa/page" target="_blank">{weather_txt}</a>{res_links}</div>'
            if (res_links or weather_txt) else ""
        )
        tourspec_html = f"""
      <div class="gf-reminders">
        <div class="gf-box-title">Tour-Specific Information</div>
        <ul>{lis}</ul>{res_block}
      </div>"""

    reminders_html = general_html + tourspec_html

    error_html   = f'<div class="gf-error">{escape(error_msg)}</div>' if error_msg else ""
    already_html = f'<div class="gf-info">{c_already}</div>' if already else ""

    # cfm 行：
    #  - skip_confirmation_no 的 tour（不需要 confirmation#）→ 显示 checkin_note（global key，cfg 回退）
    #  - 其余 tour → 显示 confirmation# + 全局 cfm_note
    #    （对照 settings_templates.html:478 label 与 :1392 预览位置确认）
    if cfg.get("skip_confirmation_no"):
        cfm_row_html = _guest_row("🔖", db_checkin_note, db_checkin_note)
    else:
        _cfm_inner = (
            f'Confirmation#: <strong>{cfm_no}</strong>'
            f'<br><span class="gf-sub-note">{c_cfm_note}</span>'
        )
        cfm_row_html = _guest_row("🔖", _cfm_inner, cfm_no)

    # submit 按钮：空回退保底（与既有前端 v('...') || 'Submit' 一致，见 settings_templates.html:1348）
    submit_btn_txt = c_submit or "Submit"

    # 方案 B：check-in 框内各行，值为空则整行不渲染
    loc_row_html = _guest_row("📍", f"<strong>Location:</strong> {checkin_loc_esc}", checkin_loc_esc)
    # 时间行：check-in 与 tour time 任一有值才渲染，缺的一半不显示标签
    _t_parts = []
    if checkin:
        _t_parts.append(f"Check-in: <strong>{checkin}</strong>")
    if tourtime:
        _t_parts.append(f"Tour: <strong>{tourtime}</strong>")
    _t_inner = " &nbsp;|&nbsp; ".join(_t_parts)
    time_row_html = _guest_row("⏰", f"{_t_inner}{late_checkin_html}", _t_inner)

    return f"""<!DOCTYPE html><html lang="en"><head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Tickets Reconfirmation – National Park Express</title>
    <style>{GUEST_CSS}</style></head><body>
    <div class="gf-wrap"><div class="gf-card">
      <div class="gf-header">
        <img src="https://nationalparkexpress.com/wp-content/uploads/2026/03/image002.png" style="width:100px;height:auto;" />
        <div class="gf-tour-badge">{tour_slug}</div>
        <h1>Tickets Reconfirmation</h1>
        <div class="gf-date">{date_fmt}</div>
        <div class="gf-meta">CHD# {chd} &nbsp;·&nbsp; {first} {last} &nbsp;·&nbsp; Party of {pax}</div>
      </div>
      <div class="gf-pickup-box">
        <div class="gf-box-title">Your Check-in Information</div>
        {loc_row_html}
        {maps_link}
        {time_row_html}
        {az_tz_html}
        {cfm_row_html}
      </div>
      {prepare_html}{reminders_html}{error_html}{already_html}
      <form method="post">
        <input type="hidden" name="token" value="{token}">
        <input type="hidden" name="npe_tix_submit" value="1">
        <input type="hidden" name="confirmation" value="yes">
        <div class="gf-section">
          <h2>📝 Notes <span class="gf-opt">(optional)</span></h2>
          <textarea name="notes" rows="3" placeholder="Any questions or special requests...">{notes_val}</textarea>
        </div>
        <div class="gf-submit">
          <p style="font-size:13px;color:#555;margin-bottom:12px;">{c_checkbox}</p>
          <button type="submit" class="gf-btn">{submit_btn_txt}</button>
          <p class="gf-small">{c_thanks_small}</p>
        </div>
      </form>
    </div></div></body></html>"""
