"""
CVE threat feed — fetches recent CVEs from cve.org NVD API.

Uses the CVE 5.0 schema format from CVEProject/cve-schema.
Caches results in DB (app_cache) for 6 hours to avoid hammering the API.
"""
import json
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.http_client import panel_client

router = APIRouter(prefix="/api/cve", tags=["cve"])

_CVE_API_BASE   = "https://cveawg.mitre.org/api"  # CVE.org official API
_NVD_API_BASE   = "https://services.nvd.nist.gov/rest/json/cves/2.0"
_CACHE_TTL_HOURS = 6
_CACHE_KEY_PREFIX = "cve_feed:"


async def _get_cached(db: AsyncSession, key: str) -> dict | None:
    from app.models.app_cache import AppCacheEntry
    row = (await db.execute(
        select(AppCacheEntry).where(AppCacheEntry.app_id == key)
    )).scalar_one_or_none()
    if not row:
        return None
    # Check TTL: use cached_at + 6h
    if row.cached_at and (datetime.utcnow() - row.cached_at).total_seconds() < _CACHE_TTL_HOURS * 3600:
        try:
            return json.loads(row.archive_path)  # store JSON in archive_path field
        except Exception:
            return None
    return None


async def _set_cached(db: AsyncSession, key: str, data: dict) -> None:
    from app.models.app_cache import AppCacheEntry
    row = (await db.execute(
        select(AppCacheEntry).where(AppCacheEntry.app_id == key)
    )).scalar_one_or_none()
    payload = json.dumps(data)
    if row:
        row.archive_path = payload
        row.cached_at = datetime.utcnow()
    else:
        row = AppCacheEntry(
            app_id=key,
            app_name=key,
            version="cache",
            archive_path=payload,
            cached_at=datetime.utcnow(),
        )
        db.add(row)
    await db.commit()


# ── GET /api/cve/recent ───────────────────────────────────────────────────────

@router.get("/recent")
async def recent_cves(
    keyword: str = "",
    severity: str = "",   # CRITICAL | HIGH | MEDIUM | LOW
    limit: int = 20,
    _=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return recent CVEs from the NVD API.
    Results are cached 6 hours. Supports keyword and severity filtering.
    """
    cache_key = f"{_CACHE_KEY_PREFIX}recent:{keyword}:{severity}"
    cached = await _get_cached(db, cache_key)
    if cached:
        items = cached.get("items", [])
        return {"items": items[:limit], "cached": True, "total": len(items)}

    params: dict = {
        "resultsPerPage": 50,
        "startIndex": 0,
    }
    if keyword:
        params["keywordSearch"] = keyword
    if severity and severity.upper() in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        params["cvssV3Severity"] = severity.upper()

    try:
        async with panel_client(timeout=15) as client:
            r = await client.get(_NVD_API_BASE, params=params)
            r.raise_for_status()
            data = r.json()
    except httpx.TimeoutException:
        raise HTTPException(504, "NVD API timed out")
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"NVD API error: {e.response.status_code}")
    except Exception as exc:
        raise HTTPException(502, f"CVE feed unavailable: {exc}")

    items = []
    for vuln in data.get("vulnerabilities", []):
        cve = vuln.get("cve", {})
        cve_id   = cve.get("id", "")
        published = cve.get("published", "")
        modified  = cve.get("lastModified", "")

        # Extract description (English preferred)
        descs = cve.get("descriptions", [])
        desc  = next((d["value"] for d in descs if d.get("lang") == "en"), "")

        # CVSS v3 base score + severity
        metrics = cve.get("metrics", {})
        cvss3   = metrics.get("cvssMetricV31", metrics.get("cvssMetricV30", []))
        score   = None
        sev     = None
        if cvss3:
            cvss_data = cvss3[0].get("cvssData", {})
            score = cvss_data.get("baseScore")
            sev   = cvss_data.get("baseSeverity")

        # References
        refs = [r["url"] for r in cve.get("references", [])[:3]]

        # Affected products (CPE)
        configs = cve.get("configurations", [])
        products = []
        for cfg in configs[:1]:
            for node in cfg.get("nodes", [])[:1]:
                for cpe in node.get("cpeMatch", [])[:3]:
                    parts = cpe.get("criteria", "").split(":")
                    products.append(parts[4] if len(parts) > 4 else "")

        items.append({
            "id":        cve_id,
            "published": published,
            "modified":  modified,
            "description": desc[:300],
            "score":     score,
            "severity":  sev,
            "references": refs,
            "products":  [p for p in products if p],
            "nvd_url":   f"https://nvd.nist.gov/vuln/detail/{cve_id}",
            "cve_url":   f"https://www.cve.org/CVERecord?id={cve_id}",
        })

    await _set_cached(db, cache_key, {"items": items})
    return {"items": items[:limit], "cached": False, "total": len(items)}


# ── GET /api/cve/{cve_id} ─────────────────────────────────────────────────────

@router.get("/{cve_id}")
async def get_cve(
    cve_id: str,
    _=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch a single CVE record from CVE.org official API."""
    if not cve_id.upper().startswith("CVE-"):
        raise HTTPException(400, "CVE ID must start with CVE-")
    cve_id = cve_id.upper()
    cache_key = f"{_CACHE_KEY_PREFIX}detail:{cve_id}"
    cached = await _get_cached(db, cache_key)
    if cached:
        return {**cached, "cached": True}

    try:
        async with panel_client(timeout=15) as client:
            r = await client.get(f"{_CVE_API_BASE}/cve/{cve_id}")
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(404, f"{cve_id} not found")
        raise HTTPException(502, f"CVE API error: {e.response.status_code}")
    except Exception as exc:
        raise HTTPException(502, str(exc))

    await _set_cached(db, cache_key, data)
    return {**data, "cached": False}
