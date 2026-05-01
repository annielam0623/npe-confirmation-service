"""
NPE PDF Handler
Parses ticket PDF filenames and auto-assigns tickets to bookings by Quantities order.

Filename format: "MTLV 901-1000 Ord ID 631251973 [3].pdf"
  - MTLV       = promotion/attraction code
  - 901-1000   = batch range (NPE purchase batch)
  - 631251973  = batch order ID (NPE purchase order, NOT guest order)
  - [3]        = ticket index within batch
"""

import re
from typing import Optional


def parse_pdf_filename(filename: str) -> Optional[dict]:
    """
    Parse a ticket PDF filename.

    Returns dict with keys:
      promotion_code, batch_range, batch_order_id, ticket_index
    or None if filename doesn't match expected format.

    Examples:
      "MTLV 901-1000 Ord ID 631251973 [1].pdf"
      "MTLV 901-1000 Ord ID 631251973 [42].pdf"
    """
    pattern = r"^([A-Z]+)\s+([\d]+-[\d]+)\s+Ord\s+ID\s+(\d+)\s+\[(\d+)\]\.pdf$"
    match = re.match(pattern, filename.strip(), re.IGNORECASE)
    if not match:
        return None

    return {
        "promotion_code": match.group(1).upper(),   # "MTLV"
        "batch_range":    match.group(2),            # "901-1000"
        "batch_order_id": match.group(3),            # "631251973"
        "ticket_index":   int(match.group(4)),       # 3
    }


def assign_tickets_to_bookings(
    bookings: list[dict],
    pdf_files: list[dict],
) -> list[dict]:
    """
    Auto-assign PDF tickets to bookings based on Quantities order.

    bookings: list of dicts with keys: id, quantities, order_number
              Must be in Excel row order (same order as PDF [1][2][3]...)
    pdf_files: list of dicts with keys: ticket_index, filename, pdf_data,
               promotion_code, batch_order_id
               (output of parse_pdf_filename + pdf bytes)

    Returns list of assignment dicts:
      {booking_id, ticket_index, filename, pdf_data, promotion_code, batch_order_id}

    Example:
      bookings = [{id:1, quantities:4}, {id:2, quantities:2}, {id:3, quantities:1}]
      pdfs sorted by ticket_index: [1,2,3,4,5,6,7]
      Result:
        booking 1 → tickets [1,2,3,4]
        booking 2 → tickets [5,6]
        booking 3 → ticket  [7]
    """
    # Sort PDFs by ticket_index
    sorted_pdfs = sorted(pdf_files, key=lambda x: x["ticket_index"])

    assignments = []
    pdf_cursor = 0

    for booking in bookings:
        qty = int(booking.get("quantities", 1))
        booking_id = booking["id"]

        for _ in range(qty):
            if pdf_cursor >= len(sorted_pdfs):
                break
            pdf = sorted_pdfs[pdf_cursor]
            assignments.append({
                "booking_id":    booking_id,
                "ticket_index":  pdf["ticket_index"],
                "filename":      pdf["filename"],
                "pdf_data":      pdf["pdf_data"],
                "promotion_code": pdf.get("promotion_code", ""),
                "batch_order_id": pdf.get("batch_order_id", ""),
            })
            pdf_cursor += 1

    return assignments


def validate_pdf_batch(
    pdf_files: list[dict],
    expected_total: int,
) -> dict:
    """
    Validate that uploaded PDFs match expected total quantity.

    Returns {"ok": True} or {"ok": False, "error": "..."}
    """
    if not pdf_files:
        return {"ok": False, "error": "No PDF files uploaded"}

    indices = [p["ticket_index"] for p in pdf_files]
    indices_set = set(indices)

    # Check for duplicates
    if len(indices) != len(indices_set):
        dupes = [i for i in indices if indices.count(i) > 1]
        return {"ok": False, "error": f"Duplicate ticket indices found: {list(set(dupes))}"}

    # Check count matches
    if len(pdf_files) != expected_total:
        return {
            "ok": False,
            "error": f"Expected {expected_total} tickets but got {len(pdf_files)} PDFs"
        }

    # Check all from same batch
    batch_ids = set(p.get("batch_order_id") for p in pdf_files)
    if len(batch_ids) > 1:
        return {"ok": False, "error": f"PDFs from multiple batches: {batch_ids}"}

    return {"ok": True}
