"""
Security advisor — live domain/container security checks.
Exposes HTTP polling + WebSocket duplex endpoints.
Auto-fix actions for common misconfigurations.
"""
import asyncio
import json
import re
import socket
import ssl
import subprocess
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy import select

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models.domain import Domain
from app.models.user import User, Role

router = APIRouter(prefix="/api/security", tags=["security"])


# ── Check definitions ─────────────────────────────────────────────────────────

async def _check_ssl(domain: str) -> dict:
    """Verify SSL cert is valid and not expiring soon."""
    try:
        ctx = ssl.create_default_context()
        conn = ctx.wrap_socket(socket.socket(), server_hostname=domain)
        conn.settimeout(5)
        conn.connect((domain, 443))
        cert = conn.getpeercert()
        conn.close()
        try:
            expires = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        except ValueError:
            # Some certs use a slightly different format; treat as unknown expiry
            return {"id": "ssl_expiry", "severity": "warn", "title": "SSL Certificate Expiry Unknown",
                    "message": "Could not parse certificate expiry date.", "auto_fixable": False}
        days_left = (expires - datetime.now(timezone.utc)).days
        if days_left < 7:
            return {"id": "ssl_expiry", "severity": "critical", "title": "SSL Certificate Expiring",
                    "message": f"Certificate expires in {days_left} days.",
                    "auto_fixable": True,
                    "remediation": "Request a new Let's Encrypt certificate via SSL / TLS page."}
        if days_left < 30:
            return {"id": "ssl_expiry", "severity": "high", "title": "SSL Certificate Expiring Soon",
                    "message": f"Certificate expires in {days_left} days.",
                    "auto_fixable": True}
        return {"id": "ssl_expiry", "severity": "pass", "title": "SSL Certificate Valid",
                "message": f"Certificate valid for {days_left} more days."}
    except ssl.SSLError as e:
        return {"id": "ssl_valid", "severity": "critical", "title": "SSL Certificate Invalid",
                "message": str(e), "auto_fixable": True}
    except Exception:
        return {"id": "ssl_reachable", "severity": "medium", "title": "SSL Check Skipped",
                "message": "Domain not publicly reachable for SSL check.",
                "details": ["This may be expected for local/dev domains."]}


async def _check_container_running(domain: str) -> dict:
    name = "site_" + domain.replace(".", "_").replace("-", "_")
    loop = asyncio.get_running_loop()
    def _run():
        r = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", name],
            capture_output=True, text=True, timeout=5
        )
        return r.returncode, r.stdout.strip()
    try:
        code, out = await loop.run_in_executor(None, _run)
        if code != 0:
            return {"id": "container_running", "severity": "critical", "title": "Container Not Found",
                    "message": f"No container found for {domain}.",
                    "auto_fixable": False,
                    "remediation": "Create the domain container from the Containers page."}
        if out != "true":
            return {"id": "container_running", "severity": "high", "title": "Container Stopped",
                    "message": f"Container {name} is not running.",
                    "auto_fixable": True,
                    "remediation": f"docker start {name}"}
        return {"id": "container_running", "severity": "pass", "title": "Container Running",
                "message": "Domain container is active."}
    except Exception as e:
        return {"id": "container_running", "severity": "medium", "title": "Container Check Failed",
                "message": str(e)}


async def _check_http_headers(domain: str) -> list[dict]:
    """Check for security HTTP headers."""
    checks = []
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5, verify=False, follow_redirects=True) as c:
            r = await c.get(f"https://{domain}")
            headers = {k.lower(): v for k, v in r.headers.items()}

        for header, detail in [
            ("x-frame-options",          "Prevents clickjacking attacks"),
            ("x-content-type-options",   "Prevents MIME-type sniffing"),
            ("referrer-policy",          "Controls referrer information"),
            ("permissions-policy",       "Restricts browser feature access"),
        ]:
            if header in headers:
                checks.append({"id": f"header_{header}", "severity": "pass",
                                "title": f"Header: {header}", "message": detail})
            else:
                checks.append({"id": f"header_{header}", "severity": "medium",
                                "title": f"Missing Header: {header}",
                                "message": detail,
                                "auto_fixable": True,
                                "remediation": f"Add to nginx config: add_header {header} ... always;"})

        # Content-Security-Policy is high severity if missing
        if "content-security-policy" not in headers:
            checks.append({"id": "header_csp", "severity": "high",
                           "title": "Missing Content-Security-Policy",
                           "message": "CSP prevents XSS and data injection attacks.",
                           "auto_fixable": True,
                           "remediation": "add_header Content-Security-Policy \"default-src 'self'\" always;"})
        else:
            checks.append({"id": "header_csp", "severity": "pass",
                           "title": "Content-Security-Policy Set", "message": ""})

        # HSTS
        if "strict-transport-security" not in headers:
            checks.append({"id": "header_hsts", "severity": "high",
                           "title": "Missing HSTS Header",
                           "message": "HTTP Strict Transport Security forces HTTPS.",
                           "auto_fixable": True,
                           "remediation": "add_header Strict-Transport-Security \"max-age=31536000; includeSubDomains\" always;"})
        else:
            checks.append({"id": "header_hsts", "severity": "pass",
                           "title": "HSTS Enabled", "message": ""})

    except Exception:
        checks.append({"id": "headers_check", "severity": "low",
                       "title": "HTTP Header Check Skipped",
                       "message": "Domain not reachable for header inspection."})
    return checks


async def _check_open_ports(domain: str) -> list[dict]:
    """Warn about unexpected open ports (quick scan of common ones)."""
    risky_ports = {21: "FTP", 23: "Telnet", 3306: "MySQL", 5432: "PostgreSQL",
                   6379: "Redis", 27017: "MongoDB", 8080: "Alt HTTP"}
    checks = []
    loop = asyncio.get_running_loop()

    async def probe(port):
        try:
            fut = loop.run_in_executor(None, lambda: socket.create_connection((domain, port), timeout=2))
            await asyncio.wait_for(asyncio.wrap_future(fut), timeout=3)
            return True
        except Exception:
            return False

    tasks = {port: asyncio.create_task(probe(port)) for port in risky_ports}
    for port, task in tasks.items():
        try:
            open_ = await task
            if open_:
                checks.append({"id": f"port_{port}", "severity": "high",
                               "title": f"Port {port} ({risky_ports[port]}) Open",
                               "message": f"{risky_ports[port]} is publicly accessible — should be restricted.",
                               "auto_fixable": False,
                               "remediation": f"Block port {port} in firewall: ufw deny {port}"})
        except Exception:
            pass
    return checks


async def run_all_checks(domain: str) -> list[dict]:
    results = []
    # Run IO-bound checks concurrently
    ssl_check, container_check, header_checks, port_checks = await asyncio.gather(
        _check_ssl(domain),
        _check_container_running(domain),
        _check_http_headers(domain),
        _check_open_ports(domain),
        return_exceptions=True,
    )
    if isinstance(ssl_check, dict):       results.append(ssl_check)
    if isinstance(container_check, dict): results.append(container_check)
    if isinstance(header_checks, list):   results.extend(header_checks)
    if isinstance(port_checks, list):     results.extend(port_checks)
    return results


# ── HTTP endpoint ─────────────────────────────────────────────────────────────

@router.get("/check/{domain}")
async def security_check(domain: str, _=Depends(get_current_user)):
    checks = await run_all_checks(domain)
    score  = round(100 * sum(1 for c in checks if c["severity"] == "pass") / max(len(checks), 1))
    return {"domain": domain, "score": score, "checks": checks, "checked_at": datetime.utcnow().isoformat()}


# ── WebSocket duplex ──────────────────────────────────────────────────────────

@router.websocket("/ws/{domain}")
async def security_ws(websocket: WebSocket, domain: str, token: str = ""):
    """
    Duplex WS: sends full check results on connect, then re-runs every 30s.
    Client can send {"action": "rescan"} to trigger immediate re-scan.
    """
    from app.auth import _decode_token
    if not token or not _decode_token(token):
        await websocket.close(code=4001, reason="Unauthorized")
        return
    await websocket.accept()
    try:
        async def send_checks():
            checks = await run_all_checks(domain)
            score  = round(100 * sum(1 for c in checks if c["severity"] == "pass") / max(len(checks), 1))
            await websocket.send_json({"domain": domain, "score": score, "checks": checks})

        await send_checks()

        async def periodic():
            while True:
                await asyncio.sleep(30)
                await send_checks()

        recv_task    = asyncio.create_task(_recv_commands(websocket, send_checks))
        periodic_task = asyncio.create_task(periodic())

        done, pending = await asyncio.wait(
            [recv_task, periodic_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()

    except WebSocketDisconnect:
        pass


async def _recv_commands(ws: WebSocket, rescan_fn):
    """Handle incoming commands from the client."""
    while True:
        try:
            msg = await ws.receive_text()
            data = json.loads(msg)
            if data.get("action") == "rescan":
                await rescan_fn()
        except (WebSocketDisconnect, RuntimeError):
            break
        except Exception:
            pass


# ── Auto-fix endpoint ─────────────────────────────────────────────────────────

class FixRequest(BaseModel):
    check_id: str


# All security headers applied together — idempotent, safe to rewrite every time.
_SECURITY_HEADERS_NGINX = """\
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=()" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'none';" always;
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
add_header Cross-Origin-Opener-Policy "same-origin" always;
add_header Cross-Origin-Resource-Policy "same-site" always;
"""

_HEADER_CHECK_IDS = {
    "header_x-frame-options", "header_x-content-type-options",
    "header_referrer-policy", "header_permissions-policy",
    "header_csp", "header_hsts",
}

_CONTAINER_API_PORT = 9000


def _container_url(domain: str, path: str) -> str:
    container = "site_" + domain.replace(".", "_").replace("-", "_")
    return f"https://{container}:{_CONTAINER_API_PORT}{path}"


def _get_token() -> str:
    import os
    return os.environ.get("CONTAINER_API_TOKEN", "")


async def _assert_domain_owner(domain: str, user: User, db) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select as _sel
    if user.role in (Role.superadmin, Role.admin):
        return
    result = await db.execute(
        _sel(Domain).where(Domain.name == domain, Domain.owner_id == user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(403, "Access denied: domain not owned by you")


@router.post("/fix/{domain}")
async def auto_fix(
    domain: str,
    body: FixRequest,
    current: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Apply an auto-fix for a security check.  Domain owners can fix their own domains."""
    await _assert_domain_owner(domain, current, db)

    check_id = body.check_id

    # ── Any missing security header → apply the full hardened header set ──────
    if check_id in _HEADER_CHECK_IDS:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=15, verify=False) as c:
                r = await c.post(
                    _container_url(domain, "/secure/nginx"),
                    json={"name": "security_headers", "content": _SECURITY_HEADERS_NGINX},
                    headers={"Authorization": f"Bearer {_get_token()}"},
                )
                if r.status_code not in (200, 201):
                    raise HTTPException(500, f"Container API error {r.status_code}: {r.text[:200]}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Could not reach container API: {e}")

        return {
            "ok": True,
            "applied": list(_HEADER_CHECK_IDS),
            "message": (
                f"All security headers applied to {domain}.\n"
                "Headers: X-Frame-Options, X-Content-Type-Options, Referrer-Policy, "
                "Permissions-Policy, Content-Security-Policy, HSTS, COOP, CORP.\n"
                "Nginx reloaded inside container."
            ),
        }

    # ── Container not running ─────────────────────────────────────────────────
    if check_id == "container_running":
        name = "site_" + domain.replace(".", "_").replace("-", "_")
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                ["docker", "start", name],
                capture_output=True, text=True, timeout=15,
            ),
        )
        if result.returncode != 0:
            raise HTTPException(500, f"docker start failed: {result.stderr}")
        return {"ok": True, "message": f"Container {name} started."}

    raise HTTPException(400, f"No auto-fix available for check_id: {check_id!r}")


# ── Global threat intelligence (CISA KEV) ─────────────────────────────────────

_threats_cache: dict | None = None
_threats_cache_ts: float = 0
_THREATS_TTL = 300  # 5 minutes


@router.get("/threats")
async def get_threats(_=Depends(get_current_user)):
    """
    Return recent CISA Known Exploited Vulnerabilities (KEV) catalog entries.
    Cached for 5 minutes to avoid hammering the CISA API.
    """
    global _threats_cache, _threats_cache_ts
    now = time.time()
    if _threats_cache is not None and (now - _threats_cache_ts) < _THREATS_TTL:
        return _threats_cache

    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get("https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json")
            r.raise_for_status()
            data = r.json()
        # Return the 20 most recently added vulnerabilities
        vulns = data.get("vulnerabilities", [])
        vulns_sorted = sorted(vulns, key=lambda v: v.get("dateAdded", ""), reverse=True)[:20]
        threats = []
        for v in vulns_sorted:
            severity = "HIGH"
            product = v.get("product", "")
            vendor = v.get("vendorProject", "")
            if "critical" in v.get("shortDescription", "").lower():
                severity = "CRITICAL"
            elif any(x in v.get("shortDescription", "").lower() for x in ["remote code", "rce", "unauthenticated"]):
                severity = "CRITICAL"
            threats.append({
                "id": v.get("cveID", ""),
                "title": f"{vendor} {product} — {v.get('vulnerabilityName', '')}",
                "severity": severity,
                "date_added": v.get("dateAdded", ""),
                "due_date": v.get("dueDate", ""),
                "description": v.get("shortDescription", ""),
                "ransomware_use": v.get("knownRansomwareCampaignUse", "Unknown"),
                "nvd_url": f"https://nvd.nist.gov/vuln/detail/{v.get('cveID', '')}",
            })
        result = {"threats": threats, "count": len(data.get("vulnerabilities", [])),
                  "catalog_version": data.get("catalogVersion", ""), "fetched_at": datetime.utcnow().isoformat()}
        _threats_cache = result
        _threats_cache_ts = now
        return result
    except Exception as e:
        # Return empty on error rather than crashing the dashboard
        return {"threats": [], "count": 0, "catalog_version": "", "error": str(e),
                "fetched_at": datetime.utcnow().isoformat()}


@router.delete("/threats/cache")
async def clear_threats_cache(_=Depends(require_admin)):
    """Force next call to re-fetch from CISA."""
    global _threats_cache, _threats_cache_ts
    _threats_cache = None
    _threats_cache_ts = 0
    return {"ok": True}


# ── Domain suggest autocomplete ───────────────────────────────────────────────

@router.get("/suggest/domains")
async def suggest_domains(
    q: str = "",
    db=Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return domain name suggestions based on query (for SmartInput autocomplete)."""
    stmt = select(Domain.name)
    if user.role not in (Role.superadmin, Role.admin):
        stmt = stmt.where(Domain.owner_id == user.id)
    if q:
        stmt = stmt.where(Domain.name.ilike(f"%{q}%"))
    stmt = stmt.limit(10)
    result = await db.execute(stmt)
    return [row[0] for row in result.fetchall()]
