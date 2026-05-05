"""
Pickup Locations API Router
CRUD for pickup_locations table.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import get_current_user

router = APIRouter()


@router.get("")
async def list_pickup_locations(
    db: AsyncSession = Depends(get_db),
    _user = Depends(get_current_user),
):
    res = await db.execute(text(
        "SELECT id, hotel_name, photo_url, instruction FROM pickup_locations ORDER BY hotel_name ASC"
    ))
    rows = res.mappings().all()
    return {"locations": [dict(r) for r in rows]}


@router.post("")
async def create_pickup_location(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    _user = Depends(get_current_user),
):
    name = (payload.get("hotel_name") or "").strip()
    url  = (payload.get("photo_url") or "").strip()
    inst = (payload.get("instruction") or "").strip()
    if not name:
        raise HTTPException(400, "hotel_name is required")

    # Check duplicate
    existing = await db.execute(text(
        "SELECT id FROM pickup_locations WHERE hotel_name ILIKE :name LIMIT 1"
    ), {"name": name})
    if existing.fetchone():
        raise HTTPException(400, f'"{name}" already exists')

    res = await db.execute(text("""
        INSERT INTO pickup_locations (hotel_name, photo_url, instruction)
        VALUES (:name, :url, :inst)
        RETURNING id
    """), {"name": name, "url": url, "inst": inst})
    await db.commit()
    return {"id": res.fetchone().id, "hotel_name": name}


@router.put("/{location_id}")
async def update_pickup_location(
    location_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    _user = Depends(get_current_user),
):
    name = (payload.get("hotel_name") or "").strip()
    url  = (payload.get("photo_url") or "").strip()
    inst = (payload.get("instruction") or "").strip()
    if not name:
        raise HTTPException(400, "hotel_name is required")

    await db.execute(text("""
        UPDATE pickup_locations
        SET hotel_name  = :name,
            photo_url   = :url,
            instruction = :inst,
            updated_at  = NOW()
        WHERE id = :id
    """), {"name": name, "url": url, "inst": inst, "id": location_id})
    await db.commit()
    return {"success": True}


@router.delete("/{location_id}")
async def delete_pickup_location(
    location_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(403, "Admin only")
    await db.execute(text(
        "DELETE FROM pickup_locations WHERE id = :id"
    ), {"id": location_id})
    await db.commit()
    return {"success": True}
