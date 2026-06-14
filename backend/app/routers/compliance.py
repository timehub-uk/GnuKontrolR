"""
Compliance & Privacy API — GDPR, privacy rights, and data governance.

Endpoints:
  ── Consent ──
  GET    /api/compliance/consent/templates         — list consent templates
  POST   /api/compliance/consent/{type}/accept     — accept a consent
  POST   /api/compliance/consent/{type}/withdraw   — withdraw a consent
  GET    /api/compliance/consent/status            — get my consent status

  ── Data Subject Rights (DSAR) ──
  POST   /api/compliance/dsar                      — submit a DSAR
  GET    /api/compliance/dsar                      — list my DSARs
  GET    /api/compliance/dsar/{id}                 — get DSAR details
  POST   /api/compliance/dsar/{id}/respond         — admin: respond to DSAR

  ── Right to Erasure ──
  POST   /api/compliance/erasure                   — request account deletion
  POST   /api/compliance/erasure/confirm           — confirm with second factor

  ── Data Portability ──
  GET    /api/compliance/export                    — export my data (JSON)
  GET    /api/compliance/export/csv                — export my data (CSV)

  ── Data Processing Register (admin) ──
  GET    /api/compliance/processing                — list processing activities
  POST   /api/compliance/processing                — create processing activity
  PUT    /api/compliance/processing/{id}           — update
  DELETE /api/compliance/processing/{id}           — delete

  ── Breach Notifications (admin) ──
  GET    /api/compliance/breaches                  — list breach events
  POST   /api/compliance/breaches                  — record a breach event
  PUT    /api/compliance/breaches/{id}             — update breach status
  POST   /api/compliance/breaches/{id}/notify      — send breach notification
"""
import csv
import io
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_admin, require_superadmin
from app.database import get_db
from app.models.user import User, Role
from app.models.consent import ConsentRecord, ConsentTemplate
from app.models.data_subject_request import DataSubjectRequest
from app.models.data_processing import DataProcessingActivity
from app.models.breach_notification import BreachEvent

log = logging.getLogger("webpanel")
router = APIRouter(prefix="/api/compliance", tags=["compliance"])


# ═════════════════════════════════════════════════════════════════════════════
# CONSENT MANAGEMENT
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/consent/templates")
async def list_consent_templates(
    db: AsyncSession = Depends(get_db),
):
    """List all active consent templates with current versions."""
    result = await db.execute(
        select(ConsentTemplate).order_by(ConsentTemplate.consent_type)
    )
    templates = result.scalars().all()
    return [
        {
            "id": t.id,
            "consent_type": t.consent_type,
            "version": t.version,
            "title": t.title,
            "body": t.body,
            "is_required": t.is_required,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        }
        for t in templates
    ]


class ConsentAction(BaseModel):
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


@router.post("/consent/{consent_type}/accept")
async def accept_consent(
    consent_type: str,
    body: Optional[ConsentAction] = None,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record user acceptance of a consent type."""
    # Validate consent type exists
    tmpl = await db.execute(
        select(ConsentTemplate).where(ConsentTemplate.consent_type == consent_type)
    )
    template = tmpl.scalar_one_or_none()
    if not template:
        raise HTTPException(404, f"Unknown consent type: {consent_type}")

    # Record acceptance
    record = ConsentRecord(
        user_id=current.id,
        consent_type=consent_type,
        version=template.version,
        granted=True,
        ip_address=body.ip_address if body else None,
        user_agent=body.user_agent if body else None,
    )
    db.add(record)
    await db.commit()

    return {"ok": True, "consent_type": consent_type, "version": template.version, "granted": True}


@router.post("/consent/{consent_type}/withdraw")
async def withdraw_consent(
    consent_type: str,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Withdraw previously granted consent."""
    # Find the most recent grant
    result = await db.execute(
        select(ConsentRecord)
        .where(
            ConsentRecord.user_id == current.id,
            ConsentRecord.consent_type == consent_type,
            ConsentRecord.granted == True,
        )
        .order_by(ConsentRecord.granted_at.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(404, "No active consent found for this type")

    # Record withdrawal
    withdraw = ConsentRecord(
        user_id=current.id,
        consent_type=consent_type,
        version=record.version,
        granted=False,
        withdrawn_at=datetime.now(timezone.utc),
    )
    db.add(withdraw)
    await db.commit()

    return {"ok": True, "consent_type": consent_type, "granted": False}


@router.get("/consent/status")
async def get_consent_status(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current consent status for all consent types for this user."""
    # Get all templates
    tmpl_result = await db.execute(select(ConsentTemplate))
    templates = tmpl_result.scalars().all()

    result = []
    for t in templates:
        # Get latest record for this user + type
        record_result = await db.execute(
            select(ConsentRecord)
            .where(
                ConsentRecord.user_id == current.id,
                ConsentRecord.consent_type == t.consent_type,
            )
            .order_by(ConsentRecord.granted_at.desc())
            .limit(1)
        )
        record = record_result.scalar_one_or_none()

        result.append({
            "consent_type": t.consent_type,
            "title": t.title,
            "version": t.version,
            "is_required": t.is_required,
            "granted": record.granted if record else False,
            "granted_at": record.granted_at.isoformat() if record and record.granted else None,
            "needs_reconsent": record.version != t.version if record else True,
        })

    return {"consents": result}


# ═════════════════════════════════════════════════════════════════════════════
# DATA SUBJECT ACCESS REQUESTS (DSAR)
# ═════════════════════════════════════════════════════════════════════════════

class DSARCreate(BaseModel):
    request_type: str  # access | erasure | portability | rectification | restrict | object
    notes: str = ""


@router.post("/dsar")
async def create_dsar(
    body: DSARCreate,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit a Data Subject Access Request (GDPR Art. 15-22)."""
    valid_types = {"access", "erasure", "portability", "rectification", "restrict", "object"}
    if body.request_type not in valid_types:
        raise HTTPException(400, f"Invalid request type. Must be one of: {', '.join(valid_types)}")

    dsar = DataSubjectRequest(
        user_id=current.id,
        request_type=body.request_type,
        notes=body.notes,
    )
    db.add(dsar)
    await db.commit()
    await db.refresh(dsar)

    # Notify admins
    try:
        from app.notify import push as notify_push
        import asyncio
        asyncio.create_task(notify_push(
            db, type="dsar_submitted",
            title=f"DSAR submitted: {body.request_type}",
            message=f"User '{current.username}' requested: {body.request_type}",
        ))
    except Exception:
        pass

    return {
        "id": dsar.id,
        "request_type": dsar.request_type,
        "status": dsar.status,
        "notes": dsar.notes,
        "requested_at": dsar.requested_at.isoformat(),
    }


@router.get("/dsar")
async def list_dsar(
    status: Optional[str] = None,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _admin: Optional[User] = Depends(require_admin),
):
    """List DSARs (admin: all, user: own)."""
    query = select(DataSubjectRequest)
    if current.role not in (Role.superadmin, Role.admin):
        query = query.where(DataSubjectRequest.user_id == current.id)
    if status:
        query = query.where(DataSubjectRequest.status == status)
    query = query.order_by(DataSubjectRequest.requested_at.desc())

    result = await db.execute(query)
    dsars = result.scalars().all()
    return [
        {
            "id": d.id,
            "user_id": d.user_id,
            "request_type": d.request_type,
            "status": d.status,
            "notes": d.notes,
            "requested_at": d.requested_at.isoformat(),
            "completed_at": d.completed_at.isoformat() if d.completed_at else None,
            "rejection_reason": d.rejection_reason,
        }
        for d in dsars
    ]


@router.get("/dsar/{dsar_id}")
async def get_dsar(
    dsar_id: int,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get DSAR details."""
    dsar = await db.get(DataSubjectRequest, dsar_id)
    if not dsar:
        raise HTTPException(404, "DSAR not found")
    if current.role not in (Role.superadmin, Role.admin) and dsar.user_id != current.id:
        raise HTTPException(403, "Access denied")
    return {
        "id": dsar.id,
        "user_id": dsar.user_id,
        "request_type": dsar.request_type,
        "status": dsar.status,
        "notes": dsar.notes,
        "requested_at": dsar.requested_at.isoformat(),
        "completed_at": dsar.completed_at.isoformat() if dsar.completed_at else None,
        "completed_by": dsar.completed_by,
        "rejection_reason": dsar.rejection_reason,
    }


class DSARResponse(BaseModel):
    status: str  # completed | rejected
    notes: str = ""
    rejection_reason: str = ""


@router.post("/dsar/{dsar_id}/respond")
async def respond_dsar(
    dsar_id: int,
    body: DSARResponse,
    current: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin: respond to a DSAR (complete or reject)."""
    dsar = await db.get(DataSubjectRequest, dsar_id)
    if not dsar:
        raise HTTPException(404, "DSAR not found")

    dsar.status = body.status
    dsar.completed_at = datetime.now(timezone.utc)
    dsar.completed_by = current.id
    if body.status == "rejected":
        dsar.rejection_reason = body.rejection_reason
    if body.notes:
        dsar.notes = (dsar.notes or "") + f"\n[Admin response] {body.notes}"
    await db.commit()
    return {"ok": True, "status": dsar.status}


# ═════════════════════════════════════════════════════════════════════════════
# RIGHT TO ERASURE (GDPR Art. 17)
# ═════════════════════════════════════════════════════════════════════════════

class ErasureRequest(BaseModel):
    confirmation: str  # must equal "DELETE MY ACCOUNT"
    password: str      # re-authentication


@router.post("/erasure")
async def request_erasure(
    body: ErasureRequest,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Request account deletion (right to erasure / right to be forgotten).

    The user must:
      1. Type "DELETE MY ACCOUNT" as confirmation
      2. Provide their current password
    """
    if body.confirmation != "DELETE MY ACCOUNT":
        raise HTTPException(400, 'Please type "DELETE MY ACCOUNT" to confirm')

    from app.auth import verify_password as _verify_pass
    if not _verify_pass(body.password, current.hashed_password):
        raise HTTPException(400, "Invalid password")

    # Create a DSAR for the erasure
    dsar = DataSubjectRequest(
        user_id=current.id,
        request_type="erasure",
        status="processing",
        notes="Self-service account deletion requested",
    )
    db.add(dsar)

    # Schedule a grace period marker (7 days before actual deletion)
    current.is_active = False
    current.is_suspended = True
    await db.commit()

    return {
        "ok": True,
        "message": (
            "Your account has been scheduled for deletion. "
            "You have 7 days to cancel by contacting support. "
            "After that, all your data will be permanently removed."
        ),
        "dsar_id": dsar.id,
    }


@router.post("/erasure/confirm")
async def confirm_erasure(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin: immediately process pending erasure requests (manual trigger)."""
    result = await db.execute(
        select(DataSubjectRequest).where(
            DataSubjectRequest.request_type == "erasure",
            DataSubjectRequest.status == "processing",
        )
    )
    dsars = result.scalars().all()

    purged = 0
    for dsar in dsars:
        user = await db.get(User, dsar.user_id)
        if user:
            # Anonymize user data
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
            user.is_suspended = True
            user.preferred_name = ""

        dsar.status = "completed"
        dsar.completed_at = datetime.now(timezone.utc)
        dsar.completed_by = current.id
        purged += 1

    await db.commit()
    return {"ok": True, "purged": purged}


# ═════════════════════════════════════════════════════════════════════════════
# DATA PORTABILITY (GDPR Art. 20)
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/export")
async def export_data(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export all user data as JSON (GDPR Art. 20 - data portability)."""
    user = await db.get(User, current.id)
    if not user:
        raise HTTPException(404, "User not found")

    # Collect all user-related data
    export = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "account": {
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "preferred_name": user.preferred_name or "",
            "role": user.role,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        },
        "profile": {
            "company": user.company or "",
            "phone": user.phone or "",
            "address_line1": user.address_line1 or "",
            "address_line2": user.address_line2 or "",
            "city": user.city or "",
            "state": user.state or "",
            "postcode": user.postcode or "",
            "country": user.country or "",
            "vat_number": user.vat_number or "",
        },
        "quotas": {
            "disk_quota_mb": user.disk_quota_mb,
            "bw_quota_mb": user.bw_quota_mb,
            "max_domains": user.max_domains,
            "max_databases": user.max_databases,
            "max_emails": user.max_emails,
        },
    }

    # Add domains
    from app.models.domain import Domain
    dom_result = await db.execute(
        select(Domain).where(Domain.owner_id == user.id)
    )
    domains = dom_result.scalars().all()
    export["domains"] = [
        {
            "name": d.name,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in domains
    ]

    # Add consent records
    consent_result = await db.execute(
        select(ConsentRecord).where(ConsentRecord.user_id == user.id)
    )
    export["consent_records"] = [
        {
            "consent_type": c.consent_type,
            "version": c.version,
            "granted": c.granted,
            "granted_at": c.granted_at.isoformat() if c.granted_at else None,
            "withdrawn_at": c.withdrawn_at.isoformat() if c.withdrawn_at else None,
        }
        for c in consent_result.scalars().all()
    ]

    return export


@router.get("/export/csv")
async def export_data_csv(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export account data as CSV."""
    user = await db.get(User, current.id)
    if not user:
        raise HTTPException(404, "User not found")

    output = io.StringIO()
    writer = csv.writer(output)

    # Account info
    writer.writerow(["Field", "Value"])
    writer.writerow(["username", user.username])
    writer.writerow(["email", user.email])
    writer.writerow(["full_name", user.full_name])
    writer.writerow(["role", user.role])
    writer.writerow(["created_at", user.created_at.isoformat() if user.created_at else ""])
    writer.writerow([])
    writer.writerow(["Profile Field", "Value"])
    writer.writerow(["company", user.company or ""])
    writer.writerow(["phone", user.phone or ""])
    writer.writerow(["address_line1", user.address_line1 or ""])
    writer.writerow(["city", user.city or ""])
    writer.writerow(["state", user.state or ""])
    writer.writerow(["postcode", user.postcode or ""])
    writer.writerow(["country", user.country or ""])

    csv_content = output.getvalue()
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="gnukontrolr-export-{user.username}.csv"',
        },
    )


# ═════════════════════════════════════════════════════════════════════════════
# DATA PROCESSING REGISTER (GDPR Art. 30)
# ═════════════════════════════════════════════════════════════════════════════

class ProcessingActivityCreate(BaseModel):
    activity_name: str
    controller: str = ""
    processor: str = ""
    purpose: str
    lawful_basis: str
    data_categories: str
    data_subjects: str = ""
    retention_period: str = ""
    recipients: str = ""
    transfers_overseas: bool = False
    safeguards: Optional[str] = None
    notes: Optional[str] = None


@router.get("/processing")
async def list_processing_activities(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """List all data processing activities (GDPR Art. 30 register)."""
    result = await db.execute(
        select(DataProcessingActivity).order_by(DataProcessingActivity.activity_name)
    )
    activities = result.scalars().all()
    return [
        {
            "id": a.id,
            "activity_name": a.activity_name,
            "controller": a.controller,
            "processor": a.processor,
            "purpose": a.purpose,
            "lawful_basis": a.lawful_basis,
            "data_categories": a.data_categories,
            "data_subjects": a.data_subjects,
            "retention_period": a.retention_period,
            "recipients": a.recipients,
            "transfers_overseas": a.transfers_overseas,
            "safeguards": a.safeguards,
            "is_active": a.is_active,
            "notes": a.notes,
            "updated_at": a.updated_at.isoformat() if a.updated_at else None,
        }
        for a in activities
    ]


@router.post("/processing")
async def create_processing_activity(
    body: ProcessingActivityCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Add a data processing activity to the register."""
    valid_bases = {"consent", "contract", "legal", "vital", "public", "legitimate"}
    if body.lawful_basis not in valid_bases:
        raise HTTPException(400, f"Invalid lawful basis. Must be one of: {', '.join(valid_bases)}")

    activity = DataProcessingActivity(**body.model_dump())
    db.add(activity)
    await db.commit()
    await db.refresh(activity)
    return {
        "id": activity.id,
        "activity_name": activity.activity_name,
        "lawful_basis": activity.lawful_basis,
        "ok": True,
    }


@router.put("/processing/{activity_id}")
async def update_processing_activity(
    activity_id: int,
    body: ProcessingActivityCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Update a data processing activity."""
    activity = await db.get(DataProcessingActivity, activity_id)
    if not activity:
        raise HTTPException(404, "Activity not found")
    for field, value in body.model_dump().items():
        setattr(activity, field, value)
    await db.commit()
    return {"ok": True}


@router.delete("/processing/{activity_id}", status_code=204)
async def delete_processing_activity(
    activity_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Delete a data processing activity."""
    activity = await db.get(DataProcessingActivity, activity_id)
    if not activity:
        raise HTTPException(404, "Activity not found")
    await db.delete(activity)
    await db.commit()


# ═════════════════════════════════════════════════════════════════════════════
# BREACH NOTIFICATIONS (GDPR Art. 33-34)
# ═════════════════════════════════════════════════════════════════════════════

class BreachCreate(BaseModel):
    title: str
    description: str
    severity: str = "medium"
    affected_users: int = 0
    data_categories: str = ""


@router.get("/breaches")
async def list_breaches(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """List all breach events."""
    query = select(BreachEvent).order_by(BreachEvent.detected_at.desc())
    if status:
        query = query.where(BreachEvent.status == status)

    result = await db.execute(query)
    breaches = result.scalars().all()
    return [
        {
            "id": b.id,
            "title": b.title,
            "severity": b.severity,
            "status": b.status,
            "detected_at": b.detected_at.isoformat(),
            "affected_users": b.affected_users,
            "data_categories": b.data_categories,
            "notified_dpa": b.notified_dpa,
            "notified_affected": b.notified_affected,
            "dpa_notified_at": b.dpa_notified_at.isoformat() if b.dpa_notified_at else None,
        }
        for b in breaches
    ]


@router.post("/breaches")
async def create_breach(
    body: BreachCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Record a new breach event."""
    valid_severities = {"low", "medium", "high", "critical"}
    if body.severity not in valid_severities:
        raise HTTPException(400, f"Invalid severity. Must be one of: {', '.join(valid_severities)}")

    breach = BreachEvent(
        title=body.title,
        description=body.description,
        severity=body.severity,
        affected_users=body.affected_users,
        data_categories=body.data_categories,
    )
    db.add(breach)
    await db.commit()
    await db.refresh(breach)

    # Auto-notify for critical/high severity
    if body.severity in ("critical", "high"):
        try:
            from app.notify import push as notify_push
            import asyncio
            asyncio.create_task(notify_push(
                db, type="breach_detected",
                title=f"[{body.severity.upper()}] Breach: {body.title}",
                message=f"Severity: {body.severity}, Affected users: {body.affected_users}",
            ))
        except Exception:
            pass

    return {
        "id": breach.id,
        "title": breach.title,
        "severity": breach.severity,
        "status": breach.status,
    }


class BreachUpdate(BaseModel):
    status: Optional[str] = None
    contained_at: Optional[datetime] = None
    root_cause: Optional[str] = None
    resolution_notes: Optional[str] = None


@router.put("/breaches/{breach_id}")
async def update_breach(
    breach_id: int,
    body: BreachUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Update a breach event."""
    breach = await db.get(BreachEvent, breach_id)
    if not breach:
        raise HTTPException(404, "Breach not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(breach, field, value)
    await db.commit()
    return {"ok": True}


@router.post("/breaches/{breach_id}/notify")
async def send_breach_notification(
    breach_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Send breach notifications to DPA (Art. 33) and affected users (Art. 34)."""
    breach = await db.get(BreachEvent, breach_id)
    if not breach:
        raise HTTPException(404, "Breach not found")

    results = {"dpa_notified": False, "affected_notified": False}

    # Notify DPA (within 72 hours for GDPR)
    try:
        from app.notify import push as notify_push
        import asyncio
        await notify_push(
            db, type="breach_dpa",
            title=f"DPA Notification: {breach.title}",
            message=f"Breach detected at {breach.detected_at.isoformat()}. "
                    f"Severity: {breach.severity}. Affected: {breach.affected_users} users. "
                    f"Data categories: {breach.data_categories}",
        )
        breach.notified_dpa = True
        breach.dpa_notified_at = datetime.now(timezone.utc)
        results["dpa_notified"] = True
    except Exception as e:
        log.error("Failed to notify DPA: %s", e)

    # Notify affected users
    try:
        await notify_push(
            db, type="breach_affected",
            title=f"Security Incident: {breach.title}",
            message=f"We are writing to inform you of a security incident. "
                    f"Detected: {breach.detected_at.isoformat()}",
        )
        breach.notified_affected = True
        breach.affected_notified_at = datetime.now(timezone.utc)
        results["affected_notified"] = True
    except Exception as e:
        log.error("Failed to notify affected users: %s", e)

    await db.commit()
    return results
