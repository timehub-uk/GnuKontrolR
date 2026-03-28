"""
Email SBL / DNSBL Security — Spamhaus and multi-blacklist checking.

Protects domain email services from spam abuse by:
  1. Checking sender IPs against configurable DNSBL lists.
  2. Maintaining an audit log of rejected/flagged senders.
  3. Providing per-domain email security policy (SPF/DKIM/DMARC enforcement).
  4. Pushing Postfix restriction rules into the container config.

Admin-only configuration endpoints; users can view their domain's events.
"""
import asyncio
import ipaddress
import socket
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin, get_current_user
from app.database import get_db
from app.models.email_security import DnsblList, DnsblCheckResult, EmailSecurityPolicy, SblEvent
from app.models.user import User, Role
from app.models.domain import Domain

router = APIRouter(prefix="/api/email-security", tags=["email-security"])

# Default DNSBL lists (pre-seeded on first use)
_DEFAULT_DNSBLS = [
    ("Spamhaus ZEN",      "zen.spamhaus.org",       "Spamhaus combined SBL+XBL+PBL list"),
    ("Spamhaus SBL",      "sbl.spamhaus.org",       "Spamhaus spam source blocklist"),
    ("SpamCop",           "bl.spamcop.net",          "SpamCop reporting network"),
    ("Barracuda BRBL",    "b.barracudacentral.org",  "Barracuda reputation blocklist"),
    ("SORBS SPAM",        "spam.sorbs.net",          "SORBS spam sources"),
    ("SORBS HTTP",        "http.dnsbl.sorbs.net",    "Open HTTP proxies"),
    ("UCEProtect L1",     "dnsbl-1.uceprotect.net",  "UCEProtect level 1 — individual IPs"),
    ("Mailspike BL",      "bl.mailspike.net",        "Mailspike combined blacklist"),
    ("SURBL multi",       "multi.surbl.org",         "URL/domain reputation (multi list)"),
]


async def _seed_default_lists(db: AsyncSession) -> None:
    count = (await db.execute(select(DnsblList))).scalars().first()
    if count:
        return
    for name, zone, desc in _DEFAULT_DNSBLS:
        db.add(DnsblList(name=name, zone=zone, description=desc, enabled=True))
    await db.commit()


# ── GET /api/email-security/dnsbl ─────────────────────────────────────────────

@router.get("/dnsbl")
async def list_dnsbl(
    _=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    await _seed_default_lists(db)
    rows = (await db.execute(select(DnsblList).order_by(DnsblList.name))).scalars().all()
    return {"lists": [_dnsbl_dict(r) for r in rows]}


def _dnsbl_dict(r: DnsblList) -> dict:
    return {
        "id": r.id, "name": r.name, "zone": r.zone,
        "description": r.description, "enabled": r.enabled, "weight": r.weight,
    }


# ── POST /api/email-security/dnsbl ────────────────────────────────────────────

class DnsblCreate(BaseModel):
    name: str
    zone: str
    description: str = ""
    weight: float = 1.0


@router.post("/dnsbl")
async def add_dnsbl(
    body: DnsblCreate,
    _=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    existing = (await db.execute(select(DnsblList).where(DnsblList.zone == body.zone))).scalar_one_or_none()
    if existing:
        raise HTTPException(409, f"DNSBL zone {body.zone!r} already configured")
    entry = DnsblList(name=body.name, zone=body.zone, description=body.description, weight=body.weight)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return _dnsbl_dict(entry)


# ── PATCH /api/email-security/dnsbl/{id} ──────────────────────────────────────

class DnsblUpdate(BaseModel):
    enabled: bool | None = None
    weight: float | None = None


@router.patch("/dnsbl/{dnsbl_id}")
async def update_dnsbl(
    dnsbl_id: int,
    body: DnsblUpdate,
    _=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    entry = await db.get(DnsblList, dnsbl_id)
    if not entry:
        raise HTTPException(404, "Not found")
    if body.enabled is not None:
        entry.enabled = body.enabled
    if body.weight is not None:
        entry.weight = body.weight
    await db.commit()
    return _dnsbl_dict(entry)


# ── DELETE /api/email-security/dnsbl/{id} ─────────────────────────────────────

@router.delete("/dnsbl/{dnsbl_id}")
async def delete_dnsbl(
    dnsbl_id: int,
    _=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    entry = await db.get(DnsblList, dnsbl_id)
    if not entry:
        raise HTTPException(404, "Not found")
    await db.delete(entry)
    await db.commit()
    return {"ok": True}


# ── POST /api/email-security/check ────────────────────────────────────────────

class CheckRequest(BaseModel):
    ip: str
    use_cache: bool = True


async def _dns_lookup(reversed_ip: str, zone: str) -> str | None:
    """Perform A-record lookup for <reversed_ip>.<zone>. Returns return code or None."""
    query = f"{reversed_ip}.{zone}"
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, socket.gethostbyname, query)
        return result
    except socket.gaierror:
        return None  # not listed


def _reverse_ip(ip: str) -> str:
    """Reverse IPv4 octets for DNSBL query format."""
    try:
        addr = ipaddress.ip_address(ip)
        if addr.version == 4:
            return ".".join(reversed(ip.split(".")))
        # IPv6: nibble-reversed
        exploded = addr.exploded.replace(":", "")
        return ".".join(reversed(list(exploded)))
    except ValueError:
        raise HTTPException(400, f"Invalid IP address: {ip!r}")


@router.post("/check")
async def check_ip(
    body: CheckRequest,
    _=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Check an IP against all enabled DNSBL lists. Returns per-list results."""
    reversed_ip = _reverse_ip(body.ip)
    lists = (await db.execute(
        select(DnsblList).where(DnsblList.enabled == True)
    )).scalars().all()

    results = []
    tasks = []

    async def _check_one(dnsbl: DnsblList):
        # Try cache first
        if body.use_cache:
            cached = (await db.execute(
                select(DnsblCheckResult).where(
                    DnsblCheckResult.ip == body.ip,
                    DnsblCheckResult.dnsbl_zone == dnsbl.zone,
                    DnsblCheckResult.expires_at > datetime.utcnow(),
                )
            )).scalar_one_or_none()
            if cached:
                return {"zone": dnsbl.zone, "name": dnsbl.name, "listed": cached.listed,
                        "return_code": cached.return_code, "cached": True}

        return_code = await _dns_lookup(reversed_ip, dnsbl.zone)
        listed = return_code is not None

        # Cache for 1 hour
        existing = (await db.execute(
            select(DnsblCheckResult).where(
                DnsblCheckResult.ip == body.ip,
                DnsblCheckResult.dnsbl_zone == dnsbl.zone,
            )
        )).scalar_one_or_none()
        if existing:
            existing.listed = listed
            existing.return_code = return_code
            existing.checked_at = datetime.utcnow()
            existing.expires_at = datetime.utcnow() + timedelta(hours=1)
        else:
            db.add(DnsblCheckResult(
                ip=body.ip,
                dnsbl_zone=dnsbl.zone,
                listed=listed,
                return_code=return_code,
                checked_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(hours=1),
            ))
        await db.commit()

        return {"zone": dnsbl.zone, "name": dnsbl.name, "listed": listed,
                "return_code": return_code, "cached": False}

    # Run all checks concurrently (capped at 10 simultaneous DNS queries)
    sem = asyncio.Semaphore(10)
    async def _guarded(dnsbl):
        async with sem:
            return await _check_one(dnsbl)

    results = await asyncio.gather(*[_guarded(d) for d in lists], return_exceptions=True)
    clean_results = [r for r in results if isinstance(r, dict)]
    blacklisted = [r for r in clean_results if r.get("listed")]

    return {
        "ip": body.ip,
        "listed_on": len(blacklisted),
        "total_checked": len(clean_results),
        "blacklisted": blacklisted,
        "results": clean_results,
    }


# ── GET /api/email-security/policy/{domain} ───────────────────────────────────

@router.get("/policy/{domain}")
async def get_policy(
    domain: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _assert_domain_access(domain, user, db)
    policy = await _get_or_create_policy(domain, db)
    return _policy_dict(policy)


async def _get_or_create_policy(domain: str, db: AsyncSession) -> EmailSecurityPolicy:
    policy = (await db.execute(
        select(EmailSecurityPolicy).where(EmailSecurityPolicy.domain == domain)
    )).scalar_one_or_none()
    if not policy:
        policy = EmailSecurityPolicy(domain=domain)
        db.add(policy)
        await db.commit()
        await db.refresh(policy)
    return policy


def _policy_dict(p: EmailSecurityPolicy) -> dict:
    return {
        "domain": p.domain, "dnsbl_check": p.dnsbl_check,
        "dnsbl_action": p.dnsbl_action, "spf_check": p.spf_check,
        "dkim_check": p.dkim_check, "dmarc_check": p.dmarc_check,
        "greylist": p.greylist, "rate_limit_per_hour": p.rate_limit_per_hour,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


# ── PATCH /api/email-security/policy/{domain} ─────────────────────────────────

class PolicyUpdate(BaseModel):
    dnsbl_check: bool | None = None
    dnsbl_action: str | None = None    # reject | defer | flag
    spf_check: bool | None = None
    dkim_check: bool | None = None
    dmarc_check: bool | None = None
    greylist: bool | None = None
    rate_limit_per_hour: int | None = None


@router.patch("/policy/{domain}")
async def update_policy(
    domain: str,
    body: PolicyUpdate,
    user=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    policy = await _get_or_create_policy(domain, db)
    if body.dnsbl_check is not None:       policy.dnsbl_check = body.dnsbl_check
    if body.dnsbl_action is not None:
        if body.dnsbl_action not in ("reject", "defer", "flag"):
            raise HTTPException(400, "dnsbl_action must be reject | defer | flag")
        policy.dnsbl_action = body.dnsbl_action
    if body.spf_check is not None:         policy.spf_check = body.spf_check
    if body.dkim_check is not None:        policy.dkim_check = body.dkim_check
    if body.dmarc_check is not None:       policy.dmarc_check = body.dmarc_check
    if body.greylist is not None:          policy.greylist = body.greylist
    if body.rate_limit_per_hour is not None: policy.rate_limit_per_hour = body.rate_limit_per_hour
    policy.updated_at = datetime.utcnow()
    await db.commit()
    return _policy_dict(policy)


# ── GET /api/email-security/events ────────────────────────────────────────────

@router.get("/events")
async def list_sbl_events(
    domain: str = "",
    limit: int = 100,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Admins see all events; regular users see only their own domains."""
    stmt = select(SblEvent).order_by(SblEvent.occurred_at.desc()).limit(limit)
    if user.role not in (Role.superadmin, Role.admin):
        # Filter to owned domains only
        owned = (await db.execute(
            select(Domain.name).where(Domain.owner_id == user.id)
        )).scalars().all()
        stmt = stmt.where(SblEvent.domain.in_(owned))
    elif domain:
        stmt = stmt.where(SblEvent.domain == domain)
    rows = (await db.execute(stmt)).scalars().all()
    return {"events": [
        {
            "id": r.id, "ip": r.ip, "sender": r.sender,
            "recipient": r.recipient, "domain": r.domain,
            "action": r.action, "dnsbl_zone": r.dnsbl_zone,
            "score": r.score,
            "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
        } for r in rows
    ]}


# ── POST /api/email-security/events (internal — called by container postfix hook)

class SblEventIn(BaseModel):
    ip: str
    sender: str = ""
    recipient: str = ""
    domain: str = ""
    action: str
    dnsbl_zone: str = ""
    score: float = 0.0


@router.post("/events")
async def record_sbl_event(
    body: SblEventIn,
    db: AsyncSession = Depends(get_db),
    # No auth required — called internally from containers via trusted network
    # Access is restricted to Docker bridge only via Traefik middleware
):
    event = SblEvent(
        ip=body.ip, sender=body.sender, recipient=body.recipient,
        domain=body.domain, action=body.action,
        dnsbl_zone=body.dnsbl_zone, score=body.score,
    )
    db.add(event)
    await db.commit()
    return {"ok": True}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _assert_domain_access(domain: str, user: User, db: AsyncSession) -> None:
    if user.role in (Role.superadmin, Role.admin):
        return
    result = await db.execute(
        select(Domain).where(Domain.name == domain, Domain.owner_id == user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(403, "Access denied: domain not owned by you")
