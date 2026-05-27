# NPE 数据库规则 & 已知坑 (bookings 表)

_最后更新：2026-05-27_

---

## 一、bookings 表关键字段类型

| 字段 | 类型 | 注意事项 |
|---|---|---|
| `status` | PostgreSQL **ENUM** (`bookingstatus`) | ⚠️ 见下方专项说明 |
| `product_type` | VARCHAR | `'bus_tour'` / `'self_drive'` |
| `tour_date` | DATE | 用 Python `date` 对象传参，不传字符串 |
| `order_number` | VARCHAR | 所有跨表关联的主键，不用 `id` |
| `quantities` | INTEGER | Excel 上传别名：`pax#` / `pax #` / `no_of_pax` |
| `pickup_location` | VARCHAR | Excel 别名：`hotel pickup` |
| `phone` | VARCHAR | Excel 别名：`customer phone` / `phone #` |

---

## 二、⚠️ status 字段 — 最高频踩坑

### 问题根源
`bookings.status` 是 PostgreSQL **原生 ENUM 类型**（`bookingstatus`），不是 VARCHAR。

PostgreSQL 对 ENUM 的处理非常严格：
- `COALESCE(b.status, '')` → 把 NULL 转成空字符串 `""` → PostgreSQL 尝试将 `""` 解析为合法 enum 值 → **报错**
- `b.status = 'confirmed'` → 大小写不匹配也可能报错（取决于 enum 定义）

### 错误信息
```
sqlalchemy.exc.DBAPIError: invalid input value for enum bookingstatus: ""
```

### ✅ 正确写法

```sql
-- 比较 status 值（先 cast 成 text）
WHERE UPPER(b.status::text) = 'CONFIRMED'
WHERE UPPER(b.status::text) IN ('PROCESSING', 'ON_HOLD', 'PENDING')

-- 检查 NULL
WHERE b.status IS NULL

-- 检查非 NULL
WHERE b.status IS NOT NULL

-- 同时处理 NULL 和值比较
WHERE b.status IS NULL OR UPPER(b.status::text) != 'CONFIRMED'
```

### ❌ 错误写法（永远不要用）
```sql
-- 会报 invalid enum value 错误
COALESCE(b.status, '')
COALESCE(b.status::text, '')   -- 这个可以，但下面这个不行
UPPER(COALESCE(b.status, ''))  -- ❌ 先 COALESCE 再 cast，顺序错了

-- 直接字符串比较（不 cast）
b.status = 'Confirmed'         -- 可能因大小写报错
```

### Python / SQLAlchemy 中
```python
# raw text SQL — 必须 cast
text("UPPER(b.status::text) = 'CONFIRMED'")

# SQLAlchemy ORM — cast 方式
from sqlalchemy import cast, String
filter(cast(Booking.status, String) == 'CONFIRMED')
```

---

## 三、order_number vs id

**所有跨表关联必须用 `order_number`（VARCHAR），不用整数 `id`。**

原因：`bookings` 和 `tickets_reminders` 是两张独立的表，各自有自己的整数 `id` 序列，两个表的 id 数字空间完全重叠，用 id 做关联会导致数据混乱。

```python
# ✅ 正确
WHERE booking_notes.order_number = bookings.order_number

# ❌ 错误（会查到错误的表）
WHERE booking_notes.booking_id = bookings.id
```

相关表：`booking_notes`、`activity_log`、`send_log`、`broadcast_recipients` — 全部用 `order_number`。

---

## 四、Rezdy Webhook 解析规则

### pickupLocation 位置
```
payload → order → items[0] → pickupLocation (dict，不是字符串！)
  ├── locationName  → bookings.pickup_location
  └── pickupTime    → bookings.pickup_time
```
**坑：** `pickupLocation` 不在 payload 根层，而是在 `items[0]` 内，且是一个 dict。

### 字段覆盖保护（updatedOrder）
```python
# 只有值存在且非 "unknown" 才覆盖，防止不完整数据覆盖已有值
if new_value and new_value.lower() != "unknown":
    row["first_name"] = new_value
```
`first_name` / `last_name` fallback 用 `None`，不写 `"Unknown"`。

### tt_number
NPE 内部另一个管理系统的流水号（简称 TT#），从 Rezdy payload 中提取存储，只需存储和展示，不涉及其他系统逻辑。

### product_type 判断
```python
if product_code in SELF_DRIVE_CODES:   # 9种 Antelope Canyon 产品
    product_type = "self_drive"
else:
    product_type = "bus_tour"          # 包含 shuttle 产品
```
判断依据是 `productCode`（稳定），不依赖 `productName`（会变）。

---

## 五、Manifest / Forecast 数据过滤

**Manifest 和 30 Day Forecast 只显示 Confirmed 订单**，PROCESSING 订单不计入 pax 数字，避免影响排车。

```sql
-- Manifest / Forecast 查询标准写法
WHERE UPPER(b.status::text) = 'CONFIRMED'
```

Orders 页面保留显示所有状态，但默认 pill 选 Confirmed。

---

## 六、其他已知坑

### 时区
- 所有时间统一用 **LA 时间**（`America/Los_Angeles`）
- `datetime.now(LA).replace(tzinfo=None)` 写入数据库（naive datetime）
- `expires_at` 等字段：DB 存的是 LA time，读取时不要当 UTC 处理

### asyncpg DATE 参数类型
asyncpg 对 `DATE` 类型字段要求传 Python `date` 对象，不接受字符串，否则报：
```
AttributeError: 'str' object has no attribute 'toordinal'
```
```python
# ✅ 正确 — 先转换再传参
from datetime import date as date_type
params["date_from"] = date_type.fromisoformat(date_from)  # 传 date 对象

# ❌ 错误 — 直接传字符串
params["date_from"] = date_from  # '2026-05-01' 字符串会报错
```

### TablePlus
- Railway PostgreSQL 有新数据提交后，TablePlus 需要**断开重连**才能看到最新数据，不是刷新。

### bcrypt
- 锁定版本：`bcrypt==4.0.1`，升级会导致部署失败。

### base.html
- 保持压缩格式，不要用 VS Code 自动格式化，否则 Jinja2 模板会被破坏。

### JS 里的 Jinja2 冲突
- `{{ }}` 在 JS 中会被 Jinja2 误解析
- 解决方案：用 `window._varName` 传数据，不在 `<script>` 里直接用 `{{ }}`
