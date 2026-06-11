"""Setup wizard state model — tracks first-time setup completion."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from app.database import Base


class SetupState(Base):
    __tablename__ = "setup_state"

    id              = Column(Integer, primary_key=True, index=True)
    step_index      = Column(Integer, default=0, nullable=False)
    completed       = Column(Boolean, default=False, nullable=False)
    secrets_changed = Column(Boolean, default=False)
    fail2ban_done   = Column(Boolean, default=False)
    geo_block_done  = Column(Boolean, default=False)
    grafana_done    = Column(Boolean, default=False)
    backup_cron_set = Column(Boolean, default=False)
    cve_cron_set    = Column(Boolean, default=False)
    update_cron_set = Column(Boolean, default=False)
    services_pruned = Column(Boolean, default=False)
    mfa_configured  = Column(Boolean, default=False)
    dsar_contact_set = Column(Boolean, default=False)
    data_retention_set = Column(Boolean, default=False)
    consent_seeded   = Column(Boolean, default=False)
    privacy_policy_done = Column(Boolean, default=False)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
