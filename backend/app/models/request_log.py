"""Per-user request log entries."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Index
from app.database import Base


class RequestLog(Base):
    __tablename__ = "request_logs"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id    = Column(String(36),  nullable=False, index=True)   # UUID
    method      = Column(String(10),  nullable=False)
    path        = Column(String(512), nullable=False)
    status      = Column(Integer,     nullable=False)
    duration_ms = Column(Float,       nullable=False)
    ip_hash     = Column(String(64),  nullable=False)               # SHA-256 of IP
    created_at  = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        # Fast lookup: user's recent entries
        Index("ix_request_logs_user_created", "user_id", "created_at"),
    )
