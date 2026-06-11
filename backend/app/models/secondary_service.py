"""Secondary (optional) service model — user-enrolled add-on containers."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from app.database import Base


class SecondaryService(Base):
    """Tracks optionally-deployed secondary services (Portainer, n8n, etc.).

    These are NOT installed by default. The admin discovers them via the
    services catalogue and explicitly enables them through a config modal.
    Once enabled, they are managed as Docker containers alongside master services.
    """
    __tablename__ = "secondary_services"

    id             = Column(Integer, primary_key=True, index=True)
    key            = Column(String(64), unique=True, nullable=False, index=True)
    name           = Column(String(128), nullable=False)
    description    = Column(String(512), default="")
    icon           = Column(String(8), default="🧩")
    category       = Column(String(32), default="other")
    enabled        = Column(Boolean, default=False, nullable=False)
    # JSON blob storing the user's config (port overrides, env vars, credentials)
    config         = Column(Text, default="{}")
    container_name = Column(String(128), default="")
    docker_image   = Column(String(256), default="")
    created_at     = Column(DateTime, default=datetime.utcnow)
    updated_at     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
