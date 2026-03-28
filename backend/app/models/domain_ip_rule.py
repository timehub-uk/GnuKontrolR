"""Per-domain IP blocking rules and country blocks."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from app.database import Base


class DomainIPRule(Base):
    """A specific IP address or CIDR range to block for a domain."""
    __tablename__ = "domain_ip_rules"

    id         = Column(Integer, primary_key=True, index=True)
    domain_id  = Column(Integer, ForeignKey("domains.id", ondelete="CASCADE"), nullable=False, index=True)
    ip_cidr    = Column(String(64), nullable=False)   # e.g. "1.2.3.4/32" or "10.0.0.0/8"
    reason     = Column(String(256), default="")
    active     = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class DomainCountryBlock(Base):
    """Block all IP ranges belonging to a country for a specific domain."""
    __tablename__ = "domain_country_blocks"

    id           = Column(Integer, primary_key=True, index=True)
    domain_id    = Column(Integer, ForeignKey("domains.id", ondelete="CASCADE"), nullable=False, index=True)
    country_code = Column(String(2), nullable=False)   # ISO 3166-1 alpha-2
    country_name = Column(String(128), nullable=False)
    active       = Column(Boolean, default=True)
    created_by   = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at   = Column(DateTime, default=datetime.utcnow)
    cidrs_cached_at = Column(DateTime, nullable=True)  # when CIDRs were last fetched
