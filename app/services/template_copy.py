"""
app/services/template_copy.py

Provides get_copy() — reads editable template text from the settings table.
Results are cached in-memory per process. Call invalidate_cache() after any save.

Key naming convention:
  tmpl__global__{field}                  — shared across all modules
  tmpl__tc__{tour_type}__{field}         — Tour Confirmation per product
  tmpl__tix__{tour_type}__{field}        — Tickets Reminder per product
"""
from __future__ import annotations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_cache: dict[str, str] = {}


async def get_copy(db: AsyncSession, key: str, default: str = "") -> str:
    """
    Return the value for settings key, falling back to default.
    Result is cached for the lifetime of the process.
    """
    if key in _cache:
        return _cache[key]
    try:
        result = await db.execute(
            text("SELECT value FROM settings WHERE key = :k"), {"k": key}
        )
        row = result.fetchone()
        value = row[0] if row else default
    except Exception:
        value = default
    _cache[key] = value
    return value


async def get_copy_many(db: AsyncSession, keys: list[str]) -> dict[str, str]:
    """Batch-fetch multiple keys in one query. Returns dict key→value."""
    missing = [k for k in keys if k not in _cache]
    if missing:
        placeholders = ", ".join(f":k{i}" for i in range(len(missing)))
        result = await db.execute(
            text(f"SELECT key, value FROM settings WHERE key IN ({placeholders})"),
            {f"k{i}": v for i, v in enumerate(missing)},
        )
        found = {r[0]: r[1] for r in result.fetchall()}
        for k in missing:
            _cache[k] = found.get(k, "")
    return {k: _cache.get(k, "") for k in keys}


def invalidate_cache(key: str | None = None):
    """
    Clear one key or the entire cache.
    Call after any POST /api/template-settings/save.
    """
    if key:
        _cache.pop(key, None)
    else:
        _cache.clear()
