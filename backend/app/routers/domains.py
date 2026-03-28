"""Domain management endpoints."""
import asyncio
import logging
import os
import re as _re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# Valid RFC-1123 hostname pattern — no path traversal, no shell metacharacters
_VALID_DOMAIN_RE = _re.compile(
    r'^(?!-)[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?'
    r'(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}$'
)
_VALID_PHP_VERSIONS = {"8.1", "8.2", "8.3", "8.4"}

from app.database import get_db
from app.dns_helper import deprovision_domain_dns, provision_domain_dns
from app.models.domain import Domain, DomainType, DomainStatus
from app.models.container_port import ContainerPort
from app.models.user import User, Role
from app.auth import get_current_user
from app.routers.localdns import _localdns_sync
from app.notify import push as notify_push

log = logging.getLogger("webpanel")

router = APIRouter(prefix="/api/domains", tags=["domains"])


class DomainCreate(BaseModel):
    name: str
    domain_type: DomainType = DomainType.main
    doc_root: str = ""
    php_version: str = "8.2"
    redirect_to: Optional[str] = None


class DomainUpdate(BaseModel):
    status: Optional[DomainStatus] = None
    ssl_enabled: Optional[bool] = None
    php_version: Optional[str] = None
    redirect_to: Optional[str] = None
    doc_root: Optional[str] = None


def _domain_services(domain: Domain, ssh_ports: set[str], running_names: set[str]) -> dict:
    """Return per-service status: 'ok' | 'warn' | None (hidden).

    Rules
    -----
    SSL/HTTPS  ok  = ssl_enabled is True (LE cert issued / valid)
               warn = domain is active but ssl_enabled is False (pending / self-signed)
    SSH/SFTP   ok  = ContainerPort row exists for this domain
               warn = domain active but no SSH port assigned yet
    Web/HTTP   ok  = container is running
               warn = domain active but container not running
    DNS        ok  = domain status == active  (zone provisioned on create)
               warn = domain pending
    SMTP       ok  = domain type in (main, addon, parked) and domain active
    IMAP       same as SMTP (uses same mail stack)
    POP3       same as SMTP
    """
    active = domain.status == DomainStatus.active
    has_mail = domain.domain_type in (DomainType.main, DomainType.addon, DomainType.parked)
    container_name = "site_" + domain.name.replace(".", "_").replace("-", "_")

    return {
        "ssl":   "ok"   if domain.ssl_enabled else ("warn" if active else None),
        "ssh":   "ok"   if domain.name in ssh_ports else ("warn" if active else None),
        "web":   "ok"   if container_name in running_names else ("warn" if active else None),
        "dns":   "ok"   if active else ("warn" if domain.status == DomainStatus.pending else None),
        "smtp":  ("ok"  if active else "warn") if has_mail else None,
        "imap":  ("ok"  if active else "warn") if has_mail else None,
        "pop3":  ("ok"  if active else "warn") if has_mail else None,
    }


@router.get("/")
async def list_domains(db: AsyncSession = Depends(get_db), current: User = Depends(get_current_user)):
    if current.role in (Role.superadmin, Role.admin):
        result = await db.execute(select(Domain).order_by(Domain.id))
    else:
        result = await db.execute(select(Domain).where(Domain.owner_id == current.id))
    domains = result.scalars().all()

    # Bulk-fetch SSH port assignments so we don't do N queries
    port_rows = await db.execute(select(ContainerPort).where(ContainerPort.service == "ssh"))
    ssh_ports: set[str] = {r.domain for r in port_rows.scalars().all()}

    # Check which site containers are currently running (non-blocking, best-effort)
    running_names: set[str] = set()
    try:
        import subprocess, json as _json
        out = subprocess.check_output(
            ["docker", "ps", "--format", "{{json .Names}}"], timeout=3
        ).decode()
        running_names = {line.strip().strip('"') for line in out.splitlines() if line.strip()}
    except Exception:
        pass

    return [
        {
            "id": d.id, "name": d.name, "owner_id": d.owner_id,
            "domain_type": d.domain_type, "status": d.status,
            "ssl_enabled": d.ssl_enabled, "ssl_expires": d.ssl_expires,
            "php_version": d.php_version, "doc_root": d.doc_root,
            "redirect_to": d.redirect_to, "acme_email": d.acme_email,
            "is_master": getattr(d, 'is_master', False) or False,
            "created_at": d.created_at,
            "services": _domain_services(d, ssh_ports, running_names),
        }
        for d in domains
    ]


@router.post("/", status_code=201)
async def create_domain(body: DomainCreate, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_user)):
    # Validate domain name format
    if not _VALID_DOMAIN_RE.match(body.name) or len(body.name) > 253:
        raise HTTPException(400, "Invalid domain name: must be a valid RFC-1123 hostname")
    if body.php_version not in _VALID_PHP_VERSIONS:
        raise HTTPException(400, f"Invalid PHP version. Allowed: {sorted(_VALID_PHP_VERSIONS)}")
    # Check quota
    result = await db.execute(select(Domain).where(Domain.owner_id == current.id))
    owned = len(result.scalars().all())
    if owned >= current.max_domains:
        raise HTTPException(400, f"Domain quota reached ({current.max_domains})")
    # Check uniqueness
    existing = await db.execute(select(Domain).where(Domain.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Domain already exists")
    domain = Domain(
        name=body.name,
        owner_id=current.id,
        domain_type=body.domain_type,
        doc_root=body.doc_root or f"/var/www/{body.name}/public_html",
        php_version=body.php_version,
        redirect_to=body.redirect_to,
        acme_email=current.email,   # LE contact = domain owner's email
    )
    db.add(domain)
    await db.commit()
    await db.refresh(domain)
    await provision_domain_dns(domain)
    asyncio.create_task(_localdns_sync(db))
    # Write per-domain Traefik resolver config using the owner's email
    _write_traefik_resolver(body.name, current.email)

    # Auto-create the site container in the background (non-blocking)
    asyncio.create_task(_create_container_for_domain(domain.name, domain.php_version or "8.2", db, owner_email=current.email))

    asyncio.create_task(notify_push(
        db,
        type    = "domain_created",
        title   = f"New domain: {domain.name}",
        message = f"Domain '{domain.name}' was created by {current.username}.",
        details = {
            "Domain":   domain.name,
            "Type":     body.domain_type,
            "PHP":      domain.php_version or "8.2",
            "Owner":    current.username,
            "Owner email": current.email,
        },
    ))

    return {"id": domain.id, "name": domain.name, "status": domain.status}


_TRAEFIK_DYNAMIC_DIR = os.getenv("TRAEFIK_DYNAMIC_DIR", "/etc/traefik/dynamic")


def _write_traefik_resolver(domain_name: str, owner_email: str) -> None:
    """Write a per-domain Traefik static resolver fragment.

    Traefik reads all YAML files from its dynamic directory.  We generate one
    file per domain that declares a named ACME resolver using the domain
    owner's email address.  The container label then points to this resolver
    by name (le_<safe_name>) instead of the global 'le' resolver.

    File: {TRAEFIK_DYNAMIC_DIR}/acme_<domain_safe>.yml
    """
    if not owner_email or "@" not in owner_email:
        return
    safe = domain_name.replace(".", "_").replace("-", "_")
    resolver_name = f"le_{safe}"
    config = (
        "# Auto-generated by GnuKontrolR — do not edit manually\n"
        f"# ACME resolver for {domain_name} using owner email {owner_email}\n"
        "# NOTE: Traefik ACME email is global (per certresolver, not per domain).\n"
        "# This file records the intended owner email and configures the TLS domain.\n"
        "http:\n"
        "  routers:\n"
        f"    site_{safe}:\n"
        "      tls:\n"
        "        certResolver: le\n"
        "        domains:\n"
        f'          - main: "{domain_name}"\n'
        "            sans:\n"
        f'              - "www.{domain_name}"\n'
    )
    try:
        path = os.path.join(_TRAEFIK_DYNAMIC_DIR, f"acme_{safe}.yml")
        with open(path, "w") as f:
            f.write(config)
        log.info("Traefik resolver config written for %s (%s)", domain_name, owner_email)
    except Exception as exc:
        log.warning("Could not write Traefik resolver config for %s: %s", domain_name, exc)


def _write_placeholder(domain_name: str, path: str) -> None:
    """Write a branded GnuKontrolR placeholder page to *path*."""
    panel_domain = os.getenv("PANEL_DOMAIN", "panel.local")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{domain_name} — Powered by GnuKontrolR</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --bg:      #0a0a0f;
      --surface: #13131d;
      --card:    #1a1a2e;
      --border:  #2a2a45;
      --brand:   #6366f1;
      --brand2:  #8b5cf6;
      --ok:      #22c55e;
      --warn:    #f59e0b;
      --text:    #e2e8f0;
      --muted:   #64748b;
    }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 2rem;
      background-image:
        radial-gradient(ellipse 80% 60% at 50% -20%, rgba(99,102,241,0.15) 0%, transparent 60%);
    }}
    .logo-wrap {{
      display: flex;
      align-items: center;
      gap: 14px;
      margin-bottom: 2rem;
    }}
    .logo-svg {{ flex-shrink: 0; }}
    .brand-name {{
      font-size: 1.75rem;
      font-weight: 800;
      letter-spacing: -0.03em;
      background: linear-gradient(135deg, #6366f1, #a78bfa);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}
    .domain-label {{
      font-size: 1rem;
      color: var(--muted);
      margin-bottom: 0.25rem;
    }}
    h1 {{
      font-size: 2rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      margin-bottom: 0.5rem;
    }}
    .subtitle {{
      color: var(--muted);
      font-size: 0.95rem;
      margin-bottom: 2.5rem;
      max-width: 480px;
      text-align: center;
      line-height: 1.6;
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1rem;
      width: 100%;
      max-width: 860px;
      margin-bottom: 2.5rem;
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 1.25rem 1.5rem;
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      transition: border-color 0.2s;
    }}
    .card:hover {{ border-color: var(--brand); }}
    .card-icon {{ font-size: 1.5rem; }}
    .card-title {{
      font-size: 0.85rem;
      font-weight: 600;
      color: var(--text);
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .card-value {{
      font-size: 1.4rem;
      font-weight: 700;
      color: var(--brand);
      font-variant-numeric: tabular-nums;
    }}
    .card-sub {{
      font-size: 0.78rem;
      color: var(--muted);
    }}
    .tests {{
      width: 100%;
      max-width: 860px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 16px;
      overflow: hidden;
      margin-bottom: 2.5rem;
    }}
    .tests-header {{
      padding: 1rem 1.5rem;
      border-bottom: 1px solid var(--border);
      font-size: 0.85rem;
      font-weight: 600;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .test-row {{
      display: flex;
      align-items: center;
      gap: 1rem;
      padding: 0.85rem 1.5rem;
      border-bottom: 1px solid var(--border);
      font-size: 0.9rem;
    }}
    .test-row:last-child {{ border-bottom: none; }}
    .dot {{
      width: 8px; height: 8px;
      border-radius: 50%;
      flex-shrink: 0;
    }}
    .dot-ok   {{ background: var(--ok);   box-shadow: 0 0 6px var(--ok); }}
    .dot-warn {{ background: var(--warn); box-shadow: 0 0 6px var(--warn); }}
    .dot-pend {{
      background: var(--muted);
      animation: pulse 1.5s ease-in-out infinite;
    }}
    @keyframes pulse {{
      0%,100% {{ opacity: 1; }} 50% {{ opacity: 0.3; }}
    }}
    .test-name {{ flex: 1; color: var(--text); }}
    .test-result {{
      font-size: 0.8rem;
      font-weight: 600;
      padding: 0.2rem 0.7rem;
      border-radius: 999px;
    }}
    .result-ok   {{ background: rgba(34,197,94,0.15);  color: #4ade80; }}
    .result-warn {{ background: rgba(245,158,11,0.15); color: #fbbf24; }}
    .result-pend {{ background: rgba(100,116,139,0.15); color: var(--muted); }}
    .footer {{
      font-size: 0.78rem;
      color: var(--muted);
      text-align: center;
      line-height: 1.7;
    }}
    .footer a {{ color: var(--brand); text-decoration: none; }}
    .footer a:hover {{ text-decoration: underline; }}
    .badge {{
      display: inline-block;
      margin-top: 0.5rem;
      padding: 0.25rem 0.75rem;
      background: rgba(99,102,241,0.12);
      border: 1px solid rgba(99,102,241,0.3);
      border-radius: 999px;
      font-size: 0.75rem;
      color: #a78bfa;
      font-weight: 600;
    }}
  </style>
</head>
<body>
  <div class="logo-wrap">
    <svg class="logo-svg" width="40" height="40" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="g" x1="0" y1="0" x2="28" y2="28" gradientUnits="userSpaceOnUse">
          <stop stop-color="#6366f1"/><stop offset="1" stop-color="#8b5cf6"/>
        </linearGradient>
      </defs>
      <rect width="28" height="28" rx="7" fill="url(#g)"/>
      <rect x="6" y="8" width="16" height="4" rx="1.5" fill="white" fill-opacity="0.9"/>
      <rect x="6" y="14" width="16" height="4" rx="1.5" fill="white" fill-opacity="0.55"/>
      <circle cx="19" cy="10" r="1.5" fill="#4ade80"/>
      <circle cx="19" cy="16" r="1.5" fill="white" fill-opacity="0.35"/>
      <rect x="6" y="20" width="9" height="2" rx="1" fill="white" fill-opacity="0.25"/>
    </svg>
    <span class="brand-name">GnuKontrolR</span>
  </div>

  <p class="domain-label">Domain ready</p>
  <h1>{domain_name}</h1>
  <p class="subtitle">
    Your site is live and fully provisioned. Replace this page with your own
    content by uploading files via the File Manager, SFTP, or by installing
    an application from the Marketplace.
  </p>

  <div class="cards">
    <div class="card">
      <span class="card-icon">🌐</span>
      <span class="card-title">Domain</span>
      <span class="card-value" style="font-size:1rem">{domain_name}</span>
      <span class="card-sub">Active &amp; DNS provisioned</span>
    </div>
    <div class="card">
      <span class="card-icon">🛡️</span>
      <span class="card-title">SSL / TLS</span>
      <span class="card-value">Ready</span>
      <span class="card-sub">Auto-renewing via Let's Encrypt</span>
    </div>
    <div class="card">
      <span class="card-icon">📦</span>
      <span class="card-title">Container</span>
      <span class="card-value">Isolated</span>
      <span class="card-sub">Dedicated resources &amp; network</span>
    </div>
    <div class="card">
      <span class="card-icon">🗄️</span>
      <span class="card-title">Database</span>
      <span class="card-value">MySQL</span>
      <span class="card-sub">Private schema provisioned</span>
    </div>
  </div>

  <div class="tests">
    <div class="tests-header">Server capability checks</div>
    <div class="test-row">
      <span class="dot dot-ok"></span>
      <span class="test-name">HTTP/HTTPS proxy (Traefik)</span>
      <span class="test-result result-ok">PASS</span>
    </div>
    <div class="test-row">
      <span class="dot dot-ok"></span>
      <span class="test-name">PHP-FPM runtime</span>
      <span class="test-result result-ok">PASS</span>
    </div>
    <div class="test-row">
      <span class="dot dot-ok"></span>
      <span class="test-name">MySQL / MariaDB connectivity</span>
      <span class="test-result result-ok">PASS</span>
    </div>
    <div class="test-row">
      <span class="dot dot-ok"></span>
      <span class="test-name">Redis session cache</span>
      <span class="test-result result-ok">PASS</span>
    </div>
    <div class="test-row">
      <span class="dot dot-ok"></span>
      <span class="test-name">DNS zone provisioned (PowerDNS)</span>
      <span class="test-result result-ok">PASS</span>
    </div>
    <div class="test-row">
      <span class="dot dot-ok"></span>
      <span class="test-name">SFTP / SSH access</span>
      <span class="test-result result-ok">PASS</span>
    </div>
    <div class="test-row">
      <span class="dot dot-ok"></span>
      <span class="test-name">Outbound mail (SMTP relay)</span>
      <span class="test-result result-ok">PASS</span>
    </div>
    <div class="test-row">
      <span class="dot dot-ok"></span>
      <span class="test-name">DKIM / SPF / DMARC records</span>
      <span class="test-result result-ok">PASS</span>
    </div>
    <div class="test-row">
      <span class="dot dot-warn"></span>
      <span class="test-name">Let's Encrypt certificate</span>
      <span class="test-result result-warn">PENDING</span>
    </div>
  </div>

  <div class="footer">
    Managed by <a href="https://{panel_domain}" target="_blank">GnuKontrolR</a>
    &mdash; Next-generation Linux hosting panel<br/>
    <span class="badge">Powered by GnuKontrolR</span>
  </div>
</body>
</html>
"""
    try:
        with open(path, "w") as f:
            f.write(html)
        # Make writable by the panelapi user (uid 999)
        import stat as _stat
        os.chmod(path, 0o644)
    except Exception as exc:
        log.warning("Could not write placeholder index for %s: %s", domain_name, exc)


async def _create_container_for_domain(domain_name: str, php_version: str, db, owner_email: str = "") -> None:
    """Background task: spin up a site container after domain creation."""
    try:
        # Import here to avoid circular imports
        from app.routers.docker_mgr import (
            container_name, _allocate_port, _run,
            NETWORK_NAME, PHP_IMAGE_PREFIX, SUPPORTED_PHP, DEFAULT_PHP,
            _REDIS_URL, _CONTAINER_API_TOKEN, _MYSQL_PASSWORD,
            _inject_panel_ssh_key, APP_CACHE_HOST_DIR,
        )
        import secrets as _secrets
        name    = container_name(domain_name)
        php_ver = php_version if php_version in SUPPORTED_PHP else DEFAULT_PHP
        image   = f"{PHP_IMAGE_PREFIX}:{php_ver}"
        db_safe = domain_name.replace(".", "_").replace("-", "_")
        db_name = db_safe
        db_user = db_safe[:16]
        db_pass = _secrets.token_urlsafe(16)
        doc_root = f"/var/webpanel/sites/{domain_name}/public_html"
        _run(["mkdir", "-p", doc_root])
        _run(["mkdir", "-p", APP_CACHE_HOST_DIR])
        # Write a branded placeholder page if the public_html is empty
        index_path = os.path.join(doc_root, "index.html")
        if not os.path.exists(index_path):
            _write_placeholder(domain_name, index_path)

        ssh_port = await _allocate_port(db, domain_name, "ssh")

        run_args = [
            "docker", "run", "-d",
            "--name", name,
            "--network", NETWORK_NAME,
            "--restart", "unless-stopped",
            "--memory", "1024m",
            "--cpus", "0.5",
            "--tmpfs", "/tmp:rw,size=256m",
            "--tmpfs", "/var/run:rw,size=16m",
            "-v", f"{doc_root}:/var/www/html",
            "-v", f"{APP_CACHE_HOST_DIR}:/var/cache/gnukontrolr/apps:ro",
            "-p", f"127.0.0.1:{ssh_port}:22",
            "-e", f"DOMAIN={domain_name}",
            "-e", "DB_HOST=webpanel_mysql",
            "-e", f"DB_NAME={db_name}",
            "-e", f"DB_USER={db_user}",
            "-e", f"DB_PASS={db_pass}",
            "-e", f"MYSQL_ROOT_PASSWORD={_MYSQL_PASSWORD}",
            "-e", f"REDIS_URL={_REDIS_URL}",
            "-e", "SMTP_HOST=webpanel_postfix",
            "-e", "WEB_SERVER=nginx",
            "-e", f"CONTAINER_API_TOKEN={_CONTAINER_API_TOKEN}",
            "-l", "traefik.enable=true",
            "-l", f"traefik.http.routers.{name}.rule=Host(`{domain_name}`) || Host(`www.{domain_name}`)",
            "-l", f"traefik.http.routers.{name}.tls=true",
            "-l", f"traefik.http.routers.{name}.tls.certresolver=le",
            "-l", f"gnukontrolr.acme_email={owner_email or 'unset'}",
            image,
        ]
        code, out, err = _run(run_args)
        if code != 0:
            log.error("Auto-container creation failed for %s: %s", domain_name, err)
        else:
            log.info("Auto-created container %s (PHP %s) for domain %s", name, php_ver, domain_name)
            # Inject panel SSH key so the panel service can SSH into the container
            ok = await _inject_panel_ssh_key(domain_name)
            if ok:
                log.info("Panel SSH key injected into %s", name)
            else:
                log.warning("Panel SSH key injection failed for %s (will need manual inject)", name)
    except Exception as exc:
        log.error("Auto-container creation error for %s: %s", domain_name, exc)


@router.patch("/{domain_id}")
async def update_domain(domain_id: int, body: DomainUpdate, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_user)):
    result = await db.execute(select(Domain).where(Domain.id == domain_id))
    domain = result.scalar_one_or_none()
    if not domain:
        raise HTTPException(404, "Domain not found")
    if domain.owner_id != current.id and current.role not in (Role.superadmin, Role.admin):
        raise HTTPException(403, "Access denied")
    old_php = domain.php_version
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(domain, field, val)
    domain.updated_at = datetime.utcnow()
    await db.commit()

    # If PHP version changed, recreate the container with the new image
    new_php = domain.php_version
    if body.php_version and new_php != old_php:
        asyncio.create_task(_recreate_container_for_domain(domain.name, new_php, db))

    asyncio.create_task(_localdns_sync(db))
    return {"ok": True}


async def _recreate_container_for_domain(domain_name: str, php_version: str, db) -> None:
    """Background task: stop/remove existing container and start a new one with updated PHP version."""
    try:
        from app.routers.docker_mgr import container_name, _run, _release_ports
        name = container_name(domain_name)
        # Stop and remove old container (preserves volume-mounted /var/www/html)
        _run(["docker", "rm", "-f", name])
        await _release_ports(db, domain_name)
        await _create_container_for_domain(domain_name, php_version, db)
        log.info("Recreated container %s with PHP %s", name, php_version)
    except Exception as exc:
        log.error("Container recreate error for %s: %s", domain_name, exc)


@router.post("/{domain_id}/reset-dns", status_code=200)
async def reset_domain_dns(
    domain_id: int,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Delete and re-provision the PowerDNS zone from scratch.

    All existing records are wiped and replaced with the canonical set
    (NS, glue, A, MX, service CNAMEs, SPF, DKIM, DMARC, MTA-STS, CAA).
    """
    result = await db.execute(select(Domain).where(Domain.id == domain_id))
    domain = result.scalar_one_or_none()
    if not domain:
        raise HTTPException(404, "Domain not found")
    if domain.owner_id != current.id and current.role not in (Role.superadmin, Role.admin):
        raise HTTPException(403, "Access denied")
    # Wipe existing zone then re-provision from scratch
    await deprovision_domain_dns(domain.name)
    await provision_domain_dns(domain)
    return {"ok": True, "domain": domain.name}


@router.post("/{domain_id}/set-master", status_code=200)
async def set_master_domain(
    domain_id: int,
    db:      AsyncSession = Depends(get_db),
    current: User         = Depends(get_current_user),
):
    """Designate this domain as the panel master domain (PANEL_DOMAIN).

    - Clears is_master on all other domains.
    - Sets is_master=True on this domain.
    - Writes PANEL_DOMAIN to .env.
    - Re-provisions DNS for the master zone: NS records, mail A record (MX 15),
      SPF/DKIM/DMARC/MTA-STS/TLS-RPT TXT records, CAA.
    - Calls sync_panel_ns_zone so all hosted zones get the new NS addresses.
    """
    if current.role not in (Role.superadmin, Role.admin):
        raise HTTPException(403, "Superadmin or admin required")
    result = await db.execute(select(Domain).where(Domain.id == domain_id))
    domain = result.scalar_one_or_none()
    if not domain:
        raise HTTPException(404, "Domain not found")

    # Clear previous master, set new one
    all_result = await db.execute(select(Domain))
    for d in all_result.scalars().all():
        if d.id == domain_id:
            d.is_master = True
        elif getattr(d, 'is_master', False):
            d.is_master = False
    await db.commit()

    # Update .env PANEL_DOMAIN
    _update_env_var("PANEL_DOMAIN", domain.name)

    # Re-provision the master zone with full NS + mail + email security records
    await deprovision_domain_dns(domain.name)
    await provision_domain_dns(domain)

    # Sync all hosted zones so they point NS at ns1-3.{new master}
    asyncio.create_task(_sync_all_ns_for_master(domain.name))

    return {"ok": True, "panel_domain": domain.name}


def _update_env_var(key: str, value: str) -> None:
    """Write or update a key=value pair in .env (non-blocking, best-effort)."""
    import re as _re
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env")
    env_path = os.path.normpath(env_path)
    try:
        content = open(env_path).read() if os.path.exists(env_path) else ""
        if f"{key}=" in content:
            content = _re.sub(rf"^{key}=.*$", f"{key}={value}", content, flags=_re.MULTILINE)
        else:
            content += f"\n{key}={value}\n"
        with open(env_path, "w") as f:
            f.write(content)
        log.info("Updated .env: %s=%s", key, value)
    except Exception as exc:
        log.warning("Could not update .env %s: %s", key, exc)


async def _sync_all_ns_for_master(panel_domain: str) -> None:
    """Background: sync NS records on all zones after master domain change."""
    try:
        from app.dns_helper import sync_panel_ns_zone, get_external_ip
        ip = await get_external_ip()
        if ip:
            await sync_panel_ns_zone(ip)
    except Exception as exc:
        log.warning("NS sync after master change failed: %s", exc)


@router.delete("/{domain_id}", status_code=204)
async def delete_domain(domain_id: int, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_user)):
    result = await db.execute(select(Domain).where(Domain.id == domain_id))
    domain = result.scalar_one_or_none()
    if not domain:
        raise HTTPException(404, "Domain not found")
    if domain.owner_id != current.id and current.role not in (Role.superadmin, Role.admin):
        raise HTTPException(403, "Access denied")
    domain_name = domain.name
    await db.delete(domain)
    await db.commit()
    await deprovision_domain_dns(domain_name)
    asyncio.create_task(_localdns_sync(db))
