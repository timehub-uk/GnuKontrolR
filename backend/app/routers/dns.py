import asyncio
import os
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.auth import require_admin, get_current_user

router = APIRouter(prefix="/api/dns", tags=["dns"])

PDNS_BASE = os.getenv("PDNS_API_URL", "http://webpanel_powerdns:8081/api/v1/servers/localhost")
PDNS_KEY  = os.getenv("PDNS_API_KEY", "changeme_pdns_key")
HEADERS   = {"X-API-Key": PDNS_KEY, "Content-Type": "application/json"}

async def pdns_get(path: str):
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{PDNS_BASE}{path}", headers=HEADERS)
        r.raise_for_status()
        return r.json()

async def pdns_post(path: str, data: dict):
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{PDNS_BASE}{path}", headers=HEADERS, json=data)
        r.raise_for_status()
        return r.json() if r.content else {}

async def pdns_patch(path: str, data: dict):
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.patch(f"{PDNS_BASE}{path}", headers=HEADERS, json=data)
        r.raise_for_status()
        return r.json() if r.content else {}

async def pdns_delete(path: str):
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.delete(f"{PDNS_BASE}{path}", headers=HEADERS)
        if r.status_code not in (200, 204):
            r.raise_for_status()
        return {}


class RecordRequest(BaseModel):
    name: str
    type: str
    content: str
    ttl: int = 300

class ZoneKindRequest(BaseModel):
    kind: str   # 'Native' | 'Master' | 'Slave'


@router.get("/zones")
async def list_zones(user=Depends(require_admin)):
    try:
        return await pdns_get("/zones")
    except httpx.HTTPError as e:
        raise HTTPException(502, f"PowerDNS unreachable: {e}")


@router.get("/zones/{zone}")
async def get_zone(zone: str, user=Depends(require_admin)):
    zone_id = zone if zone.endswith(".") else zone + "."
    try:
        return await pdns_get(f"/zones/{zone_id}")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(404, "Zone not found")
        raise HTTPException(502, str(e))


@router.post("/zones/{zone}/records")
async def add_record(zone: str, req: RecordRequest, user=Depends(require_admin)):
    zone_id = zone if zone.endswith(".") else zone + "."
    name    = req.name if req.name.endswith(".") else req.name + "."
    payload = {
        "rrsets": [{
            "name": name,
            "type": req.type.upper(),
            "ttl": req.ttl,
            "changetype": "REPLACE",
            "records": [{"content": req.content, "disabled": False}],
        }]
    }
    try:
        return await pdns_patch(f"/zones/{zone_id}", payload)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"PowerDNS error: {e}")


@router.delete("/zones/{zone}/records")
async def delete_record(zone: str, name: str, type: str, user=Depends(require_admin)):
    zone_id = zone if zone.endswith(".") else zone + "."
    name    = name if name.endswith(".") else name + "."
    payload = {
        "rrsets": [{
            "name": name,
            "type": type.upper(),
            "changetype": "DELETE",
        }]
    }
    try:
        return await pdns_patch(f"/zones/{zone_id}", payload)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"PowerDNS error: {e}")


@router.post("/zones")
async def create_zone(zone: str, user=Depends(require_admin)):
    zone_id = zone if zone.endswith(".") else zone + "."
    payload = {
        "name": zone_id,
        "kind": "Native",
        "nameservers": [],
        "rrsets": [],
    }
    try:
        return await pdns_post("/zones", payload)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"PowerDNS error: {e}")


async def _dig(domain: str, record_type: str) -> list[str]:
    """Run a dig query against 8.8.8.8, return list of answer strings."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "dig", "+short", "+time=3", "+tries=2",
            domain, record_type, "@8.8.8.8",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=8)
        lines = [l.strip().rstrip(".") for l in stdout.decode().splitlines() if l.strip()]
        return lines
    except Exception:
        return []


async def _dig_soa(domain: str) -> dict | None:
    """Run dig SOA against 8.8.8.8, return parsed dict or None."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "dig", "+short", "+time=3", "+tries=2",
            domain, "SOA", "@8.8.8.8",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=8)
        line = stdout.decode().strip()
        if not line:
            return None
        parts = line.split()
        if len(parts) < 7:
            return None
        return {
            "primary_ns": parts[0].rstrip("."),
            "email":      parts[1].rstrip(".").replace(".", "@", 1),
            "serial":     parts[2],
            "refresh":    parts[3],
            "retry":      parts[4],
            "expire":     parts[5],
            "minimum":    parts[6],
        }
    except Exception:
        return None


@router.get("/lookup/{domain}")
async def external_lookup(domain: str, user=Depends(get_current_user)):
    """Public DNS lookup for a domain — A, NS, MX, SOA records via 8.8.8.8."""
    a_task   = asyncio.create_task(_dig(domain, "A"))
    ns_task  = asyncio.create_task(_dig(domain, "NS"))
    mx_task  = asyncio.create_task(_dig(domain, "MX"))
    soa_task = asyncio.create_task(_dig_soa(domain))
    a, ns, mx, soa = await asyncio.gather(a_task, ns_task, mx_task, soa_task)
    return {"domain": domain, "A": a, "NS": ns, "MX": mx, "SOA": soa}


@router.patch("/zones/{zone}/kind")
async def set_zone_kind(zone: str, req: ZoneKindRequest, user=Depends(require_admin)):
    """Switch a zone between Native / Master / Slave."""
    allowed = {"Native", "Master", "Slave"}
    if req.kind not in allowed:
        raise HTTPException(400, f"kind must be one of {allowed}")
    zone_id = zone if zone.endswith(".") else zone + "."
    try:
        return await pdns_patch(f"/zones/{zone_id}", {"kind": req.kind})
    except httpx.HTTPError as e:
        raise HTTPException(502, f"PowerDNS error: {e}")


@router.patch("/zones/{zone}/soa", dependencies=[Depends(require_admin)])
async def update_soa(zone: str, body: dict):
    """Update the SOA record for a zone.

    Accepts: { primary_ns, email, serial, refresh, retry, expire, minimum }
    Any omitted field keeps its current value.
    Passing serial=0 auto-bumps by 1.
    """
    zone_id = zone if zone.endswith(".") else zone + "."

    # Fetch current SOA
    try:
        zdata = await pdns_get(f"/zones/{zone_id}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, "Zone not found")

    current_soa = None
    for rr in zdata.get("rrsets", []):
        if rr["type"] == "SOA":
            current_soa = rr
            break

    if not current_soa or not current_soa.get("records"):
        raise HTTPException(404, "SOA record not found in zone")

    # Parse current content:  primary email serial refresh retry expire minimum
    parts = current_soa["records"][0]["content"].split()
    if len(parts) < 7:
        raise HTTPException(502, f"Unexpected SOA format: {current_soa['records'][0]['content']}")

    cur_primary, cur_email, cur_serial, cur_refresh, cur_retry, cur_expire, cur_min = parts[:7]

    primary  = body.get("primary_ns", cur_primary).rstrip(".") + "."
    email    = body.get("email",      cur_email).rstrip(".") + "."
    refresh  = int(body.get("refresh", cur_refresh))
    retry    = int(body.get("retry",   cur_retry))
    expire   = int(body.get("expire",  cur_expire))
    minimum  = int(body.get("minimum", cur_min))

    # Serial: 0 = auto-bump, otherwise use provided value
    new_serial = int(body.get("serial", 0))
    if new_serial == 0:
        new_serial = int(cur_serial) + 1

    content = f"{primary} {email} {new_serial} {refresh} {retry} {expire} {minimum}"

    payload = {"rrsets": [{
        "name":       zone_id,
        "type":       "SOA",
        "ttl":        current_soa.get("ttl", 3600),
        "changetype": "REPLACE",
        "records":    [{"content": content, "disabled": False}],
    }]}
    try:
        await pdns_patch(f"/zones/{zone_id}", payload)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"PowerDNS error: {e}")

    return {
        "ok":        True,
        "zone":      zone,
        "soa":       content,
        "serial":    new_serial,
        "primary_ns": primary.rstrip("."),
    }


@router.post("/zones/{zone}/ensure")
async def ensure_zone(zone: str, user=Depends(require_admin)):
    """Create zone if it doesn't exist, return zone info."""
    zone_id = zone if zone.endswith(".") else zone + "."
    try:
        return await pdns_get(f"/zones/{zone_id}")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            payload = {"name": zone_id, "kind": "Native", "nameservers": [], "rrsets": []}
            try:
                return await pdns_post("/zones", payload)
            except httpx.HTTPError as e2:
                raise HTTPException(502, f"PowerDNS error: {e2}")
        raise HTTPException(502, str(e))
