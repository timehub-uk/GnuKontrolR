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
    return user


@router.patch("/{user_id}")
async def update_user(user_id: int, body: UserUpdate, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    for field, val in body.model_dump(exclude_none=True).items():
        if field == "password":
            setattr(user, "hashed_password", hash_password(val))
        else:
            setattr(user, field, val)
    await db.commit()
    return {"ok": True}


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
