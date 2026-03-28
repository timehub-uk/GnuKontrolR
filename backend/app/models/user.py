"""User model."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum as SAEnum
from sqlalchemy.orm import relationship
import enum
from app.database import Base


class Role(str, enum.Enum):
    superadmin = "superadmin"
    admin = "admin"
    reseller = "reseller"
    user = "user"


class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True, index=True)
    username        = Column(String(64),  unique=True, nullable=False, index=True)
    email           = Column(String(128), unique=True, nullable=False)
    hashed_password = Column(String(256), nullable=False)
    full_name       = Column(String(128), default="")
    role            = Column(SAEnum(Role), default=Role.user, nullable=False)
    is_active       = Column(Boolean, default=True)
    is_suspended    = Column(Boolean, default=False)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Extended customer profile
    preferred_name  = Column(String(64),  default="")   # what the user wants to be called
    company         = Column(String(128), default="")
    phone           = Column(String(32),  default="")
    address_line1   = Column(String(256), default="")
    address_line2   = Column(String(256), default="")
    city            = Column(String(64),  default="")
    state           = Column(String(64),  default="")
    postcode        = Column(String(16),  default="")
    country         = Column(String(64),  default="")
    vat_number      = Column(String(64),  default="")
    notes           = Column(String(1024), default="")

    # Quotas
    disk_quota_mb  = Column(Integer, default=5120)   # 5 GB default
    bw_quota_mb    = Column(Integer, default=51200)  # 50 GB default
    max_domains    = Column(Integer, default=10)
    max_databases  = Column(Integer, default=5)
    max_emails     = Column(Integer, default=20)

    # Superadmin support PIN (bcrypt hash of 6-digit numeric PIN)
    support_pin_hash = Column(String(256), nullable=True, default=None)

    domains   = relationship("Domain", back_populates="owner", cascade="all, delete-orphan")
