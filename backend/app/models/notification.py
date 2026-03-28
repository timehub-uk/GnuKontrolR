"""Notification model — stores panel events for the superadmin notifications panel."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Index
from app.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id         = Column(Integer, primary_key=True, index=True)
    type       = Column(String(64),   nullable=False, index=True)   # domain_created, user_created, …
    title      = Column(String(256),  nullable=False)
    message    = Column(String(1024), nullable=False)
    details    = Column(Text,         nullable=False, default="{}")  # JSON blob
    is_read    = Column(Boolean,      nullable=False, default=False, index=True)
    created_at = Column(DateTime,     nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_notifications_read_created", "is_read", "created_at"),
    )
