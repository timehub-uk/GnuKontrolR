"""User management endpoints (admin+)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from typing import Optional

from app.database import get_db
from app.models.user import User, Role
from app.auth import require_admin, hash_password, get_current_user

router = APIRouter(prefix="/api/users", tags=["users"])


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: Optional[Role] = None
    is_active: Optional[bool] = None
    is_suspended: Optional[bool] = None
    disk_quota_mb: Optional[int] = None
    bw_quota_mb: Optional[int] = None
    max_domains: Optional[int] = None
    password: Optional[str] = None


class ProfileUpdate(BaseModel):
    preferred_name: Optional[str] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postcode: Optional[str] = None
    country: Optional[str] = None


@router.get("/")
async def list_users(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(User).order_by(User.id))
    users = result.scalars().all()
    return [
        {
            "id": u.id, "username": u.username, "email": u.email,
            "full_name": u.full_name, "role": u.role,
            "is_active": u.is_active, "is_suspended": u.is_suspended,
            "created_at": u.created_at, "disk_quota_mb": u.disk_quota_mb,
            "max_domains": u.max_domains,
        }
        for u in users
    ]


@router.get("/{user_id}")
async def get_user(user_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "is_suspended": user.is_suspended,
        "max_domains": user.max_domains,
        "disk_quota_mb": user.disk_quota_mb,
        "bw_quota_mb": user.bw_quota_mb,
        "max_databases": user.max_databases,
        "max_emails": user.max_emails,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "company": user.company,
        "phone": user.phone,
        "address_line1": user.address_line1,
        "address_line2": user.address_line2,
        "city": user.city,
        "state": user.state,
        "postcode": user.postcode,
        "country": user.country,
        "vat_number": user.vat_number,
        "notes": user.notes,
    }


@router.patch("/{user_id}")
async def update_user(user_id: int, body: UserUpdate, db: AsyncSession = Depends(get_db), current=Depends(require_admin)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    email_changed = body.email is not None and body.email != user.email
    for field, val in body.model_dump(exclude_none=True).items():
        if field == "role":
            # Only superadmin can grant or revoke the superadmin role
            from app.models.user import Role as _Role
            if (val == _Role.superadmin or user.role == _Role.superadmin) and current.role != _Role.superadmin:
                raise HTTPException(403, "Only a superadmin can change the superadmin role")
        if field == "password":
            setattr(user, "hashed_password", hash_password(val))
        else:
            setattr(user, field, val)
    await db.commit()
    # If a superadmin's email was changed, re-sync ACME_EMAIL in .env
    from app.models.user import Role as _Role
    if email_changed and user.role == _Role.superadmin:
        try:
            from app.main import _sync_acme_email
            import asyncio as _asyncio
            _asyncio.create_task(_sync_acme_email())
        except Exception:
            pass
    return {"ok": True}


@router.patch("/me")
async def update_my_profile(
    body: ProfileUpdate,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the currently logged-in user's personal/contact details."""
    result = await db.execute(select(User).where(User.id == current.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    await db.commit()
    return {"ok": True, "preferred_name": user.preferred_name or ""}


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db), current=Depends(require_admin)):
    if user_id == current.id:
        raise HTTPException(400, "Cannot delete yourself")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    await db.delete(user)
    await db.commit()
