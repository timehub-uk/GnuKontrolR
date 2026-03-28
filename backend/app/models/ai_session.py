"""AI session and activity log models."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Float, ForeignKey
from app.database import Base


class AiSession(Base):
    """Tracks every AI session start/stop per user+domain+tool."""
    __tablename__ = "ai_sessions"

    id            = Column(Integer, primary_key=True)
    user_id       = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    domain        = Column(String(253), nullable=False, index=True)
    tool          = Column(String(32), default="opencode")   # opencode | claude
    agent         = Column(String(64), default="general")
    container     = Column(String(128), nullable=True)       # AI container name
    started_at    = Column(DateTime, default=datetime.utcnow)
    ended_at      = Column(DateTime, nullable=True)
    duration_s    = Column(Float, nullable=True)
    ended_reason  = Column(String(64), nullable=True)        # "user_stop" | "timeout" | "error"


class AiActivityLog(Base):
    """Per-message AI activity log — every prompt and response tracked."""
    __tablename__ = "ai_activity_log"

    id            = Column(Integer, primary_key=True)
    session_id    = Column(Integer, ForeignKey("ai_sessions.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id       = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    domain        = Column(String(253), nullable=False, index=True)
    tool          = Column(String(32), default="opencode")
    agent         = Column(String(64), default="general")
    direction     = Column(String(8), nullable=False)         # "in" (user) | "out" (AI)
    message       = Column(Text, nullable=True)
    tokens_est    = Column(Integer, nullable=True)            # rough token estimate
    model         = Column(String(64), nullable=True)         # model name if known
    flagged       = Column(Boolean, default=False)            # abuse detection flag
    flag_reason   = Column(String(128), nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow, index=True)


class AiContainerRecord(Base):
    """Tracks provisioned AI containers so they can be reused and audited."""
    __tablename__ = "ai_containers"

    id            = Column(Integer, primary_key=True)
    name          = Column(String(128), unique=True, nullable=False, index=True)
    tool          = Column(String(32), nullable=False)
    user_id       = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    created_at    = Column(DateTime, default=datetime.utcnow)
    last_used_at  = Column(DateTime, nullable=True)
    total_sessions = Column(Integer, default=0)
    status        = Column(String(32), default="running")     # running | stopped | removed
