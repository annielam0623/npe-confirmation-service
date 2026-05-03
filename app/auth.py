"""
NPE Auth — JWT login, role-based access control
Roles: admin (full access), staff (no Settings)
"""

import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

# ─── Config ───────────────────────────────────────────────────────────────────

SECRET_KEY  = os.getenv("SECRET_KEY", "change-me-in-production-please")
ALGORITHM   = "HS256"
TOKEN_EXPIRE_HOURS = 12
COOKIE_NAME = "npe_token"

# ─── Setup ────────────────────────────────────────────────────────────────────

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)
templates = Jinja2Templates(directory="app/templates")
router = APIRouter()

# ─── Pydantic Schemas ─────────────────────────────────────────────────────────

class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None


class UserOut(BaseModel):
    id: int
    username: str
    email: Optional[str]
    role: str
    is_active: bool

    class Config:
        from_attributes = True


# ─── Password Helpers ─────────────────────────────────────────────────────────

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


# ─── JWT Helpers ──────────────────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[TokenData]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        role     = payload.get("role", "staff")
        if username is None:
            return None
        return TokenData(username=username, role=role)
    except JWTError:
        return None


# ─── DB Helper ────────────────────────────────────────────────────────────────

async def get_user(db: AsyncSession, username: str):
    from app.models import AdminUser
    result = await db.execute(select(AdminUser).where(AdminUser.username == username))
    return result.scalar_one_or_none()


async def authenticate_user(db: AsyncSession, username: str, password: str):
    user = await get_user(db, username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


# ─── Current User Dependency ──────────────────────────────────────────────────

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Read JWT from cookie (browser) or Authorization header (API)."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        # fallback: Authorization: Bearer <token>
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Not authenticated")

    token_data = decode_token(token)
    if not token_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid or expired token")

    user = await get_user(db, token_data.username)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="User not found or inactive")
    return user


async def get_current_admin(current_user=Depends(get_current_user)):
    """Only admin role allowed."""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Admin access required")
    return current_user


def require_admin(current_user=Depends(get_current_user)):
    """Dependency alias for admin-only routes."""
    return get_current_admin(current_user)


# ─── Auth Routes ──────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    # If already logged in, redirect to dashboard
    token = request.cookies.get(COOKIE_NAME)
    if token and decode_token(token):
        return RedirectResponse(url="/admin/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))

    user = await authenticate_user(db, username, password)
    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password"},
            status_code=400,
        )

    token = create_access_token({"sub": user.username, "role": user.role})
    response = RedirectResponse(url="/admin/dashboard", status_code=302)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=TOKEN_EXPIRE_HOURS * 3600,
        samesite="lax",
    )
    return response


@router.post("/token")
async def api_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """API token endpoint for swagger/testing."""
    user = await authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    token = create_access_token({"sub": user.username, "role": user.role})
    return {"access_token": token, "token_type": "bearer"}


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/auth/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response


# ─── Create Admin Utility ─────────────────────────────────────────────────────

@router.post("/create-admin")
async def create_admin(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    One-time setup: create an admin user.
    Protected by ADMIN_SETUP_KEY env var.
    """
    from app.models import AdminUser

    setup_key = os.getenv("ADMIN_SETUP_KEY", "")
    body = await request.json()

    if setup_key and body.get("setup_key") != setup_key:
        raise HTTPException(status_code=403, detail="Invalid setup key")

    username = body.get("username", "").strip()
    password = body.get("password", "")
    email    = body.get("email", "")
    role     = body.get("role", "admin")

    if not username or not password:
        raise HTTPException(status_code=400, detail="username and password required")

    existing = await get_user(db, username)
    if existing:
        raise HTTPException(status_code=409, detail=f"User '{username}' already exists")

    user = AdminUser(
        username=username,
        email=email,
        hashed_password=hash_password(password),
        role=role,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    return {"message": f"User '{username}' ({role}) created successfully"}
