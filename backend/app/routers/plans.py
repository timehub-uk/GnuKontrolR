"""Hosting plan CRUD endpoints (admin+)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.database import get_db
from app.models.hosting_plan import HostingPlan
from app.models.user import User, Role
from app.auth import require_admin

router = APIRouter(prefix="/api/plans", tags=["plans"])


class PlanCreate(BaseModel):
    name: str
    description: str = ""
    price_monthly: float = 0.0
    price_yearly: float = 0.0
    disk_quota_mb: int = 5120
    bw_quota_mb: int = 51200
    max_domains: int = 10
    max_databases: int = 5
    max_emails: int = 20
    container_memory_mb: int = 1024
    container_cpus: float = 0.5
    ssl_enabled: bool = True
    ssh_enabled: bool = True
    dns_management: bool = True
    email_hosting: bool = True
    is_active: bool = True
    sort_order: int = 0


class PlanUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price_monthly: Optional[float] = None
    price_yearly: Optional[float] = None
    disk_quota_mb: Optional[int] = None
    bw_quota_mb: Optional[int] = None
    max_domains: Optional[int] = None
    max_databases: Optional[int] = None
    max_emails: Optional[int] = None
    container_memory_mb: Optional[int] = None
    container_cpus: Optional[float] = None
    ssl_enabled: Optional[bool] = None
    ssh_enabled: Optional[bool] = None
    dns_management: Optional[bool] = None
    email_hosting: Optional[bool] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class AssignPlan(BaseModel):
    plan_id: Optional[int] = None  # None = remove plan assignment


def _plan_dict(plan: HostingPlan) -> dict:
    return {
        "id": plan.id,
        "name": plan.name,
        "description": plan.description,
        "price_monthly": plan.price_monthly,
        "price_yearly": plan.price_yearly,
        "disk_quota_mb": plan.disk_quota_mb,
        "bw_quota_mb": plan.bw_quota_mb,
        "max_domains": plan.max_domains,
        "max_databases": plan.max_databases,
        "max_emails": plan.max_emails,
        "container_memory_mb": plan.container_memory_mb,
        "container_cpus": plan.container_cpus,
        "ssl_enabled": plan.ssl_enabled,
        "ssh_enabled": plan.ssh_enabled,
        "dns_management": plan.dns_management,
        "email_hosting": plan.email_hosting,
        "is_active": plan.is_active,
        "sort_order": plan.sort_order,
        "created_at": plan.created_at,
        "updated_at": plan.updated_at,
    }


@router.get("/")
async def list_plans(db: AsyncSession = Depends(get_db)):
    """List all plans (public)."""
    result = await db.execute(select(HostingPlan).order_by(HostingPlan.sort_order, HostingPlan.name))
    return [_plan_dict(p) for p in result.scalars().all()]


@router.get("/{plan_id}")
async def get_plan(plan_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(HostingPlan).where(HostingPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Plan not found")
    return _plan_dict(plan)


@router.post("/", status_code=201)
async def create_plan(body: PlanCreate, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    existing = await db.execute(select(HostingPlan).where(HostingPlan.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(409, "A plan with this name already exists")
    plan = HostingPlan(**body.model_dump())
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return _plan_dict(plan)


@router.patch("/{plan_id}")
async def update_plan(plan_id: int, body: PlanUpdate, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(HostingPlan).where(HostingPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Plan not found")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(plan, field, val)
    plan.updated_at = datetime.utcnow()
    await db.commit()
    return _plan_dict(plan)


@router.delete("/{plan_id}", status_code=204)
async def delete_plan(plan_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(HostingPlan).where(HostingPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Plan not found")
    await db.delete(plan)
    await db.commit()


@router.post("/assign/{user_id}")
async def assign_plan_to_user(user_id: int, body: AssignPlan, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    """Assign a hosting plan to a user, applying the plan's resource limits."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    if body.plan_id is not None:
        plan_result = await db.execute(select(HostingPlan).where(HostingPlan.id == body.plan_id))
        plan = plan_result.scalar_one_or_none()
        if not plan:
            raise HTTPException(404, "Plan not found")
        user.plan_id = plan.id
        # Apply plan resource limits to the user
        user.disk_quota_mb = plan.disk_quota_mb
        user.bw_quota_mb = plan.bw_quota_mb
        user.max_domains = plan.max_domains
        user.max_databases = plan.max_databases
        user.max_emails = plan.max_emails
    else:
        user.plan_id = None
    await db.commit()
    return {"ok": True, "plan_id": user.plan_id}
