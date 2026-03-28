"""Panel-side marketplace app cache tracking."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Boolean, UniqueConstraint
from app.database import Base


class AppCacheEntry(Base):
    """
    Tracks every version of a marketplace app that has been downloaded and
    cached on the panel host at /var/webpanel/app-cache/.

    Each row represents one downloaded archive file.
    The canonical filename (e.g. 'wordpress.tar.gz') is marked is_canonical=True
    and is what site containers actually read from the bind-mounted cache dir.
    Older versioned copies (e.g. 'wordpress-1711900000.tar.gz') have is_canonical=False
    and are kept for rollback / audit until pruned.

    Uniqueness: (app_id, filename) — one row per physical file.
    """
    __tablename__ = "app_cache"

    id           = Column(Integer,     primary_key=True, index=True)
    app_id       = Column(String(64),  nullable=False, index=True)
    filename     = Column(String(255), nullable=False)          # basename only
    size_bytes   = Column(BigInteger,  nullable=False, default=0)
    is_canonical = Column(Boolean,     nullable=False, default=False)  # True = the "current" file containers read
    source_url   = Column(String(1024), nullable=True)
    cached_at    = Column(DateTime,    default=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime,    nullable=True)            # updated when a container install hits this file

    __table_args__ = (
        UniqueConstraint("app_id", "filename", name="uq_app_cache_app_filename"),
    )
