"""Domain management endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.database import get_db
from app.models.domain import Domain, DomainType, DomainStatus
from app.models.user import User, Role
from app.auth import get_current_user

router = APIRouter(prefix="/api/domains", tags=["domains"])


class DomainCreate(BaseModel):
    name: str
    domain_type: DomainType = DomainType.main
    doc_root: str = ""
    php_version: str = "8.2"
    redirect_to: Optional[str] = None


class DomainUpdate(BaseModel):
    status: Optional[DomainStatus] = None
    ssl_enabled: Optional[bool] = None
    php_version: Optional[str] = None
    redirect_to: Optional[str] = None
    doc_root: Optional[str] = None


@router.get("/")
async def list_domains(db: AsyncSession = Depends(get_db), current: User = Depends(get_current_user)):
    if current.role in (Role.superadmin, Role.admin):
        result = await db.execute(select(Domain).order_by(Domain.id))
    else:
        result = await db.execute(select(Domain).where(Domain.owner_id == current.id))
    domains = result.scalars().all()
    return [
        {
            "id": d.id, "name": d.name, "owner_id": d.owner_id,
            "domain_type": d.domain_type, "status": d.status,
            "ssl_enabled": d.ssl_enabled, "ssl_expires": d.ssl_expires,
            "php_version": d.php_version, "doc_root": d.doc_root,
            "redirect_to": d.redirect_to, "created_at": d.created_at,
        }
        for d in domains
    ]


@router.post("/", status_code=201)
async def create_domain(body: DomainCreate, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_user)):
    # Check quota
    result = await db.execute(select(Domain).where(Domain.owner_id == current.id))
    owned = len(result.scalars().all())
    if owned >= current.max_domains:
        raise HTTPException(400, f"Domain quota reached ({current.max_domains})")
    # Check uniqueness
    existing = await db.execute(select(Domain).where(Domain.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Domain already exists")
    domain = Domain(
        name=body.name,
        owner_id=current.id,
        domain_type=body.domain_type,
        doc_root=body.doc_root or f"/var/www/{body.name}/public_html",
        php_version=body.php_version,
        redirect_to=body.redirect_to,
    )
    db.add(domain)
    await db.commit()
    await db.refresh(domain)
    return {"id": domain.id, "name": domain.name, "status": domain.status}


@router.patch("/{domain_id}")
async def update_domain(domain_id: int, body: DomainUpdate, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_user)):
    result = await db.execute(select(Domain).where(Domain.id == domain_id))
    domain = result.scalar_one_or_none()
    if not domain:
        raise HTTPException(404, "Domain not found")
    if domain.owner_id != current.id and current.role not in (Role.superadmin, Role.admin):
        raise HTTPException(403, "Access denied")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(domain, field, val)
    domain.updated_at = datetime.utcnow()
    await db.commit()
    return {"ok": True}


@router.delete("/{domain_id}", status_code=204)
async def delete_domain(domain_id: int, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_user)):
    result = await db.execute(select(Domain).where(Domain.id == domain_id))
    domain = result.scalar_one_or_none()
    if not domain:
        raise HTTPException(404, "Domain not found")
    if domain.owner_id != current.id and current.role not in (Role.superadmin, Role.admin):
        raise HTTPException(403, "Access denied")
    await db.delete(domain)
    await db.commit()
