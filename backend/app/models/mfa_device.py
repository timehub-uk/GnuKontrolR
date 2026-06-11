"""Multi-Factor Authentication device model."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from app.database import Base


class MFADevice(Base):
    """TOTP device registered by a user."""
    __tablename__ = "mfa_devices"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name        = Column(String(64), default="default")       # user-friendly label
    secret      = Column(String(256), nullable=False)          # encrypted TOTP secret
    algorithm   = Column(String(16), default="SHA1")           # SHA1 | SHA256 | SHA512
    digits      = Column(Integer, default=6)                   # 6 or 8
    period      = Column(Integer, default=30)                  # TOTP period in seconds
    is_active   = Column(Boolean, default=True)
    last_used   = Column(DateTime, nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)
