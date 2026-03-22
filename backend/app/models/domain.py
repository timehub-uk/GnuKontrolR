"""Domain model."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
import enum
from app.database import Base


class DomainType(str, enum.Enum):
    main    = "main"
    addon   = "addon"
    parked  = "parked"
    subdomain = "subdomain"
    redirect  = "redirect"


class DomainStatus(str, enum.Enum):
    active    = "active"
    suspended = "suspended"
    pending   = "pending"


class Domain(Base):
    __tablename__ = "domains"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String(253), unique=True, nullable=False, index=True)
    owner_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    domain_type = Column(SAEnum(DomainType), default=DomainType.main)
    status      = Column(SAEnum(DomainStatus), default=DomainStatus.active)
    doc_root    = Column(String(512), default="")
    ssl_enabled = Column(Boolean, default=False)
    ssl_expires = Column(DateTime, nullable=True)
    php_version = Column(String(16), default="8.2")
    redirect_to = Column(String(512), nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="domains")
