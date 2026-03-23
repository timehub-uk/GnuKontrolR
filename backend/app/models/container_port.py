"""Per-container, per-service unique port assignments."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, UniqueConstraint
from app.database import Base


class ContainerPort(Base):
    """
    Tracks unique host port assignments for every service in every container.

    Each (domain, service) pair gets exactly one host port from a range
    specific to that service type. The port is never reused while the row
    exists, surviving panel restarts.

    Service name convention  →  port range
    ─────────────────────────────────────────
    ssh                         10200–14999   (SFTP / SSH)
    api                         not mapped    (internal Docker only)
    node                        15000–19999   (Node.js direct access)
    sftp_ro                     20000–24999   (read-only FTP/SFTP mirror)
    websocket                   25000–29999   (WS direct, optional)
    """
    __tablename__ = "container_ports"

    id         = Column(Integer, primary_key=True, index=True)
    domain     = Column(String(253), nullable=False, index=True)
    service    = Column(String(64),  nullable=False)  # ssh | node | websocket …
    host_port  = Column(Integer,     nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("domain", "service", name="uq_domain_service"),
    )
