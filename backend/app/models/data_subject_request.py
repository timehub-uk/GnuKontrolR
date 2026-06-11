"""Data Subject Access Request (DSAR) model for GDPR compliance."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from app.database import Base


class DataSubjectRequest(Base):
    """GDPR Data Subject Access Request tracking."""
    __tablename__ = "data_subject_requests"

    id              = Column(Integer, primary_key=True, index=True)
    user_id         = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    request_type    = Column(String(32), nullable=False)       # access | erasure | portability | rectification | restrict | object
    status          = Column(String(32), default="pending")    # pending | processing | completed | rejected
    notes           = Column(Text, default="")
    requested_at    = Column(DateTime, default=datetime.utcnow)
    completed_at    = Column(DateTime, nullable=True)
    completed_by    = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rejection_reason = Column(Text, nullable=True)
