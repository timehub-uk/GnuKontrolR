"""Docker container management — one isolated container per domain."""
import asyncio
import random
import secrets
import subprocess
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.auth import require_admin, get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/docker", tags=["docker"])

NETWORK_NAME   = "webpanel_net"
NGINX_PROXY    = "webpanel_proxy"
BASE_PHP_IMAGE = "webpanel/php-site:8.2"

# SSH port range for customer containers
SSH_PORT_MIN = 10200
SSH_PORT_MAX = 19999

# Track used SSH ports in memory (in production, persist in DB)
_used_ssh_ports: set[int] = set()


def _allocate_ssh_port() -> int:
    """Pick a random unused SSH port from the customer SSH range."""
    available = set(range(SSH_PORT_MIN, SSH_PORT_MAX + 1)) - _used_ssh_ports
    if not available:
        raise RuntimeError("No SSH ports available")
    port = random.choice(list(available))
    _used_ssh_ports.add(port)
    return port


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def container_name(domain: str) -> str:
    return "site_" + domain.replace(".", "_").replace("-", "_")


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
async def get_container(domain: str, _=Depends(get_current_user)):
    name = container_name(domain)
    code, out, err = _run(["docker", "inspect", name])
    if code != 0:
        raise HTTPException(404, f"Container not found: {name}")
    return json.loads(out)[0] if out else {}


class CreateContainerRequest(BaseModel):
    db_name: Optional[str] = None
    db_user: Optional[str] = None
    db_pass: Optional[str] = None
    web_server: str = "nginx"      # nginx | apache | lighttpd
    memory_mb: int = 512
    cpus: float = 0.5


@router.post("/containers/{domain}/create")
async def create_domain_container(
    domain: str,
    body: CreateContainerRequest = CreateContainerRequest(),
    _=Depends(require_admin),
):
    """Spin up a fresh isolated Docker container for a domain with SSH access."""
    name     = container_name(domain)
    doc_root = f"/var/webpanel/sites/{domain}/public_html"
    db_name  = body.db_name or domain.replace(".", "_").replace("-", "_")
    db_user  = body.db_user or (db_name[:16])
    db_pass  = body.db_pass or secrets.token_urlsafe(16)

    # Create host directory for the site
    _run(["mkdir", "-p", doc_root])

    # Allocate a unique SSH port
    try:
        ssh_port = _allocate_ssh_port()
    except RuntimeError:
        raise HTTPException(503, "SSH port pool exhausted")

    code, out, err = _run([
        "docker", "run", "-d",
        "--name", name,
        "--network", NETWORK_NAME,
        "--restart", "unless-stopped",
        "--memory", f"{body.memory_mb}m",
        "--cpus", str(body.cpus),
        "--tmpfs", "/tmp:rw,size=64m",
        "--tmpfs", "/var/run:rw,size=16m",
        "-v", f"{doc_root}:/var/www/html",
        # Expose SSH on a private host port
        "-p", f"127.0.0.1:{ssh_port}:22",
        # Environment
        "-e", f"DOMAIN={domain}",
        "-e", f"DB_HOST=webpanel_mysql",
        "-e", f"DB_NAME={db_name}",
        "-e", f"DB_USER={db_user}",
        "-e", f"DB_PASS={db_pass}",
        "-e", f"REDIS_URL=redis://:changeme_redis@webpanel_redis:6379/0",
        "-e", f"SMTP_HOST=webpanel_postfix",
        "-e", f"WEB_SERVER={body.web_server}",
        # Traefik labels for auto-SSL
        "-l", "traefik.enable=true",
        "-l", f"traefik.http.routers.{name}.rule=Host(`{domain}`)",
        "-l", f"traefik.http.routers.{name}.tls=true",
        "-l", f"traefik.http.routers.{name}.tls.certresolver=le",
        BASE_PHP_IMAGE,
    ])
    if code != 0:
        _used_ssh_ports.discard(ssh_port)
        raise HTTPException(500, f"Failed to create container: {err}")

    return {
        "ok": True,
        "container": name,
        "domain": domain,
        "ssh_port": ssh_port,
        "ssh_host": "127.0.0.1",
        "ssh_command": f"ssh -p {ssh_port} www-data@YOUR_SERVER_IP",
        "db_name": db_name,
        "db_user": db_user,
        "db_pass": db_pass,
    }


class ContainerAction(BaseModel):
    action: str  # start | stop | restart | pause | unpause


@router.post("/containers/{domain}/action")
async def container_action(domain: str, body: ContainerAction, _=Depends(require_admin)):
    name = container_name(domain)
    if body.action not in ("start", "stop", "restart", "pause", "unpause", "kill"):
        raise HTTPException(400, "Invalid action")
    code, out, err = _run(["docker", body.action, name])
    if code != 0:
        raise HTTPException(500, err)
    return {"ok": True, "container": name, "action": body.action}


@router.delete("/containers/{domain}")
async def delete_domain_container(domain: str, _=Depends(require_admin)):
    name = container_name(domain)
    _run(["docker", "stop", name])
    code, out, err = _run(["docker", "rm", "-f", name])
    if code != 0:
        raise HTTPException(500, err)
    return {"ok": True, "removed": name}


@router.get("/containers/{domain}/logs")
async def container_logs(domain: str, tail: int = 100, _=Depends(require_admin)):
    name = container_name(domain)
    code, out, err = _run(["docker", "logs", "--tail", str(tail), name])
    return {"logs": out, "stderr": err}


@router.get("/containers/{domain}/stats")
async def container_stats(domain: str, _=Depends(get_current_user)):
    name = container_name(domain)
    code, out, err = _run([
        "docker", "stats", "--no-stream", "--format",
        "{{json .}}", name,
    ])
    if code != 0:
        raise HTTPException(500, err)
    return json.loads(out) if out else {}
