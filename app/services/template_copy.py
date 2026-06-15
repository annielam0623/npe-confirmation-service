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

    # 待接入 · lunch / mtlv
    # "tmpl__global__tc_guest_lunch_title",
    # "tmpl__global__tc_guest_lunch_hint",
    # "tmpl__global__tc_guest_lunch_default",
    # "tmpl__global__tc_guest_mtlv_title",
    # "tmpl__global__tc_guest_mtlv_locked_cancelled",
    # "tmpl__global__tc_guest_mtlv_locked_confirmed",

    # 待接入 · 其它
    # "tmpl__global__tc_guest_last_update_label",
    # "tmpl__global__tc_guest_date_modal_title",
    # "tmpl__global__tc_guest_date_modal_desc",
]
