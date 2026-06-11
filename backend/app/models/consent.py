"""User consent records for GDPR compliance."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from app.database import Base


class ConsentRecord(Base):
    """Record of user consent for data processing activities."""
    __tablename__ = "consent_records"

    id              = Column(Integer, primary_key=True, index=True)
    user_id         = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    consent_type    = Column(String(64), nullable=False)       # privacy_policy | cookies | marketing | data_processing | tos
    version         = Column(String(16), nullable=False)       # e.g. "1.0", "2.1"
    granted         = Column(Boolean, nullable=False)          # true = granted, false = withdrawn
    ip_address      = Column(String(64), nullable=True)        # IP at time of consent
    user_agent      = Column(String(512), nullable=True)       # UA string
    granted_at      = Column(DateTime, default=datetime.utcnow)
    withdrawn_at    = Column(DateTime, nullable=True)          # when consent was withdrawn


class ConsentTemplate(Base):
    """Current version of each consent type for display."""
    __tablename__ = "consent_templates"

    id              = Column(Integer, primary_key=True, index=True)
    consent_type    = Column(String(64), unique=True, nullable=False)
    version         = Column(String(16), nullable=False)
    title           = Column(String(256), nullable=False)
    body            = Column(Text, nullable=False)              # Full consent text (Markdown)
    is_required     = Column(Boolean, default=True)            # Required or optional
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
