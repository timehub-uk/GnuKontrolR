"""Data Processing Register (GDPR Art. 30) model."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from app.database import Base


class DataProcessingActivity(Base):
    """Record of a data processing activity for GDPR Art. 30 compliance."""
    __tablename__ = "data_processing_activities"

    id                  = Column(Integer, primary_key=True, index=True)
    activity_name       = Column(String(256), nullable=False)
    controller          = Column(String(256), default="")       # Data controller name
    processor           = Column(String(256), default="")       # Data processor
    purpose             = Column(Text, nullable=False)           # Purpose of processing
    lawful_basis        = Column(String(64), nullable=False)    # consent | contract | legal | vital | public | legitimate
    data_categories     = Column(Text, nullable=False)           # Categories of personal data
    data_subjects       = Column(String(256), default="")       # Categories of data subjects
    retention_period    = Column(String(128), default="")       # Retention schedule
    recipients          = Column(Text, default="")               # Third-party recipients
    transfers_overseas  = Column(Boolean, default=False)         # Cross-border transfers
    safeguards          = Column(Text, nullable=True)            # Safeguards for transfers
    is_active           = Column(Boolean, default=True)
    notes               = Column(Text, nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
