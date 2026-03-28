"""Models for email SBL/DNSBL blacklist checking and email security policy."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Float
from app.database import Base


class DnsblList(Base):
    """A configured DNSBL/RBL service to query for blacklist checks."""
    __tablename__ = "dnsbl_lists"

    id          = Column(Integer, primary_key=True)
    name        = Column(String(128), unique=True, nullable=False)   # "Spamhaus SBL"
    zone        = Column(String(253), unique=True, nullable=False)   # "zen.spamhaus.org"
    description = Column(Text, nullable=True)
    enabled     = Column(Boolean, default=True)
    weight      = Column(Float, default=1.0)   # score multiplier
    created_at  = Column(DateTime, default=datetime.utcnow)


class DnsblCheckResult(Base):
    """A cached result of a DNSBL lookup for a given IP."""
    __tablename__ = "dnsbl_check_results"

    id          = Column(Integer, primary_key=True)
    ip          = Column(String(45), nullable=False, index=True)
    dnsbl_zone  = Column(String(253), nullable=False)
    listed      = Column(Boolean, default=False)
    return_code = Column(String(64), nullable=True)  # e.g. "127.0.0.2"
    checked_at  = Column(DateTime, default=datetime.utcnow)
    expires_at  = Column(DateTime, nullable=True)    # cache TTL
    reason      = Column(Text, nullable=True)


class EmailSecurityPolicy(Base):
    """Per-domain email security settings (SPF enforcement, DKIM, DMARC, DNSBL action)."""
    __tablename__ = "email_security_policies"

    id              = Column(Integer, primary_key=True)
    domain          = Column(String(253), unique=True, nullable=False, index=True)
    dnsbl_check     = Column(Boolean, default=True)   # reject if sender IP is blacklisted
    dnsbl_action    = Column(String(32), default="reject")  # reject | defer | flag
    spf_check       = Column(Boolean, default=True)
    dkim_check      = Column(Boolean, default=True)
    dmarc_check     = Column(Boolean, default=True)
    greylist        = Column(Boolean, default=False)
    rate_limit_per_hour = Column(Integer, default=200)  # outbound rate limit
    updated_at      = Column(DateTime, default=datetime.utcnow)


class SblEvent(Base):
    """Log of IPs rejected or flagged by DNSBL checks."""
    __tablename__ = "sbl_events"

    id          = Column(Integer, primary_key=True)
    ip          = Column(String(45), nullable=False, index=True)
    sender      = Column(String(512), nullable=True)
    recipient   = Column(String(512), nullable=True)
    domain      = Column(String(253), nullable=True, index=True)   # which domain was targeted
    action      = Column(String(32), nullable=False)  # "rejected" | "deferred" | "flagged"
    dnsbl_zone  = Column(String(253), nullable=True)
    score       = Column(Float, default=0.0)
    occurred_at = Column(DateTime, default=datetime.utcnow)
