"""Country metadata: ISO code, name, flag SVG blob, and IP CIDR ranges."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, LargeBinary
from app.database import Base


class CountryData(Base):
    """Stores per-country metadata including flag SVG and cached IP ranges.

    Populated once via POST /api/geo/sync-countries (admin).
    Flags are fetched as SVG from flagcdn.com and stored as blobs so the
    frontend can display them without hitting an external CDN.
    IP CIDR list is refreshed from ipdeny.com on demand (stored as newline-
    separated text so SQLite can handle it without a separate range table).
    """
    __tablename__ = "country_data"

    id           = Column(Integer, primary_key=True, index=True)
    country_code = Column(String(2), unique=True, nullable=False, index=True)
    country_name = Column(String(128), nullable=False)
    flag_svg     = Column(LargeBinary, nullable=True)   # SVG blob from flagcdn.com
    flag_mime    = Column(String(32),  default="image/svg+xml")
    cidrs        = Column(Text, nullable=True)           # newline-separated CIDR list
    cidrs_at     = Column(DateTime, nullable=True)       # when cidrs were last fetched
    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
