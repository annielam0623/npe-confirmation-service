"""
app/services/template_copy.py

Reads editable template text from the settings table — DB is the single
runtime source of truth. Hardcoded defaults at each call site act as the
fallback when a key is missing/empty or the DB is unreachable.

Key naming convention:
  tmpl__global__{field}                  — shared across all modules
  tmpl__tc__{tour_type}__{field}         — Tour Confirmation per product
  tmpl__tix__{tour_type}__{field}        — Tickets Reminder per product
"""
from __future__ import annotations
import re
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_copy_many(db: AsyncSession, keys: list[str]) -> dict[str, str]:
    """
    Batch-fetch multiple keys in one query. Returns dict key→value
    (full tmpl__ key names; missing keys map to "").
    On any DB error, returns all keys as "" so callers fall back to
    their hardcoded defaults via get_copy_value().
    """
    if not keys:
        return {}
    try:
        placeholders = ", ".join(f":k{i}" for i in range(len(keys)))
        result = await db.execute(
            text(f"SELECT key, value FROM settings WHERE key IN ({placeholders})"),
            {f"k{i}": v for i, v in enumerate(keys)},
        )
        found = {r[0]: r[1] for r in result.fetchall()}
    except Exception:
        found = {}
    return {k: (found.get(k) or "") for k in keys}


# ── helper：从 get_copy_many 结果取值，空/缺回退 default ──
def get_copy_value(copy: dict, key: str, default: str = "") -> str:
    """Return copy[key] if present and non-empty, else default."""
    return copy.get(key) or default


# ── helper：把文案里的 {var} 占位符替换成实际值 ──
# 只替换已传入的命名变量；未知 {foo} 原样保留；裸花括号不报错。
# 用于含动态值（如 {qty}）的文案字段，替换后再塞进外层 f-string，
# 外层不会二次解析，避免 ≤3.11 f-string 内反斜杠/引号的雷。
def render_copy(text: str, **vals) -> str:
    if not text:
        return ""
    return re.sub(r"\{(\w+)\}", lambda m: str(vals.get(m.group(1), m.group(0))), text)


# ── Content Studio key 清单（集中管理；分批激活靠注释，名字不绑版本）──
# TC Guest Page：每接入一批就解开对应注释，调用处永远用 TC_GUEST_KEYS。
TC_GUEST_KEYS = [
    # 基础静态文案（已接入）
    "tmpl__global__tc_guest_already_submitted",
    "tmpl__global__tc_guest_notes_title",
    "tmpl__global__tc_guest_notes_placeholder",
    "tmpl__global__tc_guest_submit_btn",
    "tmpl__global__tc_guest_footer_thanks",

    # pickup（已接入）
    "tmpl__global__tc_guest_pickup_box_title",
    "tmpl__global__tc_guest_pu_sms_head",
    "tmpl__global__tc_guest_pu_sms_text",
    "tmpl__global__tc_guest_pu_wrong_number",
    "tmpl__global__tc_guest_pu_head_head",
    "tmpl__global__tc_guest_pu_depart_warn",
    "tmpl__global__tc_guest_pu_checkin_head",
    "tmpl__global__tc_guest_pu_checkin_text",
    "tmpl__global__tc_guest_pu_notsure_head",

    # lunch / mtlv（已接入）
    "tmpl__global__tc_guest_lunch_title",
    "tmpl__global__tc_guest_lunch_hint",
    "tmpl__global__tc_guest_lunch_default",
    "tmpl__global__tc_guest_mtlv_title",
    "tmpl__global__tc_guest_mtlv_hint",
    "tmpl__global__tc_guest_mtlv_bullet_1",
    "tmpl__global__tc_guest_mtlv_bullet_2",
    "tmpl__global__tc_guest_mtlv_locked_cancelled",
    "tmpl__global__tc_guest_mtlv_locked_confirmed",

    # 其它（已接入）
    "tmpl__global__tc_guest_last_update_label",
    "tmpl__global__tc_guest_date_modal_title",
    "tmpl__global__tc_guest_date_modal_desc",
]


# ── Tickets Reminder：全局 key 清单（per-tour key 靠 f"tmpl__tix__{tour}__{field}"
#    动态拼接，不进此列表，与 TC_GUEST_KEYS 只列 global 的模式一致）──
TIX_KEYS = [
    # Email（已 seed）
    "tmpl__global__tix_email_intro",
    "tmpl__global__tix_email_cta_desc",
    "tmpl__global__tix_email_link_expiry",
    "tmpl__global__tix_email_footer",
    "tmpl__global__tix_email_warning",       # email + guest form 共用
    # SMS（已 seed）
    "tmpl__global__tix_sms_body",
    # Guest Page（已 seed）
    "tmpl__global__tix_guest_cfm_note",
    "tmpl__global__tix_guest_already_info",
    "tmpl__global__tix_guest_checkbox_text",
    "tmpl__global__tix_guest_submit_btn",
    "tmpl__global__tix_guest_thanks_small",

    # ── 本次新建（migrate_v17）──
    # Email
    "tmpl__global__tix_email_cta_btn",
    "tmpl__global__tix_email_resource_weather",
    "tmpl__global__tix_email_resource_photo",
    "tmpl__global__tix_email_questions",
    # Guest Page
    "tmpl__global__tix_guest_prepare_title",
    "tmpl__global__tix_guest_prepare_intro",
    "tmpl__global__tix_guest_checkin_note",   # skip_confirmation_no 的 tour 用（email + guest page 共用）
    # Global
    "tmpl__global__tix_general_reminder",
    # 系统页
    "tmpl__global__tix_thanks_message",
    "tmpl__global__tix_expired_title",
    "tmpl__global__tix_expired_message",
    # Staff mail（labels 留代码不进 DB）
    "tmpl__global__tix_staffmail_subject",
    "tmpl__global__tix_staffmail_title",
]

# per-tour 字段（DB 读，靠 tour_type 拼 key）
TIX_TOUR_FIELDS = [
    "checkin_location",
    "maps_url",
    "location_photo",
    "extra_notes",
]
