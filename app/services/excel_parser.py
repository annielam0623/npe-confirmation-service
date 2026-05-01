"""
NPE Excel Parser
Ported from WordPress PHP: excel-parser.php

Supports three module formats:
  tour_confirmation : Order#, First Name, Last Name, Email, Quantities,
                      Pick-up Time, Pick-up Location, MTLV Promo
  morning_pickup    : Order#, First Name, Last Name, Phone, Quantities,
                      Pick-up Time, Pick-up Location, Driver, Vehicle#
  tickets_reminder  : Service Date, CHD#, No. of Pax, Check-in Time,
                      Tour Time, Lead Name, Phone, Confirmation#,
                      Tour Location, Email

Column order does NOT matter — matched by header name.
"""

import re
import zipfile
import xml.etree.ElementTree as ET
from typing import Optional


# ─── Column alias map ──────────────────────────────────────────────────────────
COL_ALIASES: dict[str, list[str]] = {
    "order_number":    ["order number", "order#", "order #", "chd#", "chd #"],
    "confirmation_no": ["confirmation#", "confirmation #", "confirmation number"],
    "first_name":      ["first name", "firstname", "customer first name"],
    "last_name":       ["last name", "lastname", "customer last name"],
    "lead_name":       ["lead name", "leadname", "customer full name"],
    "email":           ["email", "customer email", "e-mail"],
    "phone":           ["phone", "phone no", "phone no.", "customer phone", "phone number"],
    "quantities":      ["quantities", "no. of pax", "no of pax", "pax", "party"],
    "pickup_time":     ["pickup time", "pick-up time", "pick up time"],
    "pickup_location": ["pickup location", "pick-up location", "pick up location"],
    "driver":          ["driver"],
    "vehicle_no":      ["vehicle#", "vehicle #", "vehicle number"],
    "tour_date":       ["tour date", "service date", "date"],
    "checkin_time":    ["check-in time", "checkin time", "check in time"],
    "tour_time":       ["tour time"],
    "tour_location":   ["tour location", "meeting location"],
    "mtlv_promo":      ["mtlv promo", "mtlv_promo", "promo"],
    "special_requirements": ["order special requirements", "special requirements", "special req"],
    "agent_name":      ["agent name", "agent"],
    "session":         ["session"],
}

# ─── Required columns per module ──────────────────────────────────────────────
REQUIRED_COLS: dict[str, list[str]] = {
    "tour_confirmation": ["order_number", "email", "pickup_time", "pickup_location"],
    "morning_pickup":    ["order_number", "phone", "pickup_time", "driver", "vehicle_no"],
    "tickets_reminder":  ["order_number", "phone", "checkin_time", "tour_time"],
}


def _col_to_index(col: str) -> int:
    """Excel column letter(s) → zero-based index. A=0, B=1, Z=25, AA=26 ..."""
    col = col.upper()
    index = 0
    for ch in col:
        index = index * 26 + (ord(ch) - ord("A") + 1)
    return index - 1


def _excel_fraction_to_time(val: str) -> str:
    """Convert Excel time fraction (e.g. 0.1736) → '4:10 AM'"""
    try:
        f = float(val)
        if 0 < f < 1:
            mins = round(f * 24 * 60)
            h = (mins // 60) % 24
            m = mins % 60
            suffix = "AM" if h < 12 else "PM"
            h12 = h % 12 or 12
            return f"{h12}:{m:02d} {suffix}"
    except (ValueError, TypeError):
        pass
    return val


def _parse_shared_strings(zip_file: zipfile.ZipFile) -> list[str]:
    shared: list[str] = []
    try:
        with zip_file.open("xl/sharedStrings.xml") as f:
            tree = ET.parse(f)
            ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            for si in tree.findall(".//s:si", ns):
                texts = si.findall(".//s:t", ns)
                shared.append("".join(t.text or "" for t in texts))
    except KeyError:
        pass
    return shared


def _parse_sheet(zip_file: zipfile.ZipFile, shared: list[str]) -> list[dict[int, str]]:
    """Parse sheet1.xml → list of rows, each row = {col_index: cell_value}"""
    raw: list[dict[int, str]] = []
    try:
        with zip_file.open("xl/worksheets/sheet1.xml") as f:
            tree = ET.parse(f)
    except KeyError:
        return raw

    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    for row_el in tree.findall(".//s:row", ns):
        row: dict[int, str] = {}
        for cell in row_el.findall("s:c", ns):
            ref = cell.get("r", "")
            col_letter = re.sub(r"[0-9]", "", ref)
            ci = _col_to_index(col_letter)
            cell_type = cell.get("t", "")
            v_el = cell.find("s:v", ns)
            val = v_el.text or "" if v_el is not None else ""

            if cell_type == "s":
                val = shared[int(val)] if val.isdigit() and int(val) < len(shared) else ""
            elif cell_type in ("", "n"):
                val = _excel_fraction_to_time(val)

            row[ci] = val
        raw.append(row)
    return raw


def _find_header(raw: list[dict[int, str]]) -> tuple[Optional[int], dict[str, int]]:
    """Find header row and build canonical field → col_index map."""
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
            return ri, tmp_map
    return None, {}


def _normalize_phone(phone: str) -> str:
    if phone and not phone.startswith("+"):
        digits = re.sub(r"[^0-9]", "", phone)
        if len(digits) == 10:
            return f"+1{digits}"
        elif len(digits) == 11 and digits.startswith("1"):
            return f"+{digits}"
    return phone


def parse_excel(filepath: str, module: str) -> dict:
    """
    Parse an .xlsx file for the given module.

    Returns:
      {"rows": [...]}  on success
      {"error": "..."}  on failure
    """
    try:
        zf = zipfile.ZipFile(filepath)
    except Exception as e:
        return {"error": f"Cannot open Excel file: {e}"}

    with zf:
        shared = _parse_shared_strings(zf)
        raw = _parse_sheet(zf, shared)

    if not raw:
        return {"error": "Cannot read sheet1 from Excel file"}

    header_idx, col_map = _find_header(raw)
    if header_idx is None:
        return {"error": "Could not find a header row. Check column names."}

    # Validate required columns
    required = REQUIRED_COLS.get(module, [])
    missing = [f for f in required if f not in col_map]
    if missing:
        friendly = {
            "order_number":    "Order Number",
            "email":           "Customer Email",
            "pickup_time":     "Pick-up Time",
            "pickup_location": "Pick-up Location",
            "phone":           "Customer Phone",
            "driver":          "Driver",
            "vehicle_no":      "Vehicle#",
            "checkin_time":    "Check-in Time",
            "tour_time":       "Tour Time",
        }
        labels = [friendly.get(f, f) for f in missing]
        return {"error": f"Missing required column(s): {', '.join(labels)}"}

    def get(row: dict[int, str], field: str) -> str:
        ci = col_map.get(field)
        return row.get(ci, "").strip() if ci is not None else ""

    rows = []
    for i in range(header_idx + 1, len(raw)):
        row = raw[i]

        # Skip empty rows
        if not any(v.strip() for v in row.values()):
            continue

        # Name resolution
        first = get(row, "first_name")
        last  = get(row, "last_name")
        lead  = get(row, "lead_name")
        if not first and lead:
            parts = lead.split(" ", 1)
            first = parts[0]
            last  = parts[1] if len(parts) > 1 else ""
        name = f"{first} {last}".strip() or lead

        phone = get(row, "phone")
        phone = _normalize_phone(phone)

        # mtlv_promo: "YES" or ""
        mtlv_promo = get(row, "mtlv_promo").upper()
        has_promotion = mtlv_promo == "YES"

        rows.append({
            "order_number":         get(row, "order_number"),
            "confirmation_no":      get(row, "confirmation_no"),
            "first_name":           first,
            "last_name":            last,
            "lead_name":            lead,
            "name":                 name,
            "email":                get(row, "email"),
            "phone":                phone,
            "quantities":           get(row, "quantities") or "1",
            "pickup_time":          get(row, "pickup_time"),
            "pickup_location":      get(row, "pickup_location"),
            "driver":               get(row, "driver"),
            "vehicle_no":           get(row, "vehicle_no"),
            "tour_date":            get(row, "tour_date"),
            "checkin_time":         get(row, "checkin_time"),
            "tour_time":            get(row, "tour_time"),
            "tour_location":        get(row, "tour_location"),
            "mtlv_promo":           mtlv_promo,
            "has_promotion":        has_promotion,
            "special_requirements": get(row, "special_requirements"),
            "agent_name":           get(row, "agent_name"),
            "session":              get(row, "session"),
        })

    if not rows:
        return {"error": "No data rows found in the file."}

    return {"rows": rows}
