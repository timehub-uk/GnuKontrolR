import os
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.auth import require_admin

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
