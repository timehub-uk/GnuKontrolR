"""Fail2ban jail, ban tracking, and geo-blocking models."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float
from app.database import Base


class Fail2banJail(Base):
    __tablename__ = "fail2ban_jails"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String(64), unique=True, nullable=False, index=True)
    enabled    = Column(Boolean, default=True)
    maxretry   = Column(Integer, default=5)
    findtime   = Column(Integer, default=600)    # seconds
    bantime    = Column(Integer, default=3600)   # seconds (-1 = permanent)
    port       = Column(String(128), default="")  # e.g. "http,https" or "22"
    filter_name = Column(String(64), default="")  # fail2ban filter name
    logpath    = Column(String(512), default="")
    comment    = Column(String(256), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Fail2banBan(Base):
    """Tracks bans applied by the panel (mirrors what's in fail2ban + manual bans)."""
    __tablename__ = "fail2ban_bans"

    id         = Column(Integer, primary_key=True, index=True)
    ip         = Column(String(64), nullable=False, index=True)
    jail       = Column(String(64), default="webpanel-manual")
    reason     = Column(String(256), default="")
    banned_at  = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)  # NULL = permanent
    active     = Column(Boolean, default=True)
    banned_by  = Column(String(64), default="system")


class GeoBlockRule(Base):
    """Per-country blocking rule — drives both fail2ban and iptables ipset."""
    __tablename__ = "geo_block_rules"

    id           = Column(Integer, primary_key=True, index=True)
    country_code = Column(String(2), unique=True, nullable=False, index=True)  # ISO 3166-1 alpha-2
    country_name = Column(String(128), nullable=False)
    blocked      = Column(Boolean, default=False)
    ipset_applied = Column(Boolean, default=False)  # whether currently in iptables ipset
    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
