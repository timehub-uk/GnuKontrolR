"""HostingPlan model — pre-defined service tiers with resource limits."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, Text
from app.database import Base


class HostingPlan(Base):
    __tablename__ = "hosting_plans"

    id              = Column(Integer, primary_key=True, index=True)
    name            = Column(String(64),  unique=True, nullable=False, index=True)
    description     = Column(Text,        default="")
    price_monthly   = Column(Float,       default=0.0)
    price_yearly    = Column(Float,       default=0.0)

    # Resource limits
    disk_quota_mb   = Column(Integer, default=5120)
    bw_quota_mb     = Column(Integer, default=51200)
    max_domains     = Column(Integer, default=10)
    max_databases   = Column(Integer, default=5)
    max_emails      = Column(Integer, default=20)

    # Container resources
    container_memory_mb = Column(Integer, default=1024)
    container_cpus      = Column(Float,   default=0.5)

    # Feature flags
    ssl_enabled     = Column(Boolean, default=True)
    ssh_enabled     = Column(Boolean, default=True)
    dns_management  = Column(Boolean, default=True)
    email_hosting   = Column(Boolean, default=True)

    is_active       = Column(Boolean, default=True)
    sort_order      = Column(Integer, default=0)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
