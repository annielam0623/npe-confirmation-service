"""
NPE Tickets Router
Handles Promotion PDF ticket upload, parsing, and assignment to bookings.
"""

import io
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Booking, BookingTicket, Promotion
from app.auth import get_current_user
from app.services.pdf_handler import parse_pdf_filename, assign_tickets_to_bookings, validate_pdf_batch

router = APIRouter()


@router.post("/upload")
async def upload_tickets(
    tour_date: str = Form(...),
    pdfs: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Upload batch PDF tickets and auto-assign to bookings by Quantities order.

    Steps:
    1. Parse each PDF filename → extract promotion_code, batch_order_id, ticket_index
    2. Find all promotion bookings for that tour_date, ordered by created_at
    3. Auto-assign PDFs to bookings based on Quantities
    4. Store PDF bytes in booking_tickets table
    """
    pdf_files = []
    for upload in pdfs:
        if not upload.filename.endswith(".pdf"):
            raise HTTPException(400, f"Not a PDF: {upload.filename}")

        parsed = parse_pdf_filename(upload.filename)
        if not parsed:
            raise HTTPException(400, f"Filename format not recognized: {upload.filename}\n"
                                     f"Expected: 'MTLV 901-1000 Ord ID 631251973 [1].pdf'")

        pdf_bytes = await upload.read()
        pdf_files.append({
            **parsed,
            "filename": upload.filename,
            "pdf_data": pdf_bytes,
        })

    if not pdf_files:
        raise HTTPException(400, "No valid PDF files uploaded")

    # All PDFs must be from same promotion code
    codes = set(p["promotion_code"] for p in pdf_files)
    if len(codes) > 1:
        raise HTTPException(400, f"PDFs from multiple promotion codes in one upload: {codes}")

    promo_code = codes.pop()

    # Find promotion
    promo_result = await db.execute(select(Promotion).where(Promotion.code == promo_code))
    promotion = promo_result.scalar_one_or_none()
    if not promotion:
        raise HTTPException(404, f"Promotion code '{promo_code}' not found. Add it in /admin/promotions first.")

    # Find promotion bookings for tour_date, ordered by creation (= Excel row order)
    bookings_result = await db.execute(
        select(Booking)
        .where(Booking.tour_date == tour_date)
        .where(Booking.has_promotion == True)
        .where(Booking.promotion_id == promotion.id)
        .order_by(Booking.created_at)
    )
    bookings = bookings_result.scalars().all()

    if not bookings:
        raise HTTPException(404, f"No promotion bookings found for tour date {tour_date} with code {promo_code}")

    # Validate total count
    expected_total = sum(b.quantities for b in bookings)
    validation = validate_pdf_batch(pdf_files, expected_total)
    if not validation["ok"]:
        raise HTTPException(400, validation["error"])

    # Auto-assign
    booking_dicts = [{"id": b.id, "quantities": b.quantities} for b in bookings]
    assignments = assign_tickets_to_bookings(booking_dicts, pdf_files)

    # Save to DB
    saved = 0
    for a in assignments:
        ticket = BookingTicket(
            booking_id=a["booking_id"],
            promotion_id=promotion.id,
            batch_order_id=a["batch_order_id"],
            ticket_index=a["ticket_index"],
            filename=a["filename"],
            pdf_data=a["pdf_data"],
        )
        db.add(ticket)
        saved += 1

    await db.commit()

    return {
        "message": f"Successfully assigned {saved} tickets to {len(bookings)} bookings",
        "promotion": promo_code,
        "tour_date": tour_date,
        "total_tickets": saved,
        "bookings_affected": len(bookings),
    }


@router.get("/booking/{booking_id}")
async def get_booking_tickets(
    booking_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List all tickets assigned to a booking."""
    result = await db.execute(
        select(BookingTicket)
        .where(BookingTicket.booking_id == booking_id)
        .order_by(BookingTicket.ticket_index)
    )
    tickets = result.scalars().all()
    return [{"id": t.id, "filename": t.filename, "ticket_index": t.ticket_index} for t in tickets]
