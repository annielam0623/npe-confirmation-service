"""
Excel parser — mirrors PHP npe-operations excel-parser.php v1.3.18
Column matching is case-insensitive and alias-based (order does NOT matter).
Supports: tour_confirmation, morning_pickup, tickets_reminder
"""
from __future__ import annotations
import io
from datetime import date, timedelta
from zipfile import ZipFile
import xml.etree.ElementTree as ET

COL_ALIASES: dict[str, list[str]] = {
    "order_number":    ["order number", "order#", "order #", "chd#", "chd #"],
    "confirmation_no": ["confirmation#", "confirmation #", "confirmation number"],
    "first_name":      ["first name", "firstname"],
    "last_name":       ["last name", "lastname"],
    "lead_name":       ["lead name", "leadname", "customer name"],
    "email":           ["email", "customer email", "e-mail"],
    "phone":           ["phone", "phone no", "phone no.", "customer phone", "phone number", "phone #"],
    "quantities":      ["quantities", "no. of pax", "no of pax", "pax", "pax#", "pax #", "party"],
    "pickup_time":     ["pickup time", "pick-up time", "pick up time"],
    "pickup_location": ["pickup location", "pick-up location", "pick up location", "hotel pickup"],
    "driver":          ["driver"],
    "vehicle_no":      ["vehicle#", "vehicle #", "vehicle number", "bus#", "bus #", "bus number"],
    "tour_date":       ["tour date", "service date", "date"],
    "checkin_time":    ["check-in time", "checkin time", "check in time"],
    "tour_time":       ["tour time"],
    "tour_location":   ["tour location", "meeting location"],
}

REQUIRED_COLS: dict[str, list[str]] = {
    "morning_pickup":    ["phone", "pickup_time", "driver"],
    "tour_confirmation": ["email", "phone", "pickup_time"],
    "tickets_reminder":  ["phone", "checkin_time", "tour_time"],
}

FRIENDLY_NAMES = {
    "phone": "Phone", "email": "Email", "pickup_time": "Pickup Time",
    "driver": "Driver", "checkin_time": "Check-in Time", "tour_time": "Tour Time",
}


def _col_letter_to_index(col: str) -> int:
    col = col.upper()
    idx = 0
    for ch in col:
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


def _excel_serial_to_date(val: str) -> str:
    """
    Convert Excel date serial number → 'YYYY-MM-DD'.
    Excel epoch is 1899-12-30. Excel incorrectly treats 1900 as a leap year,
    so serial numbers >= 60 need a -1 adjustment.
    Returns original string if conversion fails.
    """
    try:
        f = float(val)
        n = int(f)
        if n >= 60:
            n -= 1  # correct for Excel's 1900 leap year bug
        d = date(1899, 12, 31) + timedelta(days=n)
        return d.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return val


def _excel_time_to_str(val: str) -> str:
    """
    Convert Excel numeric value:
    - If 0 < f < 1        → time fraction  → 'H:MM AM/PM'  (e.g. 0.486 → '11:40 AM')
    - If 1 <= f <= 109572 → date serial    → 'YYYY-MM-DD'   (e.g. 46152 → '2026-05-10')
                            (109572 = year 2199, safely excludes phone numbers / confirmation#)
    - Otherwise           → return as-is (phone numbers, large IDs, etc.)
    """
    try:
        f = float(val)
        if 0 < f < 1:
            # Time fraction
            mins = round(f * 24 * 60)
            h = (mins // 60) % 24
            m = mins % 60
            period = "PM" if h >= 12 else "AM"
            h12 = h % 12 or 12
            return f"{h12}:{m:02d} {period}"
        elif 40000 <= f <= 109572:
            # Date serial (year ~2009 ~ 2199); lower bound excludes small numbers like pax count
            return _excel_serial_to_date(val)
    except (ValueError, TypeError):
        pass
    return val


def _parse_shared_strings(zf: ZipFile) -> list[str]:
    shared: list[str] = []
    try:
        xml_bytes = zf.read("xl/sharedStrings.xml")
        root = ET.fromstring(xml_bytes)
        ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        for si in root.findall("x:si", ns):
            text = ""
            t = si.find("x:t", ns)
            if t is not None:
                text = t.text or ""
            else:
                for r in si.findall("x:r/x:t", ns):
                    text += r.text or ""
            shared.append(text)
    except KeyError:
        pass
    return shared


def _parse_sheet(zf: ZipFile, shared: list[str]) -> list[dict[int, str]]:
    xml_bytes = zf.read("xl/worksheets/sheet1.xml")
    root = ET.fromstring(xml_bytes)
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

    raw: list[dict[int, str]] = []
    for row_el in root.findall(".//x:row", ns):
        rd: dict[int, str] = {}
        for cell in row_el.findall("x:c", ns):
            ref = cell.get("r", "")
            col_letter = "".join(ch for ch in ref if ch.isalpha())
            ci = _col_letter_to_index(col_letter)
            cell_type = cell.get("t", "")
            v_el = cell.find("x:v", ns)
            val = (v_el.text or "") if v_el is not None else ""

            if cell_type == "s":
                # Shared string — look up in shared strings table
                val = shared[int(val)] if val and int(val) < len(shared) else ""
            elif cell_type in ("", "n"):
                # Numeric value (or formula with cached numeric result)
                # Could be date serial (>=1) or time fraction (0<x<1)
                val = _excel_time_to_str(val)
            # cell_type == "str" means inline string from formula result — keep val as-is

            rd[ci] = val
        if rd:
            raw.append(rd)
    return raw


def _format_phone(raw: str) -> str:
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits[0] == "1":
        return f"+{digits}"
    if digits:
        return f"+{digits}"
    return raw


def parse_excel(file_bytes: bytes, module: str) -> dict:
    """
    Returns {'rows': [...]} or {'error': 'message'}.
    """
    try:
        zf = ZipFile(io.BytesIO(file_bytes))
    except Exception:
        return {"error": "Cannot open Excel file — make sure it is .xlsx format"}

    try:
        shared = _parse_shared_strings(zf)
        raw = _parse_sheet(zf, shared)
    except Exception as e:
        return {"error": f"Cannot parse Excel file: {e}"}
    finally:
        zf.close()

    if not raw:
        return {"error": "No data found in Excel file"}

    # Find header row (≥2 recognised columns)
    header_idx: int | None = None
    col_map: dict[str, int] = {}

    for ri, row in enumerate(raw):
        matches = 0
        tmp_map: dict[str, int] = {}
        for ci, cell in row.items():
            lower = cell.strip().lower()
            for field, aliases in COL_ALIASES.items():
                if lower in aliases:
                    tmp_map[field] = ci
                    matches += 1
                    break
        if matches >= 2:
            header_idx = ri
            col_map = tmp_map
            break

    if header_idx is None:
        return {"error": "Could not find a header row. Check column names."}

    # Validate required columns
    for field in REQUIRED_COLS.get(module, []):
        if field not in col_map:
            label = FRIENDLY_NAMES.get(field, field)
            return {"error": f'Missing required column: "{label}"'}

    def get(row: dict[int, str], field: str) -> str:
        ci = col_map.get(field)
        return row.get(ci, "").strip() if ci is not None else ""

    rows: list[dict] = []
    for row in raw[header_idx + 1:]:
        if not any(v.strip() for v in row.values()):
            continue

        first = get(row, "first_name")
        last = get(row, "last_name")
        lead = get(row, "lead_name")

        if not first and lead:
            parts = lead.split(" ", 1)
            first = parts[0]
            last = parts[1] if len(parts) > 1 else ""

        name = f"{first} {last}".strip() or lead

        phone = get(row, "phone")
        if phone and not phone.startswith("+"):
            phone = _format_phone(phone)

        rows.append({
            "order_number":    get(row, "order_number"),
            "confirmation_no": get(row, "confirmation_no"),
            "first_name":      first,
            "last_name":       last,
            "lead_name":       lead,
            "name":            name,
            "email":           get(row, "email"),
            "phone":           phone,
            "quantities":      get(row, "quantities") or "1",
            "pickup_time":     get(row, "pickup_time"),
            "pickup_location": get(row, "pickup_location"),
            "driver":          get(row, "driver"),
            "vehicle_no":      get(row, "vehicle_no"),
            "tour_date":       get(row, "tour_date"),
            "checkin_time":    get(row, "checkin_time"),
            "tour_time":       get(row, "tour_time"),
            "tour_location":   get(row, "tour_location"),
        })

    if not rows:
        return {"error": "No data rows found in the file."}

    return {"rows": rows}
