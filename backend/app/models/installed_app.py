"""Tracks marketplace apps installed on customer domains."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class InstalledApp(Base):
    """
    One row per installed marketplace app instance.
    domain_name + app_id is unique — one WordPress per domain.
    Stores enough info to show the user their installations and allow
    remove/repair/reset without querying the container.
    """
    __tablename__ = "installed_apps"

    id          = Column(Integer,    primary_key=True, index=True)
    owner_id    = Column(Integer,    ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    domain_name = Column(String(253), nullable=False, index=True)
    app_id      = Column(String(64),  nullable=False)
    app_name    = Column(String(128), nullable=False)
    app_version = Column(String(64),  nullable=True)
    install_path = Column(String(512), nullable=False, default="/")
    vdns        = Column(String(512), nullable=True)   # e.g. https://wordpress.example.com
    admin_url   = Column(String(512), nullable=True)
    status      = Column(String(32),  nullable=False, default="installed")  # installed | error | removed
    installed_at = Column(DateTime,   default=datetime.utcnow, nullable=False)
    updated_at  = Column(DateTime,    default=datetime.utcnow, onupdate=datetime.utcnow)
    notes       = Column(Text,        nullable=True)
