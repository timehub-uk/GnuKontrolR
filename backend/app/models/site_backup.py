"""SiteBackup — DB record for every backup created via the panel."""
import secrets
import uuid
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, BigInteger, ForeignKey
from app.database import Base


class SiteBackup(Base):
    __tablename__ = "site_backups"

    id          = Column(Integer, primary_key=True)
    domain      = Column(String(253), nullable=False, index=True)
    filename    = Column(String(512), nullable=False)
    backup_type = Column(String(32), default="website")   # website | files | db | full
    size        = Column(BigInteger, nullable=True)
    unique_id   = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    csc_token   = Column(String(64), nullable=False, default=lambda: secrets.token_hex(32))
    created_at  = Column(DateTime, default=datetime.utcnow)
    created_by  = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deleted     = Column(Integer, default=0)   # soft-delete flag
