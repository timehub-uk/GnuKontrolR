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
from app.dns_helper import (
    rotate_dkim_key, sync_all_domains, sync_all_ns,
    get_external_ip, get_external_ipv6, get_internal_ip,
    update_effective_ip, sync_panel_ns_zone,
)
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
_last_ip_check: dict = {}
_last_known_ipv4: str = ""
_last_known_ipv6: str = ""
_last_known_internal: str = ""

# Keep the old name so main.py still works without changes
ns_ip_sync_loop = None   # replaced below by ip_check_loop; updated in main.py


def _env_path() -> str:
    import os as _os
    # .env is two directories above this file: backend/app/routers/ → project root
    return _os.path.normpath(
        _os.path.join(_os.path.dirname(__file__), "..", "..", "..", ".env")
    )


def _update_env_ip(ipv4: str, ipv6: str = "") -> None:
    """Write SERVER_IP (and optionally SERVER_IPV6) back to .env so restarts keep the right value."""
    import re as _re
    path = _env_path()
    try:
        with open(path) as f:
            content = f.read()
        new = _re.sub(r"^SERVER_IP=.*$", f"SERVER_IP={ipv4}", content, flags=_re.MULTILINE)
        if new == content and f"SERVER_IP={ipv4}" not in content:
            new += f"\nSERVER_IP={ipv4}\n"
        # Upsert SERVER_IPV6 line
        if ipv6:
            if _re.search(r"^SERVER_IPV6=", new, flags=_re.MULTILINE):
                new = _re.sub(r"^SERVER_IPV6=.*$", f"SERVER_IPV6={ipv6}", new, flags=_re.MULTILINE)
            else:
                new += f"SERVER_IPV6={ipv6}\n"
        with open(path, "w") as f:
            f.write(new)
    except Exception as exc:
        log.warning("Could not update SERVER_IP in .env: %s", exc)


async def ip_check_loop(interval: int = 3600) -> None:
    """Every *interval* seconds:
      - Detect external IPv4, external IPv6, and internal IP.
      - On any change: update the effective IP, rewrite .env, and run a full DNS sync
        (all A/AAAA records + NS records) so PowerDNS immediately reflects the new address.
    """
    global _last_known_ipv4, _last_known_ipv6, _last_known_internal

    while True:
        try:
            # Detect all three IPs concurrently
            ipv4, ipv6, internal = await asyncio.gather(
                get_external_ip(),
                get_external_ipv6(),
                get_internal_ip(),
                return_exceptions=True,
            )
            ipv4     = ipv4     if isinstance(ipv4, str)     else ""
            ipv6     = ipv6     if isinstance(ipv6, str)     else ""
            internal = internal if isinstance(internal, str) else ""

            changed = (
                (ipv4     and ipv4     != _last_known_ipv4)     or
                (ipv6     and ipv6     != _last_known_ipv6)     or
                (internal and internal != _last_known_internal)
            )

            if changed:
                log.info(
                    "IP change detected — ext4: %s→%s  ext6: %s→%s  internal: %s→%s",
                    _last_known_ipv4, ipv4,
                    _last_known_ipv6, ipv6,
                    _last_known_internal, internal,
                )
                update_effective_ip(ipv4, internal)
                _update_env_ip(ipv4, ipv6)

                async with AsyncSessionLocal() as db:
                    result = await db.execute(select(Domain))
                    domains = result.scalars().all()

                # Full DNS sync: all A records + NS glue (with AAAA if IPv6 available)
                await sync_panel_ns_zone(ipv4, ipv6=ipv6)
                ns_summary  = await sync_all_ns(domains, ipv4, ipv6=ipv6)
                dns_summary = await sync_all_domains(domains, server_ip=ipv4)

                _last_known_ipv4     = ipv4
                _last_known_ipv6     = ipv6
                _last_known_internal = internal

                _last_ip_check.clear()
                _last_ip_check.update({
                    "external_ipv4": ipv4,
                    "external_ipv6": ipv6 or None,
                    "internal_ip":   internal or None,
                    "changed": True,
                    "ns_updated":  len(ns_summary.get("updated", [])),
                    "dns_provisioned": len(dns_summary.get("provisioned", [])),
                    "errors": ns_summary.get("errors", []) + dns_summary.get("errors", []),
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                })
                log.info(
                    "IP sync complete — ext4=%s ext6=%s internal=%s ns_updated=%d dns_provisioned=%d",
                    ipv4, ipv6, internal,
                    len(ns_summary.get("updated", [])),
                    len(dns_summary.get("provisioned", [])),
                )
            else:
                _last_ip_check.update({
                    "external_ipv4": ipv4,
                    "external_ipv6": ipv6 or None,
                    "internal_ip":   internal or None,
                    "changed": False,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                })
                log.debug("IP check: all IPs unchanged (ext4=%s ext6=%s internal=%s)", ipv4, ipv6, internal)

        except Exception as exc:
            log.error("IP check loop error: %s", exc)

        await asyncio.sleep(interval)


@router.get("/ip-status", dependencies=[Depends(require_superadmin)])
async def get_ip_status():
    """Return the most recent IP check result (superadmin only)."""
    if _last_ip_check:
        return _last_ip_check
    # Nothing cached yet — do a live probe
    ipv4, ipv6, internal = await asyncio.gather(
        get_external_ip(), get_external_ipv6(), get_internal_ip(),
        return_exceptions=True,
    )
    return {
        "external_ipv4": ipv4 if isinstance(ipv4, str) else None,
        "external_ipv6": ipv6 if isinstance(ipv6, str) and ipv6 else None,
        "internal_ip":   internal if isinstance(internal, str) else None,
        "changed": None,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "note": "live probe — hourly loop has not run yet",
    }


@router.post("/ip-sync", dependencies=[Depends(require_superadmin)])
async def trigger_ip_sync():
    """Manually trigger a full IP detection + DNS sync (superadmin only)."""
    global _last_known_ipv4, _last_known_ipv6, _last_known_internal
    ipv4, ipv6, internal = await asyncio.gather(
        get_external_ip(), get_external_ipv6(), get_internal_ip(),
        return_exceptions=True,
    )
    ipv4     = ipv4     if isinstance(ipv4, str)     else ""
    ipv6     = ipv6     if isinstance(ipv6, str)     else ""
    internal = internal if isinstance(internal, str) else ""

    update_effective_ip(ipv4, internal)
    _update_env_ip(ipv4, ipv6)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Domain))
        domains = result.scalars().all()

    await sync_panel_ns_zone(ipv4, ipv6=ipv6)
    ns_summary  = await sync_all_ns(domains, ipv4, ipv6=ipv6)
    dns_summary = await sync_all_domains(domains, server_ip=ipv4)

    _last_known_ipv4     = ipv4
    _last_known_ipv6     = ipv6
    _last_known_internal = internal

    result_data = {
        "external_ipv4": ipv4,
        "external_ipv6": ipv6 or None,
        "internal_ip":   internal or None,
        "ns_updated":    len(ns_summary.get("updated", [])),
        "dns_provisioned": len(dns_summary.get("provisioned", [])),
        "errors": ns_summary.get("errors", []) + dns_summary.get("errors", []),
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }
    _last_ip_check.clear()
    _last_ip_check.update({**result_data, "changed": True})
    return result_data


# Keep backward-compat alias for old /ns-sync calls
@router.get("/ns-sync", dependencies=[Depends(require_superadmin)])
async def get_ns_sync_status():
    return _last_ip_check or {"message": "No IP sync has run yet"}


@router.post("/ns-sync", dependencies=[Depends(require_superadmin)])
async def trigger_ns_sync():
    return await trigger_ip_sync()


@router.get("/test", dependencies=[Depends(require_superadmin)])
async def test_dns_connectivity():
    """Live diagnostic: probe external IPs and verify PowerDNS API + zone DB (superadmin only).

    Returns:
      - detected external IPv4 / IPv6 / internal IP
      - PowerDNS API reachability
      - count of zones in PowerDNS vs domains in the panel DB
      - any mismatches (domains in DB missing from PowerDNS)
    """
    import httpx as _httpx
    from app.database import AsyncSessionLocal as _ASL
    from app.dns_helper import PDNS_BASE as _BASE, _HEADERS as _HDR

    # ── IP detection ──────────────────────────────────────────────────────────
    ipv4, ipv6, internal = await asyncio.gather(
        get_external_ip(), get_external_ipv6(), get_internal_ip(),
        return_exceptions=True,
    )
    ipv4     = ipv4     if isinstance(ipv4, str)     else f"ERROR: {ipv4}"
    ipv6     = ipv6     if isinstance(ipv6, str)     else None
    internal = internal if isinstance(internal, str) else f"ERROR: {internal}"

    # ── PowerDNS API ─────────────────────────────────────────────────────────
    pdns_ok     = False
    pdns_zones  = []
    pdns_error  = None
    try:
        async with _httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{_BASE}/zones", headers=_HDR)
            r.raise_for_status()
            pdns_zones = [z["id"].rstrip(".") for z in r.json()]
            pdns_ok = True
    except Exception as exc:
        pdns_error = str(exc)

    # ── Domain DB ────────────────────────────────────────────────────────────
    db_domains: list[str] = []
    try:
        async with _ASL() as db:
            result = await db.execute(select(Domain))
            db_domains = [d.name for d in result.scalars().all()]
    except Exception as exc:
        db_domains = [f"DB ERROR: {exc}"]

    pdns_set = set(pdns_zones)
    db_set   = set(db_domains)
    missing_from_pdns  = sorted(db_set  - pdns_set)
    orphan_in_pdns     = sorted(pdns_set - db_set)

    return {
        "ips": {
            "external_ipv4": ipv4,
            "external_ipv6": ipv6 or None,
            "internal":      internal,
        },
        "powerdns": {
            "reachable":   pdns_ok,
            "error":       pdns_error,
            "zone_count":  len(pdns_zones),
        },
        "database": {
            "domain_count": len(db_domains),
        },
        "mismatches": {
            "missing_from_powerdns": missing_from_pdns,
            "orphan_in_powerdns":    orphan_in_pdns,
        },
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


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
