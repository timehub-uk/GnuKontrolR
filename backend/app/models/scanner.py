"""Models for antivirus scan results, malware detections, and sanitization log."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Float
from app.database import Base


class ScanJob(Base):
    """A full-domain antivirus scan run triggered by an admin."""
    __tablename__ = "scan_jobs"

    id          = Column(Integer, primary_key=True)
    domain      = Column(String(253), nullable=False, index=True)
    area        = Column(String(32), default="public")   # public | uploads | private | all
    status      = Column(String(32), default="pending")  # pending | running | done | failed
    started_at  = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    total_files = Column(Integer, default=0)
    infected    = Column(Integer, default=0)
    clean       = Column(Integer, default=0)
    errors      = Column(Integer, default=0)
    triggered_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    summary     = Column(Text, nullable=True)   # JSON list of findings


class MalwareAlert(Base):
    """Individual file flagged by AV or malware pattern heuristics."""
    __tablename__ = "malware_alerts"

    id          = Column(Integer, primary_key=True)
    scan_job_id = Column(Integer, ForeignKey("scan_jobs.id", ondelete="CASCADE"), nullable=True)
    domain      = Column(String(253), nullable=False, index=True)
    area        = Column(String(32), nullable=False)
    filepath    = Column(String(2048), nullable=False)
    threat_name = Column(String(255), nullable=True)   # e.g. "PHP.Webshell.A"
    detection   = Column(String(64), nullable=True)    # "clamav" | "heuristic" | "manual"
    severity    = Column(String(16), default="medium") # low | medium | high | critical
    quarantined = Column(Boolean, default=False)
    resolved    = Column(Boolean, default=False)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    detected_at = Column(DateTime, default=datetime.utcnow)
    notes       = Column(Text, nullable=True)


class SanitizeLog(Base):
    """Record of each file sanitization action."""
    __tablename__ = "sanitize_log"

    id          = Column(Integer, primary_key=True)
    domain      = Column(String(253), nullable=False, index=True)
    area        = Column(String(32), nullable=False)
    filepath    = Column(String(2048), nullable=False)
    action      = Column(String(64), nullable=False)   # "strip_php_exec" | "strip_eval" | "remove_base64" | ...
    lines_changed = Column(Integer, default=0)
    performed_at  = Column(DateTime, default=datetime.utcnow)
    performed_by  = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    backup_path   = Column(String(2048), nullable=True)  # path to original backup
