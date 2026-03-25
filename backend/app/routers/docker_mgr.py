"""Docker container management — one isolated container per domain."""
import asyncio
import os
import random
import secrets
import socket
import subprocess
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth import require_admin, get_current_user
from app.database import get_db
from app.models.container_port import ContainerPort
from app.models.domain import Domain
from app.models.user import User, Role

# Redis URL as passed to customer containers — reads from the same env var
# the panel itself uses, so they always share the correct credentials.
_REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

router = APIRouter(prefix="/api/docker", tags=["docker"])

NETWORK_NAME   = "webpanel_net"
NGINX_PROXY    = "webpanel_proxy"
BASE_PHP_IMAGE = "webpanel/php-site:8.2"

# ── Per-service port ranges (unique host ports, never shared across containers)
# Container API (port 9000) is INTERNAL ONLY — never mapped to the host.
PORT_RANGES = {
    "ssh":       (10200, 14999),   # SFTP / SSH access
    "node":      (15000, 19999),   # Node.js direct access (optional expose)
    "websocket": (20000, 24999),   # WebSocket direct (optional)
}


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def _port_is_free(port: int) -> bool:
    """
    Return True only if the port is not bound by ANY process on the host —
    not just by our own containers.  Checks both IPv4 and IPv6 to catch
    dual-stack listeners.  SO_REUSEADDR is intentionally NOT set so we get a
    real conflict signal even against sockets that are in TIME_WAIT.
    """
    for family, addr in (
        (socket.AF_INET,  "0.0.0.0"),
        (socket.AF_INET6, "::"),
    ):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as s:
                s.bind((addr, port))
        except OSError:
            return False   # port already bound
    return True


def container_name(domain: str) -> str:
    return "site_" + domain.replace(".", "_").replace("-", "_")


def resolve_container(name_or_domain: str) -> str:
    """Return the actual Docker container name.
    If the value already looks like a container name (contains no dots and
    starts with a known prefix, or was passed as a raw container name from
    the list endpoint) return it as-is.  Otherwise treat it as a domain."""
    # Raw container names passed from the list page have no dots and are not
    # domain-like (e.g. "webpanel_api", "site_example_com").
    if "." not in name_or_domain:
        return name_or_domain
    return container_name(name_or_domain)


async def _allocate_port(db, domain: str, service: str) -> int:
    """
    Allocate a globally unique host port for a (domain, service) pair.

    Guarantees:
      - No two customers ever share the same host port for any service.
      - Re-entrant: returns the existing port if already allocated.
      - Race-safe: retries up to 10 times on DB unique-constraint collision,
        re-querying taken ports each attempt so the candidate pool shrinks.
      - Durable: persisted to DB — survives panel restarts.
    """
    # Return existing assignment without touching the DB again
    result = await db.execute(
        select(ContainerPort).where(
            ContainerPort.domain  == domain,
            ContainerPort.service == service,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing.host_port

    lo, hi = PORT_RANGES[service]
    loop = asyncio.get_running_loop()

    for attempt in range(10):
        # Re-query DB taken ports on every attempt so concurrent allocations
        # that committed between retries are excluded from the candidate pool.
        taken_result = await db.execute(
            select(ContainerPort.host_port).where(
                ContainerPort.host_port >= lo,
                ContainerPort.host_port <= hi,
            )
        )
        db_taken = {row[0] for row in taken_result.fetchall()}

        # Build the candidate list: DB-free ports in range, shuffled so we
        # don't hammer the same ports on every retry.
        candidates = list(set(range(lo, hi + 1)) - db_taken)
        if not candidates:
            raise RuntimeError(
                f"Port pool exhausted for service '{service}' "
                f"(range {lo}-{hi}, all {hi - lo + 1} slots recorded in DB)"
            )
        random.shuffle(candidates)

        # Walk candidates until we find one that is also free at the OS level.
        # _port_is_free does a real bind() — catches ports used by Docker,
        # system daemons, or anything else running on the host, not just our DB.
        port = None
        for candidate in candidates:
            free = await loop.run_in_executor(None, _port_is_free, candidate)
            if free:
                port = candidate
                break

        if port is None:
            # Every DB-free candidate was OS-busy — extremely unlikely but handle it.
            raise RuntimeError(
                f"All available ports for service '{service}' are in use by the OS "
                f"(range {lo}-{hi}). Check for external processes binding these ports."
            )

        db.add(ContainerPort(domain=domain, service=service, host_port=port))
        try:
            await db.commit()
            return port   # port is now exclusively ours in both DB and OS
        except IntegrityError:
            # Another request won the race and took this port between our OS
            # check and our commit.  Roll back and re-query on the next attempt.
            await db.rollback()

    raise RuntimeError(
        f"Could not allocate unique port for {domain}/{service} after 10 attempts"
    )


async def _release_ports(db, domain: str):
    """Free all port allocations for a domain on container deletion."""
    result = await db.execute(
        select(ContainerPort).where(ContainerPort.domain == domain)
    )
    for row in result.scalars().all():
        await db.delete(row)
    await db.commit()


async def _get_ports(db, domain: str) -> dict:
    """Return all port assignments for a domain as {service: host_port}."""
    result = await db.execute(
        select(ContainerPort).where(ContainerPort.domain == domain)
    )
    return {row.service: row.host_port for row in result.scalars().all()}


@router.get("/containers")
async def list_containers(_=Depends(require_admin)):
    code, out, err = _run([
        "docker", "ps", "-a",
        "--filter", f"network={NETWORK_NAME}",
        "--format", "{{json .}}",
    ])
    if code != 0:
        raise HTTPException(500, f"Docker error: {err}")
    containers = [json.loads(line) for line in out.splitlines() if line]
    return containers


@router.get("/containers/{domain}")
async def get_container(domain: str, db=Depends(get_db), current: User = Depends(get_current_user)):
    if current.role not in (Role.superadmin, Role.admin):
        result = await db.execute(select(Domain).where(Domain.name == domain, Domain.owner_id == current.id))
        if not result.scalar_one_or_none():
            raise HTTPException(403, "Access denied")
    name = container_name(domain)
    code, out, err = _run(["docker", "inspect", name])
    if code != 0:
        raise HTTPException(404, f"Container not found: {name}")
    ports = await _get_ports(db, domain)
    info  = json.loads(out)[0] if out else {}
    return {**info, "_port_assignments": ports}


class CreateContainerRequest(BaseModel):
    db_name:    Optional[str] = None
    db_user:    Optional[str] = None
    db_pass:    Optional[str] = None
    web_server: str   = "nginx"   # nginx | apache | lighttpd
    memory_mb:  int   = 512
    cpus:       float = 0.5
    enable_node: bool = False     # expose Node.js on unique host port


@router.post("/containers/{domain}/create")
async def create_domain_container(
    domain: str,
    body:   CreateContainerRequest = CreateContainerRequest(),
    db=Depends(get_db),
    _=Depends(require_admin),
):
    """
    Spin up a fresh isolated Docker container for a domain.
    Each service gets its own unique, persisted host port.
    Container API (port 9000) stays internal — never mapped to host.
    """
    name     = container_name(domain)
    doc_root = f"/var/webpanel/sites/{domain}/public_html"
    db_name  = body.db_name or domain.replace(".", "_").replace("-", "_")
    db_user  = body.db_user or db_name[:16]
    db_pass  = body.db_pass or secrets.token_urlsafe(16)

    # Create host directory for the site
    _run(["mkdir", "-p", doc_root])

    # Allocate unique host ports for all active services
    try:
        ssh_port = await _allocate_port(db, domain, "ssh")
        node_port = await _allocate_port(db, domain, "node") if body.enable_node else None
    except RuntimeError as e:
        raise HTTPException(503, str(e))

    # Build docker run arguments
    run_args = [
        "docker", "run", "-d",
        "--name", name,
        "--network", NETWORK_NAME,
        "--restart", "unless-stopped",
        "--memory", f"{body.memory_mb}m",
        "--cpus", str(body.cpus),
        "--tmpfs", "/tmp:rw,size=64m",
        "--tmpfs", "/var/run:rw,size=16m",
        "-v", f"{doc_root}:/var/www/html",
        # SSH — unique per container, loopback-only (Traefik not involved)
        "-p", f"127.0.0.1:{ssh_port}:22",
    ]

    # Node.js direct access (optional, loopback-only)
    if node_port:
        run_args += ["-p", f"127.0.0.1:{node_port}:3000"]

    run_args += [
        # Environment
        "-e", f"DOMAIN={domain}",
        "-e", f"DB_HOST=webpanel_mysql",
        "-e", f"DB_NAME={db_name}",
        "-e", f"DB_USER={db_user}",
        "-e", f"DB_PASS={db_pass}",
        "-e", f"REDIS_URL={_REDIS_URL}",
        "-e", f"SMTP_HOST=webpanel_postfix",
        "-e", f"WEB_SERVER={body.web_server}",
        # Traefik labels for auto-SSL routing (HTTP/HTTPS — no unique port needed)
        "-l", "traefik.enable=true",
        "-l", f"traefik.http.routers.{name}.rule=Host(`{domain}`)",
        "-l", f"traefik.http.routers.{name}.tls=true",
        "-l", f"traefik.http.routers.{name}.tls.certresolver=le",
        BASE_PHP_IMAGE,
    ]

    code, out, err = _run(run_args)
    if code != 0:
        await _release_ports(db, domain)
        raise HTTPException(500, f"Failed to create container: {err}")

    ports = await _get_ports(db, domain)
    return {
        "ok":          True,
        "container":   name,
        "domain":      domain,
        "ports":       ports,
        "ssh_command": f"ssh -p {ssh_port} www-data@YOUR_SERVER_IP",
        "db_name":     db_name,
        "db_user":     db_user,
        "db_pass":     db_pass,
        "note": (
            "Container API (port 9000) is internal-only on webpanel_net — "
            "not mapped to host by design."
        ),
    }


@router.get("/containers/{domain}/ports")
async def get_domain_ports(domain: str, db=Depends(get_db), _=Depends(get_current_user)):
    """Return all unique port assignments for a domain's container."""
    ports = await _get_ports(db, domain)
    if not ports:
        raise HTTPException(404, f"No port assignments found for {domain}")
    return {"domain": domain, "ports": ports}


class ContainerAction(BaseModel):
    action: str  # start | stop | restart | pause | unpause


@router.post("/containers/{domain}/action")
async def container_action(domain: str, body: ContainerAction, _=Depends(require_admin)):
    name = resolve_container(domain)
    if body.action not in ("start", "stop", "restart", "pause", "unpause", "kill"):
        raise HTTPException(400, "Invalid action")
    code, out, err = _run(["docker", body.action, name])
    if code != 0:
        raise HTTPException(500, err)
    return {"ok": True, "container": name, "action": body.action}


@router.delete("/containers/{domain}")
async def delete_domain_container(domain: str, db=Depends(get_db), _=Depends(require_admin)):
    name = container_name(domain)
    _run(["docker", "stop", name])
    code, out, err = _run(["docker", "rm", "-f", name])
    if code != 0:
        raise HTTPException(500, err)
    # Release all port allocations for this domain
    await _release_ports(db, domain)
    return {"ok": True, "removed": name}


@router.get("/containers/{domain}/logs")
async def container_logs(domain: str, tail: int = 100, _=Depends(require_admin)):
    tail = min(max(tail, 1), 1000)
    name = resolve_container(domain)
    code, out, err = _run(["docker", "logs", "--tail", str(tail), name])
    return {"logs": out, "stderr": err}


@router.get("/containers/{domain}/stats")
async def container_stats(domain: str, db=Depends(get_db), current: User = Depends(get_current_user)):
    if current.role not in (Role.superadmin, Role.admin):
        result = await db.execute(select(Domain).where(Domain.name == domain, Domain.owner_id == current.id))
        if not result.scalar_one_or_none():
            raise HTTPException(403, "Access denied")
    name = resolve_container(domain)
    code, out, err = _run([
        "docker", "stats", "--no-stream", "--format",
        "{{json .}}", name,
    ])
    if code != 0:
        raise HTTPException(500, err)
    return json.loads(out) if out else {}
