"""Password policy configuration model."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from app.database import Base


class PasswordPolicy(Base):
    """System-wide password policy configuration."""
    __tablename__ = "password_policies"

    id                  = Column(Integer, primary_key=True, index=True)
    min_length          = Column(Integer, default=12)
    require_uppercase   = Column(Boolean, default=True)
    require_lowercase   = Column(Boolean, default=True)
    require_digit       = Column(Boolean, default=True)
    require_special     = Column(Boolean, default=True)
    max_age_days        = Column(Integer, default=90)           # Password expiry
    prevent_reuse       = Column(Integer, default=5)            # Number of previous passwords to remember
    max_login_attempts  = Column(Integer, default=5)
    lockout_duration_m  = Column(Integer, default=15)           # Minutes
    is_active           = Column(Boolean, default=True)
    updated_by          = Column(Integer, nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PasswordHistory(Base):
    """Tracks previous password hashes for reuse prevention."""
    __tablename__ = "password_history"

    id              = Column(Integer, primary_key=True, index=True)
    user_id         = Column(Integer, nullable=False, index=True)
    hashed_password = Column(String(256), nullable=False)
    created_at      = Column(DateTime, default=datetime.utcnow)
