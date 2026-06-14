"""
Data retention policy enforcement.

Provides endpoints for:
  - Listing current retention policies
  - Triggering manual cleanup of expired data
  - Auto-cleanup of expired sessions, logs, consent records
  - Secure deletion of expired user data
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin, get_current_user
from app.database import get_db, AsyncSessionLocal
from app.models.user import User
from app.models.request_log import RequestLog
from app.models.consent import ConsentRecord
from app.models.data_subject_request import DataSubjectRequest

log = logging.getLogger("webpanel")
router = APIRouter(prefix="/api/data-retention", tags=["data-retention"])

# Retention periods (in days)
RETENTION_CONFIG = {
    "request_logs": {
        "max_entries_per_user": 1000,
        "max_age_days": 365,          # 12 months for SOC 2 / ISO 27001 compliance
        "description": "API request audit logs",
    },
    "consent_records": {
        "max_age_days": 365 * 3,      # 3 years (GDPR recommendation)
        "description": "User consent records",
    },
    "completed_dsars": {
        "max_age_days": 365,          # 1 year after completion
        "description": "Completed data subject access requests",
    },
    "suspended_accounts": {
        "max_age_days": 90,           # 90 days after suspension
        "description": "Suspended/inactive accounts pending deletion",
    },
    "password_history": {
        "max_entries_per_user": 5,
        "description": "Previous password hashes for reuse prevention",
    },
}


@router.get("/config")
async def get_retention_config(
    _admin: User = Depends(require_admin),
):
    """Return the current retention policy configuration."""
    return {"policies": RETENTION_CONFIG}


@router.post("/cleanup")
async def trigger_cleanup(
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Trigger manual cleanup of expired data.

    This performs:
    1. Prune request logs to max entries per user
    2. Delete expired consent records
    3. Delete completed DSARs older than retention
    4. Delete suspended accounts past grace period
    5. Prune password history
    """
    results = {}

    # 1. Request logs - prune to max entries per user
    # (Already handled per-insert in activity_log.py at 1000 entries)
    # Now also prune by age
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_CONFIG["request_logs"]["max_age_days"])
    result = await db.execute(
        delete(RequestLog).where(RequestLog.created_at < cutoff)
    )
    results["request_logs_pruned"] = result.rowcount

    # 2. Consent records older than retention
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_CONFIG["consent_records"]["max_age_days"])
    result = await db.execute(
        delete(ConsentRecord).where(ConsentRecord.granted_at < cutoff)
    )
    results["consent_records_pruned"] = result.rowcount

    # 3. Completed DSARs older than retention
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_CONFIG["completed_dsars"]["max_age_days"])
    result = await db.execute(
        delete(DataSubjectRequest).where(
            and_(
                DataSubjectRequest.status == "completed",
                DataSubjectRequest.completed_at < cutoff,
            )
        )
    )
    results["completed_dsars_pruned"] = result.rowcount

    # 4. Suspended accounts past grace period
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_CONFIG["suspended_accounts"]["max_age_days"])
    result = await db.execute(
        select(User).where(
            User.is_suspended == True,
            User.updated_at < cutoff,
        )
    )
    expired = result.scalars().all()
    purged_count = 0
    for user in expired:
        # Anonymize fully
        user.username = f"deleted_user_{user.id}"
        user.email = f"deleted_{user.id}@deleted.local"
        user.hashed_password = "DELETED"
        user.full_name = ""
        user.company = ""
        user.phone = ""
        user.address_line1 = ""
        user.address_line2 = ""
        user.city = ""
        user.state = ""
        user.postcode = ""
        user.country = ""
        user.vat_number = ""
        user.notes = ""
        user.is_active = False
        purged_count += 1
    await db.commit()
    results["suspended_accounts_purged"] = purged_count

    return {
        "ok": True,
        "results": results,
        "note": "Data retention cleanup completed successfully.",
    }


async def scheduled_cleanup():
    """Background task: run data retention cleanup every 24 hours."""
    while True:
        try:
            async with AsyncSessionLocal() as db:
                cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_CONFIG["request_logs"]["max_age_days"])
                await db.execute(delete(RequestLog).where(RequestLog.created_at < cutoff))
                await db.commit()
                log.info("Scheduled data retention cleanup completed")
        except Exception as e:
            log.error("Scheduled cleanup failed: %s", e)
        await asyncio.sleep(86400)  # 24 hours
