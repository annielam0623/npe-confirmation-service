"""
app/auth.py
JWT utility functions + role-based access control dependencies.
Roles: superadmin > admin > staff
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import AdminUser

# ── Config ────────────────────────────────────────────────────────────────────
SECRET_KEY         = "npe-secret-key-change-in-prod"
ALGORITHM          = "HS256"
COOKIE_NAME        = "npe_token"
TOKEN_EXPIRE_HOURS = 12

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ADMIN_ROLES      = ("admin", "superadmin")
ALL_ROLES        = ("staff", "admin", "superadmin")


# ── Password helpers ──────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── JWT helpers ───────────────────────────────────────────────────────────────
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


# ── Current user from cookie ──────────────────────────────────────────────────
async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Optional[AdminUser]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    username = payload.get("sub")
    if not username:
        return None
    result = await db.execute(select(AdminUser).where(AdminUser.username == username))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        return None
    return user


# ── Dependency: staff or above (all ops pages) ───────────────────────────────
async def require_staff(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_302_FOUND,
                            headers={"Location": "/auth/login"})
    if user.role not in ALL_ROLES:
        raise HTTPException(status_code=403, detail="Access denied")
    return user


# ── Dependency: admin or superadmin (Settings, Users) ────────────────────────
async def require_admin(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_302_FOUND,
                            headers={"Location": "/auth/login"})
    if user.role not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ── Dependency: superadmin only (change roles) ───────────────────────────────
async def require_superadmin(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_302_FOUND,
                            headers={"Location": "/auth/login"})
    if user.role != "superadmin":
        raise HTTPException(status_code=403, detail="Superadmin access required")
    return user


# ── Login helper ──────────────────────────────────────────────────────────────
async def authenticate_user(
    username: str,
    password: str,
    db: AsyncSession,
) -> Optional[AdminUser]:
    result = await db.execute(select(AdminUser).where(AdminUser.username == username))
    user = result.scalar_one_or_none()
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    return user
