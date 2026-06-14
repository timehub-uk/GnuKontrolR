"""User model."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum as SAEnum, ForeignKey, Text
from sqlalchemy.orm import relationship
import enum
from app.database import Base, EncryptedString


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
    encrypted_password = Column(EncryptedString(256), nullable=True, default=None)
    full_name       = Column(EncryptedString(128), default="")
    role            = Column(SAEnum(Role), default=Role.user, nullable=False)
    is_active       = Column(Boolean, default=True)
    is_suspended    = Column(Boolean, default=False)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Extended customer profile
    preferred_name  = Column(EncryptedString(64),  default="")   # what the user wants to be called
    company         = Column(String(128), default="")
    phone           = Column(EncryptedString(32),  default="")
    address_line1   = Column(EncryptedString(256), default="")
    address_line2   = Column(EncryptedString(256), default="")
    city            = Column(String(64),  default="")
    state           = Column(String(64),  default="")
    postcode        = Column(EncryptedString(16),  default="")
    country         = Column(String(64),  default="")
    vat_number      = Column(EncryptedString(64),  default="")
    notes           = Column(EncryptedString(1024), default="")

    # Quotas
    disk_quota_mb  = Column(Integer, default=5120)   # 5 GB default
    bw_quota_mb    = Column(Integer, default=51200)  # 50 GB default
    max_domains    = Column(Integer, default=10)
    max_databases  = Column(Integer, default=5)
    max_emails     = Column(Integer, default=20)

    # Hosting plan
    plan_id = Column(Integer, ForeignKey("hosting_plans.id"), nullable=True, default=None)

    # Superadmin support PIN (bcrypt hash of 6-digit numeric PIN)
    support_pin_hash = Column(String(256), nullable=True, default=None)

    # Consent & GDPR fields
    consent_version   = Column(String(16), nullable=True, default=None)  # Last accepted consent version
    data_exported_at  = Column(DateTime, nullable=True)                   # Last data export timestamp
    erasure_requested = Column(Boolean, default=False)                    # Right to erasure flag
    erasure_scheduled = Column(DateTime, nullable=True)                   # When erasure will be executed
    marketing_opt_in  = Column(Boolean, default=False)                    # Marketing consent
    cookie_preferences = Column(Text, nullable=True)                      # JSON-encoded cookie preferences

    # Account security
    last_login_at   = Column(DateTime, nullable=True)                    # Last successful login
    last_login_ip   = Column(String(64), nullable=True)                  # Last login IP (hashed)
    password_changed_at = Column(DateTime, nullable=True)                # Last password change
    mfa_enabled     = Column(Boolean, default=False)                     # Whether MFA is active
    failed_logins   = Column(Integer, default=0)                         # Consecutive failed logins
    locked_until    = Column(DateTime, nullable=True)                    # Account lockout expiry
    recovery_codes_hash = Column(String(512), nullable=True)             # Hashed recovery codes

    domains   = relationship("Domain", back_populates="owner", cascade="all, delete-orphan")
    plan      = relationship("HostingPlan", foreign_keys=[plan_id])
