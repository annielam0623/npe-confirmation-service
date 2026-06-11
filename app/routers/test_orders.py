"""
app/routers/test_orders.py
Test-order deletion — admin only.

匹配（OR，任一命中即列出）：
  - order_number / chd_number 只接受 CHDTESTORDER 前缀（真实 CHD 单按订单号永远删不掉）
  - phone 可匹配任意单 —— 用来清“规则之前的脏数据”（那批旧测试单没前缀，只能靠电话捞）

删除范围：
  按 order_number 删 6 张：bookings, send_log, booking_notes,
                           checkin_log, broadcast_recipients, short_links
  按 chd_number  删 1 张：tickets_reminders
  保留不动：activity_log（操作日志留痕）

安全护栏（服务端，不信前端）：
  - TESTORDER 前缀的单：直接放行
  - 非前缀的单（phone 捞出的旧脏单）：必须提交 phone，且库里该单 phone == 提交值才放行
    => 即便绕过前端直接调接口，也只能删“与提交电话同号”的单，删不掉任意真实单
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import require_admin

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

TEST_PREFIX = "CHDTESTORDER"

# 按 order_number 删的表
ORDER_TABLES = [
    "bookings",
    "send_log",
    "booking_notes",
    "checkin_log",
    "broadcast_recipients",
    "short_links",
]
# 按 chd_number 删的表
CHD_TABLES = [
    "tickets_reminders",
]


def _is_test_order(on: str) -> bool:
    return bool(on) and on.upper().startswith(TEST_PREFIX)


# ── GET /admin/settings/test-orders ──────────────────────────────────────────
@router.get("/admin/settings/test-orders", response_class=HTMLResponse)
async def test_orders_page(request: Request, current_user=Depends(require_admin)):
    return templates.TemplateResponse(
        "admin/settings_test_orders.html",
        {
            "request": request,
            "current_user": current_user,
            "active_section": "settings",
            "active_page": "settings_test_orders",
        },
    )


# ── POST /api/test-orders/preview ────────────────────────────────────────────
# body: {"order": "CHDTESTORDER...", "phone": "+1702..."}  至少一个
@router.post("/api/test-orders/preview")
async def preview(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    order = (payload.get("order") or "").strip()
    phone = (payload.get("phone") or "").strip()
    if not order and not phone:
        raise HTTPException(400, "Provide an order number or a phone.")

    use_order = _is_test_order(order)   # order 条件只在 TESTORDER 前缀时生效

    def _where(order_col: str):
        conds, params = [], {}
        if use_order:
            conds.append(f"UPPER({order_col}) LIKE :order_like")
            params["order_like"] = order.upper() + "%"
        if phone:
            # 规范化比对：库里 phone 和提交值都去掉非数字再比，免疫括号/空格/横线
            conds.append("regexp_replace(phone, '[^0-9]', '', 'g') = regexp_replace(:phone, '[^0-9]', '', 'g')")
            params["phone"] = phone
        return " OR ".join(conds), params

    agg: dict[str, dict] = {}

    def _flag(on: str) -> str:
        return "test" if _is_test_order(on) else "phone"

    # 1) bookings —— 有完整资料
    w, p = _where("order_number")
    res = await db.execute(text(f"""
        SELECT order_number, first_name, last_name, phone, tour_date
        FROM bookings WHERE {w}
    """), p)
    for r in res.mappings().all():
        on = r["order_number"]
        if not on:
            continue
        agg.setdefault(on, {
            "order_number": on,
            "name": f"{r['first_name'] or ''} {r['last_name'] or ''}".strip() or "—",
            "phone": r["phone"] or "—",
            "date": str(r["tour_date"]) if r["tour_date"] else "—",
            "flag": _flag(on),
            "tables": set(),
        })["tables"].add("bookings")

    # 2) send_log —— 捞“只发过、没 bookings 行”的测试单（它有 order_number + phone）
    w, p = _where("order_number")
    res = await db.execute(text(f"""
        SELECT DISTINCT order_number, phone FROM send_log WHERE {w}
    """), p)
    for r in res.mappings().all():
        on = r["order_number"]
        if not on:
            continue
        agg.setdefault(on, {
            "order_number": on, "name": "—", "phone": r["phone"] or "—",
            "date": "—", "flag": _flag(on), "tables": set(),
        })["tables"].add("send_log")

    # 3) tickets_reminders —— 用 chd_number 当订单号，也有 phone
    w, p = _where("chd_number")
    res = await db.execute(text(f"""
        SELECT DISTINCT chd_number, phone FROM tickets_reminders WHERE {w}
    """), p)
    for r in res.mappings().all():
        on = r["chd_number"]
        if not on:
            continue
        agg.setdefault(on, {
            "order_number": on, "name": "—", "phone": r["phone"] or "—",
            "date": "—", "flag": _flag(on), "tables": set(),
        })["tables"].add("tickets_reminders")

    # 4) 其余表只用来标“命中几张表”（按已解析出的订单号回查）
    ons = list(agg.keys())
    if ons:
        for tbl in ["booking_notes", "checkin_log", "broadcast_recipients", "short_links"]:
            try:
                r = await db.execute(
                    text(f"SELECT DISTINCT order_number FROM {tbl} WHERE order_number = ANY(:ons)"),
                    {"ons": ons},
                )
                for row in r.mappings().all():
                    if row["order_number"] in agg:
                        agg[row["order_number"]]["tables"].add(tbl)
            except Exception:
                # 某张表万一不存在/无 order_number 列，不影响预览
                pass

    items = []
    for it in agg.values():
        it["tables"] = sorted(it["tables"])
        it["table_count"] = len(it["tables"])
        items.append(it)
    items.sort(key=lambda x: (x["flag"] != "test", x["order_number"]))

    return {
        "items": items,
        "total": len(items),
        "flagged": sum(1 for i in items if i["flag"] == "phone"),
    }


# ── POST /api/test-orders/purge ──────────────────────────────────────────────
# body: {"order_numbers": [...], "phone": "...", "ack": true}
@router.post("/api/test-orders/purge")
async def purge(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    if not payload.get("ack"):
        raise HTTPException(400, "Confirmation required.")
    requested = payload.get("order_numbers") or []
    submitted_phone = (payload.get("phone") or "").strip()
    if not requested:
        raise HTTPException(400, "No orders selected.")

    # 服务端复核（不信前端勾选）：
    allowed = []
    for on in requested:
        if not on:
            continue
        if _is_test_order(on):
            allowed.append(on)                       # 前缀单：直接放行
            continue
        # 非前缀单（phone 捞出的旧脏单）：必须提交 phone，且库里该单 phone 与之一致
        if not submitted_phone:
            continue
        chk = await db.execute(text("""
            SELECT 1 FROM bookings
              WHERE order_number = :on
                AND regexp_replace(phone, '[^0-9]', '', 'g') = regexp_replace(:ph, '[^0-9]', '', 'g')
            UNION
            SELECT 1 FROM send_log
              WHERE order_number = :on
                AND regexp_replace(phone, '[^0-9]', '', 'g') = regexp_replace(:ph, '[^0-9]', '', 'g')
            UNION
            SELECT 1 FROM tickets_reminders
              WHERE chd_number = :on
                AND regexp_replace(phone, '[^0-9]', '', 'g') = regexp_replace(:ph, '[^0-9]', '', 'g')
            LIMIT 1
        """), {"on": on, "ph": submitted_phone})
        if chk.first():
            allowed.append(on)

    if not allowed:
        raise HTTPException(400, "No valid orders to delete after server-side validation.")

    deleted = {}
    for tbl in ORDER_TABLES:
        try:
            r = await db.execute(
                text(f"DELETE FROM {tbl} WHERE order_number = ANY(:ons)"),
                {"ons": allowed},
            )
            deleted[tbl] = r.rowcount
        except Exception as e:
            await db.rollback()
            raise HTTPException(500, f"Delete failed on {tbl}: {e}")

    for tbl in CHD_TABLES:
        try:
            r = await db.execute(
                text(f"DELETE FROM {tbl} WHERE chd_number = ANY(:ons)"),
                {"ons": allowed},
            )
            deleted[tbl] = r.rowcount
        except Exception as e:
            await db.rollback()
            raise HTTPException(500, f"Delete failed on {tbl}: {e}")

    await db.commit()
    return {
        "success": True,
        "deleted_orders": allowed,
        "rows_deleted": deleted,
        "message": f"Deleted {len(allowed)} order(s) across {len(deleted)} table(s).",
    }
