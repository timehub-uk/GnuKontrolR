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


def _zone_create_payload(zone_id: str) -> dict:
    """Build a zone creation payload with a correct SOA primary NS."""
    zone_name = zone_id.rstrip(".")
    primary_ns = f"ns1.{zone_name}."
    hostmaster = f"hostmaster.{zone_name}."
    soa_content = f"{primary_ns} {hostmaster} 1 10800 3600 604800 3600"
    return {
        "name": zone_id,
        "kind": "Native",
        "nameservers": [],
        "rrsets": [{
            "name": zone_id,
            "type": "SOA",
            "ttl": 3600,
            "records": [{"content": soa_content, "disabled": False}],
        }],
    }


@router.post("/zones")
async def create_zone(zone: str, user=Depends(require_admin)):
    zone_id = zone if zone.endswith(".") else zone + "."
    try:
        return await pdns_post("/zones", _zone_create_payload(zone_id))
    except httpx.HTTPError as e:
        raise HTTPException(502, f"PowerDNS error: {e}")


_DNS_RESOLVER = None

def _get_resolver():
    """Return a cached dnspython resolver pointed at 8.8.8.8."""
    global _DNS_RESOLVER
    if _DNS_RESOLVER is None:
        import dns.resolver as _r
        res = _r.Resolver(configure=False)
        res.nameservers = ["8.8.8.8", "8.8.4.4"]
        res.timeout = 4
        res.lifetime = 8
        _DNS_RESOLVER = res
    return _DNS_RESOLVER


def _dns_query(domain: str, rtype: str) -> list[str]:
    """Blocking DNS query via dnspython → list of string answers."""
    import dns.resolver, dns.exception
    try:
        answers = _get_resolver().resolve(domain, rtype, raise_on_no_answer=False)
        results = []
        for r in answers:
            txt = r.to_text().rstrip(".")
            results.append(txt)
        return results
    except (dns.resolver.NXDOMAIN, dns.resolver.NoNameservers,
            dns.exception.Timeout, dns.resolver.NoAnswer):
        return []
    except Exception:
        return []


def _dns_ptr(ip: str) -> str:
    """Reverse PTR lookup for an IP — returns hostname or empty string."""
    import dns.reversename, dns.exception
    try:
        rev = dns.reversename.from_address(ip)
        answers = _get_resolver().resolve(rev, "PTR", raise_on_no_answer=False)
        for r in answers:
            return str(r.to_text()).rstrip(".")
        return ""
    except Exception:
        return ""


def _company_from_ptr(ptr: str) -> str:
    """Extract a readable company name from a PTR hostname."""
    if not ptr:
        return ""
    # Strip common dynamic-IP prefixes like ip74-208-111-216.pbiaas.com → pbiaas.com
    import re
    # Remove leading segments that look like encoded IPs or hostnames
    parts = ptr.split(".")
    # Take last 2 parts as the domain (e.g. pbiaas.com, godaddy.com)
    if len(parts) >= 2:
        apex = ".".join(parts[-2:])
        # Map known apex domains to friendly names
        _KNOWN = {
            "pbiaas.com":        "PurelyBrands / Web.com",
            "web.com":           "Web.com",
            "networksolutions.com": "Network Solutions",
            "godaddy.com":       "GoDaddy",
            "cloudflare.com":    "Cloudflare",
            "awsdns.com":        "Amazon Route 53",
            "awsdns.net":        "Amazon Route 53",
            "awsdns.org":        "Amazon Route 53",
            "awsdns.info":       "Amazon Route 53",
            "hetzner.com":       "Hetzner",
            "ovh.net":           "OVH",
            "digitalocean.com":  "DigitalOcean",
            "linode.com":        "Linode / Akamai",
            "vultr.com":         "Vultr",
            "namecheap.com":     "Namecheap",
            "registrar-servers.com": "Namecheap",
            "domaincontrol.com": "GoDaddy",
            "name-services.com": "enom / Tucows",
            "ultradns.net":      "UltraDNS",
            "dynect.net":        "Dyn DNS",
        }
        return _KNOWN.get(apex, apex)
    return ptr


def _dns_soa(domain: str) -> dict | None:
    """Query SOA via dnspython, return parsed dict or None."""
    import dns.resolver, dns.exception
    try:
        answers = _get_resolver().resolve(domain, "SOA", raise_on_no_answer=False)
        for r in answers:
            mname  = str(r.mname).rstrip(".")
            rname  = str(r.rname).rstrip(".")
            # rname uses dots for @ — first dot is the @ separator
            email  = rname.replace(".", "@", 1)
            return {
                "primary_ns": mname,
                "email":      email,
                "serial":     str(r.serial),
                "refresh":    str(r.refresh),
                "retry":      str(r.retry),
                "expire":     str(r.expire),
                "minimum":    str(r.minimum),
            }
        return None
    except Exception:
        return None


@router.get("/lookup/{domain}")
async def external_lookup(domain: str, user=Depends(get_current_user)):
    """Public DNS lookup for a domain — A, AAAA, NS (with glue IPs), MX, SOA via 8.8.8.8."""
    loop = asyncio.get_running_loop()

    a, aaaa, ns, mx, soa = await asyncio.gather(
        loop.run_in_executor(None, _dns_query, domain, "A"),
        loop.run_in_executor(None, _dns_query, domain, "AAAA"),
        loop.run_in_executor(None, _dns_query, domain, "NS"),
        loop.run_in_executor(None, _dns_query, domain, "MX"),
        loop.run_in_executor(None, _dns_soa,   domain),
    )

    # Resolve each NS hostname → its own A record (glue IP) in parallel
    ns_ip_results = await asyncio.gather(
        *[loop.run_in_executor(None, _dns_query, n, "A") for n in ns]
    )
    ns_ips = {n: ips for n, ips in zip(ns, ns_ip_results)}

    # PTR lookup on each unique NS IP → company name
    all_ns_ips = list({ip for ips in ns_ips.values() for ip in ips})
    ptr_results = await asyncio.gather(
        *[loop.run_in_executor(None, _dns_ptr, ip) for ip in all_ns_ips]
    )
    ns_companies = {
        ip: _company_from_ptr(ptr)
        for ip, ptr in zip(all_ns_ips, ptr_results)
    }

    server_ip = os.getenv("SERVER_IP", "")

    return {
        "domain":    domain,
        "A":         a,
        "AAAA":      aaaa,
        "NS":        ns,
        "ns_ips":      ns_ips,
        "ns_companies": ns_companies,
        "MX":          mx,
        "SOA":       soa,
        "server_ip": server_ip,
    }


@router.patch("/zones/{zone}/kind")
async def set_zone_kind(zone: str, req: ZoneKindRequest, user=Depends(require_admin)):
    """Switch a zone between Native / Master / Slave."""
    # PowerDNS 4.5+ uses Primary/Secondary; accept old names and normalise
    _alias = {"Master": "Primary", "Slave": "Secondary"}
    kind = _alias.get(req.kind, req.kind)
    allowed = {"Native", "Primary", "Secondary"}
    if kind not in allowed:
        raise HTTPException(400, f"kind must be one of {allowed}")
    req = ZoneKindRequest(kind=kind)
    zone_id = zone if zone.endswith(".") else zone + "."
    try:
        # Zone metadata changes (kind) require PUT, not PATCH in PowerDNS 4.x
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.put(f"{PDNS_BASE}/zones/{zone_id}", headers=HEADERS, json={"kind": req.kind})
            r.raise_for_status()
        return {"ok": True, "zone": zone, "kind": req.kind}
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
            try:
                return await pdns_post("/zones", _zone_create_payload(zone_id))
            except httpx.HTTPError as e2:
                raise HTTPException(502, f"PowerDNS error: {e2}")
        raise HTTPException(502, str(e))
