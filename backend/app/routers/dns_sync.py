"""DNS synchronisation router.

POST /api/dns/sync  — superadmin: immediately reconcile PowerDNS against DB.
GET  /api/dns/sync  — superadmin: return last sync result.

The background sync task (every 180 s) is registered in main.py lifespan.
"""
import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_superadmin
from app.database import AsyncSessionLocal, get_db
from app.dns_helper import rotate_dkim_key, sync_all_domains, sync_all_ns, get_external_ip, sync_panel_ns_zone
from app.models.domain import Domain

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dns", tags=["dns-sync"])

# Shared last-result cache (in-process; good enough for a single-instance panel)
_last_sync: dict = {}


async def run_dns_sync() -> dict:
    """Pull all domains from DB and reconcile with PowerDNS."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Domain))
        domains = result.scalars().all()

    summary = await sync_all_domains(domains)
    summary["synced_at"] = datetime.now(timezone.utc).isoformat()
    summary["domain_count"] = len(domains)
    _last_sync.clear()
    _last_sync.update(summary)
    return summary


async def dns_sync_loop(interval: int = 180) -> None:
    """Background task: sync DNS every *interval* seconds."""
    while True:
        try:
            result = await run_dns_sync()
            log.info(
                "DNS sync: provisioned=%d deleted=%d errors=%d",
                len(result.get("provisioned", [])),
                len(result.get("deleted", [])),
                len(result.get("errors", [])),
            )
        except Exception as exc:
            log.error("DNS sync loop error: %s", exc)
        await asyncio.sleep(interval)


_last_ns_sync: dict = {}
_last_known_ip: str = ""


async def ns_ip_sync_loop(interval: int = 3600) -> None:
    """Every *interval* seconds, re-detect external IP and update NS1/NS2/NS3 records."""
    global _last_known_ip
    while True:
        try:
            ip = await get_external_ip()
            if ip and ip != _last_known_ip:
                log.info("External IP changed: %s → %s; refreshing NS records", _last_known_ip, ip)
                async with AsyncSessionLocal() as db:
                    result = await db.execute(select(Domain))
                    domains = result.scalars().all()
                await sync_panel_ns_zone(ip)
                summary = await sync_all_ns(domains, ip)
                summary["detected_ip"] = ip
                summary["synced_at"] = datetime.now(timezone.utc).isoformat()
                _last_known_ip = ip
                _last_ns_sync.clear()
                _last_ns_sync.update(summary)
                log.info("NS sync: updated=%d errors=%d ip=%s",
                         len(summary.get("updated", [])), len(summary.get("errors", [])), ip)
            else:
                log.debug("NS sync: IP unchanged (%s) — no update needed", ip)
        except Exception as exc:
            log.error("NS IP sync loop error: %s", exc)
        await asyncio.sleep(interval)


@router.get("/ns-sync", dependencies=[Depends(require_superadmin)])
async def get_ns_sync_status():
    """Return the result of the most recent NS record sync (superadmin only)."""
    return _last_ns_sync or {"message": "No NS sync has run yet", "last_known_ip": _last_known_ip}


@router.post("/ns-sync", dependencies=[Depends(require_superadmin)])
async def trigger_ns_sync():
    """Manually trigger NS record sync for all domains (superadmin only)."""
    global _last_known_ip
    ip = await get_external_ip()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Domain))
        domains = result.scalars().all()
    summary = await sync_all_ns(domains, ip)
    summary["detected_ip"] = ip
    summary["synced_at"] = datetime.now(timezone.utc).isoformat()
    _last_known_ip = ip
    _last_ns_sync.clear()
    _last_ns_sync.update(summary)
    return summary


@router.post("/sync", dependencies=[Depends(require_superadmin)])
async def trigger_dns_sync():
    """Manually trigger a full DNS sync (superadmin only)."""
    return await run_dns_sync()


@router.get("/sync", dependencies=[Depends(require_superadmin)])
async def get_last_sync_result():
    """Return the result of the most recent DNS sync (superadmin only)."""
    return _last_sync or {"message": "No sync has run yet"}


@router.post("/dkim/{domain_name}/rotate", dependencies=[Depends(require_superadmin)])
async def rotate_domain_dkim(domain_name: str, db: AsyncSession = Depends(get_db)):
    """Admin only: regenerate the DKIM key for a domain and update PowerDNS.

    DKIM keys are immutable by default.  This endpoint is the only way to
    rotate them.  Allow DNS TTL (3600 s) to propagate before rotating in
    production.
    """
    result = await db.execute(select(Domain).where(Domain.name == domain_name))
    domain = result.scalar_one_or_none()
    if not domain:
        raise HTTPException(404, "Domain not found")
    pub_b64 = await rotate_dkim_key(domain)
    return {
        "domain": domain_name,
        "selector": "mail",
        "dns_record": f"mail._domainkey.{domain_name}",
        "public_key": pub_b64,
        "note": "Allow 3600 s (DNS TTL) for propagation before the old key expires.",
    }
