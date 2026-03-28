"""Domain management endpoints."""
import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.database import get_db
from app.dns_helper import deprovision_domain_dns, provision_domain_dns
from app.models.domain import Domain, DomainType, DomainStatus
from app.models.user import User, Role
from app.auth import get_current_user

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


@router.get("/")
async def list_domains(db: AsyncSession = Depends(get_db), current: User = Depends(get_current_user)):
    if current.role in (Role.superadmin, Role.admin):
        result = await db.execute(select(Domain).order_by(Domain.id))
    else:
        result = await db.execute(select(Domain).where(Domain.owner_id == current.id))
    domains = result.scalars().all()
    return [
        {
            "id": d.id, "name": d.name, "owner_id": d.owner_id,
            "domain_type": d.domain_type, "status": d.status,
            "ssl_enabled": d.ssl_enabled, "ssl_expires": d.ssl_expires,
            "php_version": d.php_version, "doc_root": d.doc_root,
            "redirect_to": d.redirect_to, "created_at": d.created_at,
        }
        for d in domains
    ]


@router.post("/", status_code=201)
async def create_domain(body: DomainCreate, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_user)):
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
    )
    db.add(domain)
    await db.commit()
    await db.refresh(domain)
    await provision_domain_dns(domain)

    # Auto-create the site container in the background (non-blocking)
    asyncio.create_task(_create_container_for_domain(domain.name, domain.php_version or "8.2", db))

    return {"id": domain.id, "name": domain.name, "status": domain.status}


async def _create_container_for_domain(domain_name: str, php_version: str, db) -> None:
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
            "-l", f"traefik.http.routers.{name}.rule=Host(`{domain_name}`)",
            "-l", f"traefik.http.routers.{name}.tls=true",
            "-l", f"traefik.http.routers.{name}.tls.certresolver=le",
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
