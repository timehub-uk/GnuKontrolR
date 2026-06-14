"""Docker container management — one isolated container per domain."""
import asyncio
import os
import random
import secrets
import re
import socket
import subprocess
import json
import httpx
from app.http_client import panel_client
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth import require_admin, get_current_user
from app.database import get_db
from app.dns_helper import deprovision_domain_dns, provision_domain_dns
from app.models.container_port import ContainerPort
from app.models.domain import Domain
from app.models.user import User, Role
from app.docker_client import (
    list_images, list_containers as dc_list_containers,
    inspect_container, create_container, start_container,
    stop_container, restart_container, pause_container, unpause_container,
    kill_container, remove_container, container_logs as dc_container_logs,
    container_stats as dc_container_stats, all_containers_stats,
)

# Redis URL as passed to customer containers — reads from the same env var
# the panel itself uses, so they always share the correct credentials.
_REDIS_URL             = os.environ.get("REDIS_URL", "redis://redis:6379/0")
_CONTAINER_API_TOKEN   = os.environ.get("CONTAINER_API_TOKEN", "")
_MYSQL_PASSWORD        = os.environ.get("MYSQL_PASSWORD", "")

# ── Panel SSH keypair ─────────────────────────────────────────────────────────
# The panel service has its own ECDSA keypair stored on the host.
# On first run it is auto-generated. The public key is injected into every
# domain container so the panel service can SSH in as gnukontrolr-admin.
_PANEL_KEY_DIR  = "/var/webpanel/panel_ssh"
_PANEL_KEY_FILE = f"{_PANEL_KEY_DIR}/id_ecdsa"
_PANEL_PUB_FILE = f"{_PANEL_KEY_DIR}/id_ecdsa.pub"


def _ensure_panel_ssh_key() -> str:
    """Generate the panel's ECDSA keypair on first call. Return the public key."""
    import stat
    os.makedirs(_PANEL_KEY_DIR, mode=0o700, exist_ok=True)
    if not os.path.exists(_PANEL_KEY_FILE):
        subprocess.run(
            ["ssh-keygen", "-t", "ecdsa", "-b", "521",
             "-f", _PANEL_KEY_FILE, "-N", "", "-C", "gnukontrolr-panel"],
            check=True, capture_output=True,
        )
        os.chmod(_PANEL_KEY_FILE, 0o600)
    with open(_PANEL_PUB_FILE) as fh:
        return fh.read().strip()


async def _inject_panel_ssh_key(domain: str, token: str | None = None) -> bool:
    """Push the panel's public key into the domain container. Returns True on success.

    Args:
        domain: the domain name for the target container.
        token:  the per-domain container API token (from the domain record).
                If None, looked up from the database.
    """
    try:
        pub_key = _ensure_panel_ssh_key()
    except Exception:
        return False

    # Resolve token from DB if not provided
    if not token:
        from app.database import AsyncSessionLocal as _AsyncSessionLocal
        async with _AsyncSessionLocal() as _db:
            _result = await _db.execute(select(Domain).where(Domain.name == domain))
            _dom = _result.scalar_one_or_none()
            if _dom:
                token = _dom.container_api_token or ""

    url = _container_api_url_direct(domain, "/admin/ssh-key")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    # NOTE: Do NOT use panel_client() here — it HMAC-signs requests with the
    # global CONTAINER_API_TOKEN env var, while the container verifies against
    # its per-domain token. Use a plain AsyncClient with the per-domain token.
    for attempt in range(6):  # container may still be initialising
        try:
            async with httpx.AsyncClient(timeout=10, verify=False) as client:
                r = await client.post(url, json={"public_key": pub_key}, headers=headers)
                if r.status_code == 200:
                    return True
        except Exception:
            pass
        await asyncio.sleep(5)
    return False


def _container_api_url_direct(domain: str, path: str) -> str:
    name = container_name(domain)
    return f"https://{name}:9000{path}"

router = APIRouter(prefix="/api/docker", tags=["docker"])

NETWORK_NAME      = "webpanel_net"
NGINX_PROXY       = "webpanel_proxy"
PHP_IMAGE_PREFIX  = "webpanel/php-site"
SUPPORTED_PHP     = {"8.1", "8.2", "8.3"}
DEFAULT_PHP       = "8.2"

# Shared read-only marketplace app cache mounted into every site container.
# Panel downloads/manages this; containers read from it without needing internet.
APP_CACHE_HOST_DIR = "/var/webpanel/app-cache"

# ── Per-service port ranges (unique host ports, never shared across containers)
# Container API (port 9000) is INTERNAL ONLY — never mapped to the host.
PORT_RANGES = {
    "ssh":       (10200, 14999),   # SFTP / SSH access
    "node":      (15000, 19999),   # Node.js direct access (optional expose)
    "websocket": (20000, 24999),   # WebSocket direct (optional)
}


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """Run a host command (mkdir, cp, etc.) with arg validation."""
    for arg in cmd:
        if not re.match(r"^[a-zA-Z0-9_./\-:={}\[\]\" %*]+$", arg):
            raise ValueError(f"Dangerous argument in command: {arg}")
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
        (socket.AF_INET,  "127.0.0.1"),
        (socket.AF_INET6, "::1"),
    ):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as s:
                s.bind((addr, port))
        except OSError:
            return False   # port already bound
    return True


def container_name(domain: str) -> str:
    safe = re.sub(r'[^a-zA-Z0-9_.-]', '_', domain)
    return "site_" + safe.replace(".", "_").replace("-", "_")


def resolve_container(name_or_domain: str) -> str:
    """Return the actual Docker container name.
    If the value already looks like a container name (contains no dots and
    starts with a known prefix, or was passed as a raw container name from
    the list endpoint) return it as-is.  Otherwise treat it as a domain."""
    if not re.match(r"^[a-zA-Z0-9_.-]+$", name_or_domain):
        raise ValueError("Invalid container name")
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


_PHP_UPDATE_SCRIPT = os.path.join(
    os.path.dirname(__file__),
    "../../../../docker/site-template/check-php-updates.sh"
)


@router.get("/php-versions")
async def list_php_versions(_=Depends(require_admin)):
    """Return locally built PHP versions and the current SUPPORTED_PHP set."""
    try:
        images = await list_images("webpanel/php-site")
        local = sorted(set(
            tag for img in images
            for tag in img.get("RepoTags", [])
            if ":" in tag and tag.split(":")[1][0].isdigit()
        ))
    except Exception:
        local = []
    return {"built": local, "supported": sorted(SUPPORTED_PHP)}


@router.post("/php-versions/check-updates")
async def check_php_updates(dry_run: bool = False, _=Depends(require_admin)):
    """
    Detect new PHP FPM versions on Docker Hub and build images for any not yet built.
    Runs check-php-updates.sh in the background — returns immediately with a job token.
    Poll GET /api/docker/php-versions to see newly built versions appear.
    """
    script = os.path.realpath(_PHP_UPDATE_SCRIPT)
    if not os.path.isfile(script):
        raise HTTPException(500, f"Update script not found: {script}")
    args = ["/bin/bash", script]
    if dry_run:
        args.append("--dry-run")
    # Run detached — building can take many minutes
    proc = subprocess.Popen(
        args,
        stdout=open("/var/log/gnukontrolr-php-update.log", "a"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return {
        "ok":    True,
        "pid":   proc.pid,
        "log":   "/var/log/gnukontrolr-php-update.log",
        "dry_run": dry_run,
        "note":  "Build running in background. Poll GET /api/docker/php-versions for results.",
    }


@router.post("/php-versions/build")
async def build_php_version(version: str, _=Depends(require_admin)):
    """Force-build a specific PHP version image (e.g. '8.4')."""
    import re
    if not re.fullmatch(r"\d{1,3}\.\d{1,3}", version):
        raise HTTPException(400, "Version must be in X.Y format (e.g. 8.4)")
    script = os.path.realpath(_PHP_UPDATE_SCRIPT)
    if not os.path.isfile(script):
        raise HTTPException(500, f"Update script not found: {script}")
    proc = subprocess.Popen(
        ["/bin/bash", script, "--force", version],
        stdout=open("/var/log/gnukontrolr-php-update.log", "a"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return {
        "ok":     True,
        "pid":    proc.pid,
        "version": version,
        "log":    "/var/log/gnukontrolr-php-update.log",
        "note":   f"Building webpanel/php-site:{version} in background.",
    }


@router.get("/containers")
async def list_containers(_=Depends(require_admin)):
    try:
        containers = await dc_list_containers(all=True, filters={"network": [NETWORK_NAME]})
    except Exception as e:
        raise HTTPException(500, f"Docker error: {e}")
    return containers


@router.get("/containers/{domain}")
async def get_container(domain: str, db=Depends(get_db), current: User = Depends(get_current_user)):
    if not re.match(r"^[a-zA-Z0-9.-]+$", domain):
        raise HTTPException(400, "Invalid domain name")
    if current.role not in (Role.superadmin, Role.admin):
        result = await db.execute(select(Domain).where(Domain.name == domain, Domain.owner_id == current.id))
        if not result.scalar_one_or_none():
            raise HTTPException(403, "Access denied")
    name = container_name(domain)
    try:
        info = await inspect_container(name)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(404, f"Container not found: {name}")
        raise HTTPException(500, f"Docker error: {e}")
    except Exception as e:
        raise HTTPException(500, f"Docker error: {e}")
    ports = await _get_ports(db, domain)
    return {**info, "_port_assignments": ports}


class CreateContainerRequest(BaseModel):
    db_name:     Optional[str]   = None
    db_user:     Optional[str]   = None
    db_pass:     Optional[str]   = None
    web_server:  str             = "nginx"   # nginx | apache | lighttpd
    memory_mb:   int             = 1024
    cpus:        float           = 0.5
    enable_node: bool            = False     # expose Node.js on unique host port
    php_version: Optional[str]   = None      # override domain's php_version


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
    Uses the Docker HTTP API via docker-api-proxy (no docker.sock).
    """
    name     = container_name(domain)
    doc_root = f"/var/webpanel/sites/{domain}/public_html"
    db_name  = body.db_name or domain.replace(".", "_").replace("-", "_")
    db_user  = body.db_user or db_name[:16]
    db_pass  = body.db_pass or secrets.token_urlsafe(16)

    # Resolve PHP version: body override → domain record → default
    php_ver = body.php_version
    if not php_ver:
        domain_row = await db.scalar(select(Domain).where(Domain.name == domain))
        php_ver = domain_row.php_version if domain_row else DEFAULT_PHP
    if php_ver not in SUPPORTED_PHP:
        php_ver = DEFAULT_PHP
    image = f"{PHP_IMAGE_PREFIX}:{php_ver}"

    # Create host directories
    _run(["mkdir", "-p", doc_root])
    _run(["mkdir", "-p", APP_CACHE_HOST_DIR])

    # Allocate unique host ports for all active services
    try:
        ssh_port = await _allocate_port(db, domain, "ssh")
        node_port = await _allocate_port(db, domain, "node") if body.enable_node else None
    except RuntimeError as e:
        raise HTTPException(503, str(e))

    # Build containers-stats port bindings
    port_bindings = {
        "22/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(ssh_port)}],
    }
    exposed_ports = {
        "22/tcp": {},
        "9000/tcp": {},  # container API — internal only
    }
    if node_port:
        port_bindings["3000/tcp"] = [{"HostIp": "127.0.0.1", "HostPort": str(node_port)}]
        exposed_ports["3000/tcp"] = {}

    # H9: Generate per-domain container API token and store on the domain record
    import secrets as _secrets
    domain_token = _secrets.token_urlsafe(32)
    _dom_result = await db.execute(select(Domain).where(Domain.name == domain))
    _dom_row = _dom_result.scalar_one_or_none()
    if _dom_row:
        _dom_row.container_api_token = domain_token
        await db.commit()

    # Environment variables
    env = [
        f"DOMAIN={domain}",
        f"DB_HOST=webpanel_mysql",
        f"DB_NAME={db_name}",
        f"DB_USER={db_user}",
        f"DB_PASS={db_pass}",
        f"MYSQL_ROOT_PASSWORD={_MYSQL_PASSWORD}",
        f"REDIS_URL={_REDIS_URL}",
        f"SMTP_HOST=webpanel_postfix",
        f"WEB_SERVER={body.web_server}",
        f"CONTAINER_API_TOKEN={domain_token}",
    ]

    # Labels for Traefik auto-routing
    labels = {
        "traefik.enable": "true",
        f"traefik.http.routers.{name}.rule": f"Host(`{domain}`)",
        f"traefik.http.routers.{name}.tls": "true",
        f"traefik.http.routers.{name}.tls.certresolver": "le",
    }

    # Volumes
    volumes = [
        f"{doc_root}:/var/www/html",
        f"{APP_CACHE_HOST_DIR}:/var/cache/gnukontrolr/apps:rw",
    ]

    # Tmpfs mounts
    tmpfs = {
        "/tmp": "rw,size=256m",
        "/var/run": "rw,size=16m",
    }

    # Create the container via Docker HTTP API
    try:
        result = await create_container(
            name=name,
            image=image,
            network=NETWORK_NAME,
            env=env,
            volumes=volumes,
            labels=labels,
            port_bindings=port_bindings,
            exposed_ports=exposed_ports,
            mem_limit=f"{body.memory_mb}m",
            cpus=body.cpus,
            tmpfs=tmpfs,
            host_config={
                "RestartPolicy": {"Name": "unless-stopped"},
            },
        )
        await start_container(name)
    except Exception as e:
        await _release_ports(db, domain)
        raise HTTPException(500, f"Failed to create container: {e}")

    # Provision DNS: create zone + A records in PowerDNS.
    domain_row = await db.scalar(select(Domain).where(Domain.name == domain))
    if domain_row:
        await provision_domain_dns(domain_row)

    # Inject panel SSH key in background (container needs a few seconds to start up)
    asyncio.create_task(_inject_panel_ssh_key(domain, token=domain_token))

    ports = await _get_ports(db, domain)
    return {
        "ok":          True,
        "container":   name,
        "domain":      domain,
        "ports":       ports,
        "ssh_command": f"ssh -p {ssh_port} www-data@YOUR_SERVER_IP",
        "admin_ssh":   f"ssh -p {ssh_port} -i {_PANEL_KEY_FILE} gnukontrolr-admin@YOUR_SERVER_IP",
        "db_name":     db_name,
        "db_user":     db_user,
        "db_pass":     db_pass,
        "note": (
            "Container API (port 9000) is internal-only on webpanel_net — "
            "not mapped to host by design."
        ),
    }


@router.get("/panel-ssh-key")
async def get_panel_ssh_key(_=Depends(require_admin)):
    """Return the panel service's SSH public key (auto-generated on first call)."""
    try:
        pub = _ensure_panel_ssh_key()
    except Exception as exc:
        raise HTTPException(500, f"Failed to generate panel SSH key: {exc}")
    return {"public_key": pub, "key_file": _PANEL_KEY_FILE}


@router.post("/containers/{domain}/inject-panel-key")
async def inject_panel_key(domain: str, _=Depends(require_admin)):
    """
    Inject the panel's SSH public key into an existing domain container.
    Use this for containers created before panel key support was added.
    """
    ok = await _inject_panel_ssh_key(domain)
    if not ok:
        raise HTTPException(503, "Could not inject key — is the container running?")
    ssh_port = None
    try:
        import sqlite3 as _s
    except ImportError:
        pass
    return {
        "ok": True,
        "domain": domain,
        "admin_ssh": f"ssh -i {_PANEL_KEY_FILE} gnukontrolr-admin@<server_ip> -p <ssh_port>",
        "tip": "Get the SSH port via GET /api/docker/containers/{domain}/ports",
    }


@router.get("/containers/{domain}/ssh-info")
async def container_ssh_info(domain: str, db=Depends(get_db), _=Depends(require_admin)):
    """Return SSH connection details for a domain container (both customer and admin)."""
    ports = await _get_ports(db, domain)
    ssh_port = ports.get("ssh")
    if not ssh_port:
        raise HTTPException(404, "No SSH port allocated for this container")
    return {
        "domain":       domain,
        "ssh_port":     ssh_port,
        "customer_ssh": f"ssh -p {ssh_port} webuser@YOUR_SERVER_IP",
        "customer_sftp":f"sftp -P {ssh_port} www-data@YOUR_SERVER_IP",
        "admin_ssh":    f"ssh -p {ssh_port} -i {_PANEL_KEY_FILE} gnukontrolr-admin@YOUR_SERVER_IP",
        "panel_key":    _PANEL_PUB_FILE,
        "note":         "webuser = domain customer (real shell). www-data = SFTP-only (chrooted). gnukontrolr-admin = superadmin.",
    }


class WebUserSshKeyRequest(BaseModel):
    public_key: str


@router.post("/containers/{domain}/webuser-ssh-key")
async def set_webuser_ssh_key(domain: str, body: WebUserSshKeyRequest, db=Depends(get_db), current: User = Depends(get_current_user)):
    """
    Set the customer's SSH public key for the domain container (webuser account).
    Domain owner or admin can call this.
    """
    if current.role not in (Role.superadmin, Role.admin):
        result = await db.execute(select(Domain).where(Domain.name == domain, Domain.owner_id == current.id))
        if not result.scalar_one_or_none():
            raise HTTPException(403, "Access denied")
    url = _container_api_url_direct(domain, "/webuser/ssh-key")
    headers = {"Authorization": f"Bearer {_CONTAINER_API_TOKEN}"} if _CONTAINER_API_TOKEN else {}
    async with panel_client(timeout=15, verify=False) as client:
        try:
            r = await client.post(url, json={"public_key": body.public_key}, headers=headers)
            r.raise_for_status()
        except httpx.ConnectError:
            raise HTTPException(503, "Container unreachable — is it running?")
        except httpx.HTTPStatusError as exc:
            raise HTTPException(exc.response.status_code, exc.response.text)
        except Exception as exc:
            raise HTTPException(500, str(exc))
    ports = await _get_ports(db, domain)
    ssh_port = ports.get("ssh", "???")
    return {
        "ok": True,
        "domain": domain,
        "user": "webuser",
        "ssh_command": f"ssh -p {ssh_port} webuser@YOUR_SERVER_IP",
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
    if not re.match(r"^[a-zA-Z0-9.-]+$", domain):
        raise HTTPException(400, "Invalid domain name")
    name = resolve_container(domain)
    action_map = {
        "start": start_container,
        "stop": stop_container,
        "restart": restart_container,
        "pause": pause_container,
        "unpause": unpause_container,
        "kill": kill_container,
    }
    action_fn = action_map.get(body.action)
    if not action_fn:
        raise HTTPException(400, "Invalid action")
    try:
        await action_fn(name)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(404, f"Container not found: {name}")
        raise HTTPException(500, f"Docker error: {e}")
    except Exception as e:
        raise HTTPException(500, f"Docker error: {e}")
    return {"ok": True, "container": name, "action": body.action}


@router.delete("/containers/{domain}")
async def delete_domain_container(domain: str, db=Depends(get_db), _=Depends(require_admin)):
    if not re.match(r"^[a-zA-Z0-9.-]+$", domain):
        raise HTTPException(400, "Invalid domain name")
    name = container_name(domain)
    try:
        await stop_container(name)
    except Exception:
        pass  # may already be stopped
    try:
        await remove_container(name, force=True)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(404, f"Container not found: {name}")
        raise HTTPException(500, f"Docker error: {e}")
    except Exception as e:
        raise HTTPException(500, f"Docker error: {e}")
    # Release all port allocations for this domain
    await _release_ports(db, domain)
    # Remove DNS zone from PowerDNS.
    await deprovision_domain_dns(domain)
    return {"ok": True, "removed": name}


@router.get("/containers/{domain}/logs")
async def container_logs(domain: str, tail: int = 100, _=Depends(require_admin)):
    if not re.match(r"^[a-zA-Z0-9.-]+$", domain):
        raise HTTPException(400, "Invalid domain name")
    tail = min(max(tail, 1), 1000)
    name = resolve_container(domain)
    try:
        result = await dc_container_logs(name, tail=tail)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(404, f"Container not found: {name}")
        raise HTTPException(500, f"Docker error: {e}")
    except Exception as e:
        raise HTTPException(500, f"Docker error: {e}")
    return {"logs": result.get("stdout", ""), "stderr": result.get("stderr", "")}


class AdminSshKeyRequest(BaseModel):
    public_key: str


_CONTAINER_API_PORT = 9000
_TLS_VERIFY = False   # self-signed cert on internal network


def _container_api_url(domain: str, path: str) -> str:
    name = container_name(domain)
    return f"https://{name}:{_CONTAINER_API_PORT}{path}"


@router.post("/containers/{domain}/admin-ssh-key", status_code=200)
async def inject_admin_ssh_key(domain: str, body: AdminSshKeyRequest, _=Depends(require_admin)):
    """
    Inject a superadmin SSH public key into the domain container's
    gnukontrolr-admin user.  After this the superadmin can SSH directly
    into the container with full bash shell + TCP-forwarding rights.

    Returns the SSH command to use (port = allocated host SSH port for the container).
    """
    url = _container_api_url(domain, "/admin/ssh-key")
    headers = {"Authorization": f"Bearer {_CONTAINER_API_TOKEN}"} if _CONTAINER_API_TOKEN else {}
    async with panel_client(timeout=15, verify=_TLS_VERIFY) as client:
        try:
            r = await client.post(url, json={"public_key": body.public_key}, headers=headers)
            r.raise_for_status()
        except httpx.ConnectError:
            raise HTTPException(503, "Container unreachable — is it running?")
        except httpx.HTTPStatusError as exc:
            raise HTTPException(exc.response.status_code, exc.response.text)
        except Exception as exc:
            raise HTTPException(500, str(exc))

    # Return the SSH connection command using the host-mapped SSH port
    return {
        "ok": True,
        "domain": domain,
        "user": "gnukontrolr-admin",
        "note": (
            "Use `GET /api/docker/containers/{domain}/ports` to find the host SSH port, "
            "then: ssh -p <port> gnukontrolr-admin@YOUR_SERVER_IP"
        ),
    }


@router.delete("/containers/{domain}/admin-ssh-key", status_code=200)
async def revoke_admin_ssh_key(domain: str, _=Depends(require_admin)):
    """Remove the superadmin SSH key from a domain container."""
    url = _container_api_url(domain, "/admin/ssh-key")
    headers = {"Authorization": f"Bearer {_CONTAINER_API_TOKEN}"} if _CONTAINER_API_TOKEN else {}
    async with panel_client(timeout=10, verify=_TLS_VERIFY) as client:
        try:
            r = await client.delete(url, headers=headers)
            r.raise_for_status()
        except httpx.ConnectError:
            raise HTTPException(503, "Container unreachable")
        except Exception as exc:
            raise HTTPException(500, str(exc))
    return {"ok": True}


@router.get("/containers/{domain}/stats")
async def container_stats(domain: str, db=Depends(get_db), current: User = Depends(get_current_user)):
    if not re.match(r"^[a-zA-Z0-9.-]+$", domain):
        raise HTTPException(400, "Invalid domain name")
    if current.role not in (Role.superadmin, Role.admin):
        result = await db.execute(select(Domain).where(Domain.name == domain, Domain.owner_id == current.id))
        if not result.scalar_one_or_none():
            raise HTTPException(403, "Access denied")
    name = resolve_container(domain)
    try:
        stats = await dc_container_stats(name)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(404, f"Container not found: {name}")
        raise HTTPException(500, f"Docker error: {e}")
    except Exception as e:
        raise HTTPException(500, f"Docker error: {e}")
    return stats


async def _collect_all_stats() -> dict:
    """Returns stats keyed by container name via the HTTP API."""
    try:
        return await all_containers_stats()
    except Exception:
        return {}


@router.get("/stats")
async def all_container_stats(_=Depends(require_admin)):
    """
    Return CPU / memory stats for every running container in one call.
    Uses the Docker HTTP API to gather stats.
    """
    return await _collect_all_stats()
