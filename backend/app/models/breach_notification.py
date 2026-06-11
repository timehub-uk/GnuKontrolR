"""Breach notification model for GDPR Art. 33-34 compliance."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from app.database import Base


class BreachEvent(Base):
    """Record of a security breach for notification tracking."""
    __tablename__ = "breach_events"

    id                  = Column(Integer, primary_key=True, index=True)
    title               = Column(String(256), nullable=False)
    description         = Column(Text, nullable=False)
    severity            = Column(String(16), default="medium")  # low | medium | high | critical
    detected_at         = Column(DateTime, default=datetime.utcnow)
    contained_at        = Column(DateTime, nullable=True)
    root_cause          = Column(Text, nullable=True)
    affected_users      = Column(Integer, default=0)
    data_categories     = Column(Text, default="")              # comma-separated
    notified_dpa        = Column(Boolean, default=False)         # GDPR Art. 33
    dpa_notified_at     = Column(DateTime, nullable=True)
    notified_affected   = Column(Boolean, default=False)         # GDPR Art. 34
    affected_notified_at = Column(DateTime, nullable=True)
    notification_method = Column(String(64), nullable=True)     # email | system | both
    status              = Column(String(32), default="open")    # open | investigating | contained | resolved
    resolution_notes    = Column(Text, nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
