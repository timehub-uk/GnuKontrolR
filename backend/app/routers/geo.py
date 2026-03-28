"""
Geo / country data management.

Admin endpoints:
  POST /api/geo/sync-countries   — populate DB with all countries + fetch flags + CIDRs
  POST /api/geo/refresh-cidrs    — refresh CIDR lists for all (or one) country

Public (authenticated) endpoints:
  GET  /api/geo/countries        — list all countries with flag URLs
  GET  /api/geo/flag/{cc}        — serve flag blob (SVG)
  GET  /api/geo/cidrs/{cc}       — return CIDR list for a country
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models.country_data import CountryData
from app.models.user import User
from app.routers.ip_rules import COUNTRIES

log = logging.getLogger("webpanel")
router = APIRouter(prefix="/api/geo", tags=["geo"])

_CIDR_TTL = timedelta(hours=24)


async def _fetch_flag(cc: str, client: httpx.AsyncClient) -> Optional[bytes]:
    """Fetch flag SVG from flagcdn.com (4×3 aspect ratio SVG)."""
    url = f"https://flagcdn.com/{cc.lower()}.svg"
    try:
        resp = await client.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.content
    except Exception as exc:
        log.debug("Flag fetch failed for %s: %s", cc, exc)
    return None


async def _fetch_cidrs(cc: str, client: httpx.AsyncClient) -> Optional[str]:
    """Fetch aggregated CIDR list from ipdeny.com, return as newline-separated text."""
    url = f"https://www.ipdeny.com/ipblocks/data/aggregated/{cc.lower()}-aggregated.zone"
    try:
        resp = await client.get(url, timeout=30)
        if resp.status_code == 200:
            return resp.text.strip()
    except Exception as exc:
        log.debug("CIDR fetch failed for %s: %s", cc, exc)
    return None


# ── Admin: sync all countries ─────────────────────────────────────────────────

@router.post("/sync-countries", dependencies=[Depends(require_admin)])
async def sync_countries(
    refresh_cidrs: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """Populate/update all countries in DB with flags and (optionally) CIDRs.

    This makes ~250 HTTP requests concurrently with a semaphore-limited pool.
    Expected runtime: ~30–60 s depending on network latency.
    """
    sem = asyncio.Semaphore(20)  # max 20 concurrent requests

    async def fetch_one(entry: dict, client: httpx.AsyncClient) -> dict:
        cc = entry["code"]
        async with sem:
            flag  = await _fetch_flag(cc, client)
            cidrs = await _fetch_cidrs(cc, client) if refresh_cidrs else None
        return {"cc": cc, "name": entry["name"], "flag": flag, "cidrs": cidrs}

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[fetch_one(e, client) for e in COUNTRIES])

    updated = 0
    for r in results:
        existing = (await db.execute(
            select(CountryData).where(CountryData.country_code == r["cc"])
        )).scalar_one_or_none()

        if existing:
            if r["flag"]:
                existing.flag_svg = r["flag"]
            if r["cidrs"] is not None:
                existing.cidrs    = r["cidrs"]
                existing.cidrs_at = datetime.utcnow()
            existing.updated_at = datetime.utcnow()
        else:
            db.add(CountryData(
                country_code = r["cc"],
                country_name = r["name"],
                flag_svg     = r["flag"],
                cidrs        = r["cidrs"],
                cidrs_at     = datetime.utcnow() if r["cidrs"] else None,
            ))
        updated += 1

    await db.commit()
    return {"updated": updated, "total": len(COUNTRIES)}


# ── Admin: refresh CIDRs for one or all countries ────────────────────────────

@router.post("/refresh-cidrs", dependencies=[Depends(require_admin)])
async def refresh_cidrs(
    country_code: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Refresh CIDR lists from ipdeny.com.  Pass country_code to limit to one."""
    if country_code:
        codes = [country_code.upper()]
    else:
        result = await db.execute(select(CountryData))
        codes = [c.country_code for c in result.scalars().all()]

    sem = asyncio.Semaphore(10)

    async def refresh_one(cc: str, client: httpx.AsyncClient):
        async with sem:
            cidrs = await _fetch_cidrs(cc, client)
        if cidrs is None:
            return
        row = (await db.execute(
            select(CountryData).where(CountryData.country_code == cc)
        )).scalar_one_or_none()
        if row:
            row.cidrs    = cidrs
            row.cidrs_at = datetime.utcnow()
        else:
            from app.routers.ip_rules import _COUNTRY_MAP
            db.add(CountryData(
                country_code = cc,
                country_name = _COUNTRY_MAP.get(cc, cc),
                cidrs        = cidrs,
                cidrs_at     = datetime.utcnow(),
            ))

    async with httpx.AsyncClient() as client:
        await asyncio.gather(*[refresh_one(cc, client) for cc in codes])

    await db.commit()
    return {"refreshed": len(codes)}


# ── Authenticated: list countries with flag URLs ──────────────────────────────

@router.get("/countries")
async def list_countries(
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all countries with flag URL and whether CIDRs are cached."""
    result = await db.execute(select(CountryData).order_by(CountryData.country_name))
    rows   = result.scalars().all()

    if not rows:
        # DB not yet synced — return static list without flags
        return [{"code": c["code"], "name": c["name"], "flag_url": None, "has_cidrs": False}
                for c in COUNTRIES]

    return [
        {
            "code":      r.country_code,
            "name":      r.country_name,
            "flag_url":  f"/api/geo/flag/{r.country_code.lower()}",
            "has_cidrs": bool(r.cidrs),
        }
        for r in rows
    ]


# ── Authenticated: serve flag blob ────────────────────────────────────────────

@router.get("/flag/{cc}")
async def get_flag(
    cc: str,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cc = cc.upper().split(".")[0]  # strip any extension
    result = await db.execute(
        select(CountryData).where(CountryData.country_code == cc)
    )
    row = result.scalar_one_or_none()
    if not row or not row.flag_svg:
        raise HTTPException(404, "Flag not found — run /api/geo/sync-countries first")
    return Response(
        content=row.flag_svg,
        media_type=row.flag_mime or "image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


# ── Authenticated: get CIDRs for a country ────────────────────────────────────

@router.get("/cidrs/{cc}")
async def get_cidrs(
    cc: str,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cc = cc.upper()
    result = await db.execute(
        select(CountryData).where(CountryData.country_code == cc)
    )
    row = result.scalar_one_or_none()
    if not row or not row.cidrs:
        return {"country_code": cc, "cidrs": [], "cached_at": None}
    return {
        "country_code": cc,
        "cidrs":        [c for c in row.cidrs.splitlines() if c.strip()],
        "cached_at":    row.cidrs_at,
    }
