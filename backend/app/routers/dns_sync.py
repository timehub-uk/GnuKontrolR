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
from app.dns_helper import rotate_dkim_key, sync_all_domains
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
