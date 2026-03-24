"""Authentication endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from typing import Optional

from app.database import get_db
from app.models.user import User, Role
from app.auth import (
    verify_password, hash_password,
    create_access_token, create_refresh_token,
    get_current_user,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    # Account
    username:  str
    email:     EmailStr
    password:  str
    full_name: str = ""

    # Customer profile
    company:       str = ""
    phone:         str = ""
    address_line1: str = ""
    address_line2: str = ""
    city:          str = ""
    state:         str = ""
    postcode:      str = ""
    country:       str = ""
    vat_number:    str = ""


class TokenResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"
    role:          str
    username:      str


@router.post("/token", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == form.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    if user.is_suspended:
        raise HTTPException(status_code=403, detail="Account suspended")
    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
        role=user.role,
        username=user.username,
    )


@router.post("/register", status_code=201)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # First user becomes superadmin
    result = await db.execute(select(User))
    is_first = result.first() is None
    user = User(
        username=req.username,
        email=req.email,
        hashed_password=hash_password(req.password),
        full_name=req.full_name,
        role=Role.superadmin if is_first else Role.user,
        # Profile fields
        company=req.company,
        phone=req.phone,
        address_line1=req.address_line1,
        address_line2=req.address_line2,
        city=req.city,
        state=req.state,
        postcode=req.postcode,
        country=req.country,
        vat_number=req.vat_number,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"id": user.id, "username": user.username, "role": user.role}


@router.get("/me")
async def me(current: User = Depends(get_current_user)):
    return {
        "id":            current.id,
        "username":      current.username,
        "email":         current.email,
        "full_name":     current.full_name,
        "role":          current.role,
        "is_active":     current.is_active,
        "disk_quota_mb": current.disk_quota_mb,
        "bw_quota_mb":   current.bw_quota_mb,
        "max_domains":   current.max_domains,
        # Profile
        "company":       current.company,
        "phone":         current.phone,
        "address_line1": current.address_line1,
        "address_line2": current.address_line2,
        "city":          current.city,
        "state":         current.state,
        "postcode":      current.postcode,
        "country":       current.country,
    }
