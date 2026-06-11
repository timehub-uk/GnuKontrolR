"""
Secondary (optional) services — add-on containers the admin can discover
and deploy through the services page.  Each has a config modal with setup
fields, then runs as a Docker container on webpanel_net.
"""
import asyncio
import json
import logging
import os
import secrets
import subprocess
import string
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.database import get_db
from app.models.secondary_service import SecondaryService

log = logging.getLogger("webpanel")

router = APIRouter(prefix="/api/server/secondary", tags=["secondary-services"])

# ────────────────────────────────────────────────────────────────────────────
# Secondary services catalogue  (hardcoded — extend here to add more)
# ────────────────────────────────────────────────────────────────────────────

SECONDARY_CATALOGUE: dict[str, dict] = {
    "portainer": {
        "name": "Portainer",
        "description": "Docker container management UI. Manage containers, images, volumes, networks, and more through a web dashboard.",
        "icon": "🐳",
        "category": "management",
        "docker_image": "portainer/portainer-ce:latest",
        "default_container_name": "webpanel_portainer",
        "config_schema": [
            {"key": "port", "label": "Web UI Port", "type": "number", "default": 9443, "required": True,
             "description": "HTTPS port for the Portainer dashboard"},
            {"key": "password", "label": "Admin Password", "type": "password", "required": True,
             "description": "Initial admin password for Portainer (can be changed later)"},
        ],
        "web_port": "{{port}}",
        "description_full": "Portainer is a lightweight service management UI that allows you to easily manage your Docker containers, images, networks, and volumes.",
    },
    "minio": {
        "name": "MinIO",
        "description": "S3-compatible object storage. Ideal for backups, file hosting, and application data storage.",
        "icon": "📦",
        "category": "storage",
        "docker_image": "minio/minio:latest",
        "default_container_name": "webpanel_minio",
        "config_schema": [
            {"key": "port_api", "label": "API Port", "type": "number", "default": 9000, "required": True,
             "description": "S3-compatible API port"},
            {"key": "port_console", "label": "Console Port", "type": "number", "default": 9001, "required": True,
             "description": "Web management console port"},
            {"key": "root_user", "label": "Root Username", "type": "text", "default": "minioadmin", "required": True,
             "description": "MinIO root user (min 3 characters)"},
            {"key": "root_password", "label": "Root Password", "type": "password", "required": True,
             "description": "MinIO root password (min 8 characters)"},
        ],
        "web_port": "{{port_console}}",
        "description_full": "MinIO is a high-performance, S3-compatible object store. Use it for storing backups, static assets, logs, or any unstructured data.",
    },
    "n8n": {
        "name": "n8n",
        "description": "Workflow automation platform. Connect apps and automate tasks with a visual editor.",
        "icon": "⚡",
        "category": "automation",
        "docker_image": "n8nio/n8n:latest",
        "default_container_name": "webpanel_n8n",
        "config_schema": [
            {"key": "port", "label": "Web UI Port", "type": "number", "default": 5678, "required": True,
             "description": "Port for the n8n web interface"},
            {"key": "encryption_key", "label": "Encryption Key", "type": "password", "required": True,
             "description": "Used to encrypt credentials in n8n database"},
            {"key": "timezone", "label": "Timezone", "type": "text", "default": "UTC", "required": False,
             "description": "Server timezone (e.g. Europe/London, America/New_York)"},
        ],
        "web_port": "{{port}}",
        "description_full": "n8n is a workflow automation tool that lets you connect apps and create automations without code. Supports 400+ integrations.",
    },
    "uptime_kuma": {
        "name": "Uptime Kuma",
        "description": "Self-hosted uptime monitoring tool. Monitor HTTP, TCP, ping, and get notified when services go down.",
        "icon": "📊",
        "category": "monitoring",
        "docker_image": "louislam/uptime-kuma:latest",
        "default_container_name": "webpanel_uptime_kuma",
        "config_schema": [
            {"key": "port", "label": "Web UI Port", "type": "number", "default": 3001, "required": True,
             "description": "Port for the Uptime Kuma dashboard"},
        ],
        "web_port": "{{port}}",
        "description_full": "Uptime Kuma is a self-hosted monitoring tool like Uptime Robot. Monitor HTTP, HTTPS, TCP, DNS, Ping, and get notifications via Telegram, Discord, email, and more.",
    },
    "netdata": {
        "name": "NetData",
        "description": "Real-time server monitoring with rich dashboards. CPU, memory, disk, network, and more.",
        "icon": "📈",
        "category": "monitoring",
        "docker_image": "netdata/netdata:latest",
        "default_container_name": "webpanel_netdata",
        "config_schema": [
            {"key": "port", "label": "Dashboard Port", "type": "number", "default": 19999, "required": True,
             "description": "Port for the NetData real-time dashboard"},
        ],
        "web_port": "{{port}}",
        "description_full": "NetData is a real-time performance monitoring tool that provides unparalleled insights into your systems and applications.",
    },
    "changedetection": {
        "name": "ChangeDetection.io",
        "description": "Monitor web pages for changes and get notified via email, Discord, Slack, and more.",
        "icon": "🔍",
        "category": "monitoring",
        "docker_image": "ghcr.io/dgtlmoon/changedetection.io:latest",
        "default_container_name": "webpanel_changedetection",
        "config_schema": [
            {"key": "port", "label": "Web UI Port", "type": "number", "default": 5000, "required": True,
             "description": "Port for the ChangeDetection dashboard"},
        ],
        "web_port": "{{port}}",
        "description_full": "ChangeDetection.io monitors web pages for changes and notifies you when content changes. Perfect for tracking price changes, documentation updates, and more.",
    },
    "vaultwarden": {
        "name": "Vaultwarden",
        "description": "Unofficial Bitwarden-compatible password manager server. Sync your passwords across all devices.",
        "icon": "🔐",
        "category": "security",
        "docker_image": "vaultwarden/server:latest",
        "default_container_name": "webpanel_vaultwarden",
        "config_schema": [
            {"key": "port", "label": "Web UI Port", "type": "number", "default": 8081, "required": True,
             "description": "Port for the Vaultwarden web interface"},
            {"key": "admin_token", "label": "Admin Token", "type": "password", "required": True,
             "description": "Token for accessing the Vaultwarden admin panel"},
        ],
        "web_port": "{{port}}",
        "description_full": "Vaultwarden is a lightweight self-hosted password manager compatible with Bitwarden clients. Store, sync, and share passwords securely.",
    },
    "nginx_proxy_manager": {
        "name": "Nginx Proxy Manager",
        "description": "Web-based reverse proxy management with SSL certificate auto-renewal.",
        "icon": "🌐",
        "category": "management",
        "docker_image": "jc21/nginx-proxy-manager:latest",
        "default_container_name": "webpanel_npm",
        "config_schema": [
            {"key": "port_http", "label": "HTTP Port", "type": "number", "default": 8080, "required": True,
             "description": "HTTP proxy entry port"},
            {"key": "port_https", "label": "HTTPS Port", "type": "number", "default": 8443, "required": True,
             "description": "HTTPS proxy entry port"},
            {"key": "port_admin", "label": "Admin UI Port", "type": "number", "default": 8181, "required": True,
             "description": "Port for the admin web interface"},
        ],
        "web_port": "{{port_admin}}",
        "description_full": "Nginx Proxy Manager provides a beautiful web interface to manage Nginx proxy hosts, SSL certificates, and access lists.",
    },
}


def _random_password(length: int = 24) -> str:
    """Generate a secure random alphanumeric password."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _substitute(template: str, config: dict) -> str:
    """Replace {{key}} placeholders with config values."""
    for k, v in config.items():
        template = template.replace("{{" + k + "}}", str(v))
    return template


def _container_state(container_name: str) -> str:
    """Return Docker container state: running → active, exited → inactive, etc."""
    try:
        r = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Status}}", container_name],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return "not installed"
        state = r.stdout.strip()
        if state == "running":
            return "active"
        if state in ("exited", "dead", "removing"):
            return "inactive"
        if state == "restarting":
            return "restarting"
        return state or "unknown"
    except Exception:
        return "unknown"


def _container_port(container_name: str, container_port: int) -> Optional[str]:
    """Return the host port mapping for a container port, or None."""
    try:
        r = subprocess.run(
            ["docker", "inspect", "--format",
             "{{(index (index .NetworkSettings.Ports \"" + str(container_port) + "/tcp\") 0).HostPort}}",
             container_name],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return None


async def _ensure_secondary_table(db: AsyncSession) -> None:
    """Create secondary_service records for any missing catalogue entries."""
    from sqlalchemy import text
    for key, info in SECONDARY_CATALOGUE.items():
        existing = await db.execute(
            select(SecondaryService).where(SecondaryService.key == key)
        )
        if not existing.scalar_one_or_none():
            svc = SecondaryService(
                key=key,
                name=info["name"],
                description=info["description"],
                icon=info.get("icon", "🧩"),
                category=info.get("category", "other"),
                enabled=False,
                config="{}",
                container_name="",
                docker_image=info["docker_image"],
            )
            db.add(svc)
    await db.commit()


# ── Helpers that build docker-run args ──────────────────────────────────────

def _build_docker_run_args(catalogue_entry: dict, config: dict) -> list[str]:
    """Build the `docker run` argument list for a secondary service."""
    args = [
        "docker", "run", "-d",
        "--network", "webpanel_net",
        "--restart", "unless-stopped",
    ]

    # Labels for management
    key = catalogue_entry.get("key", "")
    container_name = catalogue_entry.get("default_container_name", f"webpanel_{key}")
    args.extend(["--name", container_name])
    args.extend(["--label", f"gnukontrolr.secondary={key}"])
    args.extend(["--label", "gnukontrolr.managed=true"])

    key_id = [k for k, v in SECONDARY_CATALOGUE.items() if v == catalogue_entry][0] \
        if any(v == catalogue_entry for v in SECONDARY_CATALOGUE.values()) else ""

    # Ports — defined per service in the catalogue
    port_mappings = catalogue_entry.get("port_mappings", [])
    for pm in port_mappings:
        host_port = config.get(pm["config_key"], pm.get("default_host_port"))
        host_port = _substitute(str(host_port), config)
        args.extend(["-p", f"{host_port}:{pm['container_port']}"])

    # Volumes
    volumes = catalogue_entry.get("volumes", [])
    for vol in volumes:
        src = _substitute(vol["host_path"], config)
        dst = _substitute(vol["container_path"], config)
        args.extend(["-v", f"{src}:{dst}"])

    # Environment variables
    env_vars = catalogue_entry.get("env_vars", [])
    for env in env_vars:
        val = config.get(env["config_key"], env.get("default", ""))
        args.extend(["-e", f"{env['var_name']}={_substitute(str(val), config)}"])

    # Extra args from catalogue
    extra = catalogue_entry.get("extra_args", [])
    args.extend(extra)

    # Image
    image = _substitute(catalogue_entry["docker_image"], config)
    args.append(image)

    # Command override
    cmd_override = catalogue_entry.get("command")
    if cmd_override:
        cmd_str = _substitute(cmd_override, config)
        args.extend(cmd_str.split())

    return args


def _build_run_args_for_service(key: str, config: dict) -> list[str]:
    """Build docker run args for a specific secondary service by key."""
    entry = SECONDARY_CATALOGUE.get(key)
    if not entry:
        raise ValueError(f"Unknown secondary service: {key}")
    return _build_docker_run_args(entry, config)


# ── Define port_mappings, volumes, env_vars per service ─────────────────────

def _enrich_catalogue() -> None:
    """Add runtime metadata (ports, volumes, env_vars) to each catalogue entry."""
    _port_mappings: dict[str, list[dict]] = {
        "portainer": [
            {"config_key": "port", "container_port": 9443, "default_host_port": 9443},
        ],
        "minio": [
            {"config_key": "port_api", "container_port": 9000, "default_host_port": 9000},
            {"config_key": "port_console", "container_port": 9001, "default_host_port": 9001},
        ],
        "n8n": [
            {"config_key": "port", "container_port": 5678, "default_host_port": 5678},
        ],
        "uptime_kuma": [
            {"config_key": "port", "container_port": 3001, "default_host_port": 3001},
        ],
        "netdata": [
            {"config_key": "port", "container_port": 19999, "default_host_port": 19999},
        ],
        "changedetection": [
            {"config_key": "port", "container_port": 5000, "default_host_port": 5000},
        ],
        "vaultwarden": [
            {"config_key": "port", "container_port": 80, "default_host_port": 8081},
        ],
        "nginx_proxy_manager": [
            {"config_key": "port_http", "container_port": 80, "default_host_port": 8080},
            {"config_key": "port_https", "container_port": 443, "default_host_port": 8443},
            {"config_key": "port_admin", "container_port": 81, "default_host_port": 8181},
        ],
    }

    _volumes: dict[str, list[dict]] = {
        "portainer": [
            {"host_path": "/var/run/docker.sock", "container_path": "/var/run/docker.sock"},
            {"host_path": "portainer_data", "container_path": "/data"},
        ],
        "minio": [
            {"host_path": "minio_data", "container_path": "/data"},
        ],
        "n8n": [
            {"host_path": "n8n_data", "container_path": "/home/node/.n8n"},
        ],
        "uptime_kuma": [
            {"host_path": "uptime_kuma_data", "container_path": "/app/data"},
        ],
        "netdata": [
            {"host_path": "/etc/passwd", "container_path": "/host/etc/passwd:ro"},
            {"host_path": "/etc/group", "container_path": "/host/etc/group:ro"},
            {"host_path": "/proc", "container_path": "/host/proc:ro"},
            {"host_path": "/sys", "container_path": "/host/sys:ro"},
            {"host_path": "netdata_lib", "container_path": "/var/lib/netdata"},
            {"host_path": "netdata_cache", "container_path": "/var/cache/netdata"},
        ],
        "changedetection": [
            {"host_path": "changedetection_data", "container_path": "/datastore"},
        ],
        "vaultwarden": [
            {"host_path": "vaultwarden_data", "container_path": "/data"},
        ],
        "nginx_proxy_manager": [
            {"host_path": "npm_data", "container_path": "/data"},
            {"host_path": "npm_letsencrypt", "container_path": "/etc/letsencrypt"},
        ],
    }

    _env_vars: dict[str, list[dict]] = {
        "minio": [
            {"var_name": "MINIO_ROOT_USER", "config_key": "root_user", "default": "minioadmin"},
            {"var_name": "MINIO_ROOT_PASSWORD", "config_key": "root_password"},
        ],
        "n8n": [
            {"var_name": "N8N_ENCRYPTION_KEY", "config_key": "encryption_key"},
            {"var_name": "GENERIC_TIMEZONE", "config_key": "timezone", "default": "UTC"},
            {"var_name": "N8N_PORT", "config_key": "port", "default": 5678},
        ],
        "netdata": [
            {"var_name": "NETDATA_CLAIM_TOKEN", "config_key": "claim_token", "default": ""},
            {"var_name": "NETDATA_CLAIM_URL", "config_key": "claim_url", "default": ""},
        ],
        "vaultwarden": [
            {"var_name": "ADMIN_TOKEN", "config_key": "admin_token"},
        ],
    }

    _extra_args: dict[str, list[str]] = {
        "portainer": [
            "--restart", "unless-stopped",
            "-e", "SELINUX=false",
        ],
        "netdata": [
            "--cap-add", "SYS_PTRACE",
            "--security-opt", "apparmor=unconfined",
        ],
        "nginx_proxy_manager": [
            "--restart", "unless-stopped",
        ],
    }

    _commands: dict[str, str] = {
        "minio": "server /data --console-address :9001",
    }

    for key in SECONDARY_CATALOGUE:
        SECONDARY_CATALOGUE[key]["key"] = key
        SECONDARY_CATALOGUE[key]["port_mappings"] = _port_mappings.get(key, [])
        SECONDARY_CATALOGUE[key]["volumes"] = _volumes.get(key, [])
        SECONDARY_CATALOGUE[key]["env_vars"] = _env_vars.get(key, [])
        SECONDARY_CATALOGUE[key]["extra_args"] = _extra_args.get(key, [])
        if key in _commands:
            SECONDARY_CATALOGUE[key]["command"] = _commands[key]


_enrich_catalogue()


# ────────────────────────────────────────────────────────────────────────────
# API Endpoints
# ────────────────────────────────────────────────────────────────────────────

@router.get("/catalogue")
async def list_catalogue():
    """Return the full catalogue of available optional services."""
    result = {}
    for key, info in SECONDARY_CATALOGUE.items():
        result[key] = {
            "key": key,
            "name": info["name"],
            "description": info["description"],
            "description_full": info.get("description_full", ""),
            "icon": info.get("icon", "🧩"),
            "category": info.get("category", "other"),
            "docker_image": info["docker_image"],
            "config_schema": info["config_schema"],
            "web_port": info.get("web_port", ""),
        }
    return result


@router.get("")
async def list_secondary_services(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """List all secondary services with their current Docker state.

    Returns both enabled and available services so the frontend can
    show the catalogue alongside running instance status.
    """
    await _ensure_secondary_table(db)
    result = await db.execute(select(SecondaryService))
    rows = result.scalars().all()

    services = {}
    for row in rows:
        state = "not installed"
        port = None
        if row.enabled and row.container_name:
            state = _container_state(row.container_name)
            # Try to get web port from config
            try:
                cfg = json.loads(row.config) if row.config else {}
                web_port_tpl = SECONDARY_CATALOGUE.get(row.key, {}).get("web_port", "")
                if web_port_tpl:
                    port_str = _substitute(web_port_tpl, cfg)
                    # Check if it's a numeric port or needs port mapping lookup
                    if port_str.isdigit():
                        port = int(port_str)
            except (json.JSONDecodeError, ValueError):
                pass

        services[row.key] = {
            "key": row.key,
            "name": row.name,
            "description": row.description,
            "icon": row.icon,
            "category": row.category,
            "enabled": row.enabled,
            "state": state,
            "container_name": row.container_name,
            "docker_image": row.docker_image,
            "config": json.loads(row.config) if row.config else {},
            "web_port": port,
        }
    return services


@router.get("/{key}/config")
async def get_service_config(
    key: str,
    _=Depends(require_admin),
):
    """Return the config schema and any saved config for a secondary service."""
    entry = SECONDARY_CATALOGUE.get(key)
    if not entry:
        raise HTTPException(404, f"Unknown secondary service: {key}")

    db = None
    saved_config = {}
    try:
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(SecondaryService).where(SecondaryService.key == key)
            )
            row = result.scalar_one_or_none()
            if row and row.config:
                saved_config = json.loads(row.config)
    except Exception:
        pass

    return {
        "key": key,
        "schema": entry["config_schema"],
        "saved_config": saved_config,
    }


class EnableSecondaryRequest(BaseModel):
    config: dict = {}


@router.post("/{key}/enable")
async def enable_secondary_service(
    key: str,
    body: EnableSecondaryRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Enable (deploy) a secondary service with the provided config.

    Pulls the image, creates and starts the container, saves config to DB.
    """
    entry = SECONDARY_CATALOGUE.get(key)
    if not entry:
        raise HTTPException(404, f"Unknown secondary service: {key}")

    # Find DB record
    result = await db.execute(
        select(SecondaryService).where(SecondaryService.key == key)
    )
    svc = result.scalar_one_or_none()
    if not svc:
        raise HTTPException(404, "Service not found in database — re-run GET /api/server/secondary first")

    if svc.enabled:
        raise HTTPException(409, f"{svc.name} is already enabled. Disable it first to reconfigure.")

    config = body.config or {}
    container_name = entry["default_container_name"]

    # Auto-generate passwords for any password-type fields that are empty
    for field in entry["config_schema"]:
        if field["type"] == "password" and (not config.get(field["key"]) or config.get(field["key"]) == ""):
            config[field["key"]] = _random_password()

    # Validate required fields
    for field in entry["config_schema"]:
        if field.get("required") and not config.get(field["key"]):
            raise HTTPException(400, f"'{field['label']}' is required")

    try:
        args = _build_run_args_for_service(key, config)
    except ValueError as e:
        raise HTTPException(400, str(e))

    log.info("Deploying secondary service %s → container %s", key, container_name)

    loop = asyncio.get_running_loop()

    def _deploy():
        # Pull image first
        pull = subprocess.run(
            ["docker", "pull", entry["docker_image"]],
            capture_output=True, text=True, timeout=120,
        )
        # Remove existing container with same name if any
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True, text=True, timeout=10,
        )
        # Run the container
        r = subprocess.run(args, capture_output=True, text=True, timeout=60)
        return r

    result_proc = await loop.run_in_executor(None, _deploy)

    if result_proc.returncode != 0:
        error_msg = result_proc.stderr.strip()[:500]
        log.error("Failed to deploy %s: %s", key, error_msg)
        raise HTTPException(500, f"Failed to deploy {key}: {error_msg}")

    # Save to DB
    svc.enabled = True
    svc.config = json.dumps(config)
    svc.container_name = container_name
    svc.docker_image = entry["docker_image"]
    svc.updated_at = datetime.utcnow()
    await db.commit()

    return {
        "ok": True,
        "key": key,
        "container_name": container_name,
        "config": config,
    }


@router.post("/{key}/disable")
async def disable_secondary_service(
    key: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Disable (remove) a secondary service. Stops and removes the container."""
    result = await db.execute(
        select(SecondaryService).where(SecondaryService.key == key)
    )
    svc = result.scalar_one_or_none()
    if not svc:
        raise HTTPException(404, f"Unknown secondary service: {key}")
    if not svc.enabled:
        raise HTTPException(409, f"{svc.name} is not enabled")

    container_name = svc.container_name
    if container_name:
        loop = asyncio.get_running_loop()

        def _remove():
            subprocess.run(
                ["docker", "stop", container_name],
                capture_output=True, text=True, timeout=30,
            )
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True, text=True, timeout=15,
            )

        await loop.run_in_executor(None, _remove)

    svc.enabled = False
    svc.container_name = ""
    svc.config = "{}"
    svc.updated_at = datetime.utcnow()
    await db.commit()

    return {"ok": True, "key": key, "message": f"{svc.name} disabled and container removed"}


@router.post("/{key}/{action}")
async def control_secondary_service(
    key: str,
    action: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Start, stop, or restart an enabled secondary service container."""
    if action not in ("start", "stop", "restart"):
        raise HTTPException(400, "action must be start, stop, or restart")

    result = await db.execute(
        select(SecondaryService).where(SecondaryService.key == key)
    )
    svc = result.scalar_one_or_none()
    if not svc:
        raise HTTPException(404, f"Unknown secondary service: {key}")
    if not svc.enabled or not svc.container_name:
        raise HTTPException(409, f"{svc.name} is not enabled")

    container = svc.container_name
    loop = asyncio.get_running_loop()

    def _control():
        # For start, try to start existing container; if container doesn't exist, re-deploy
        if action == "start":
            r = subprocess.run(
                ["docker", "inspect", "--format", "{{.Name}}", container],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode != 0:
                # Container was removed, need to re-create it from saved config
                try:
                    config = json.loads(svc.config) if svc.config else {}
                    args = _build_run_args_for_service(key, config)
                    return subprocess.run(args, capture_output=True, text=True, timeout=60)
                except Exception as e:
                    return subprocess.CompletedProcess([], 1, "", str(e))

        return subprocess.run(
            ["docker", action, container],
            capture_output=True, text=True, timeout=30,
        )

    r = await loop.run_in_executor(None, _control)
    if r.returncode != 0:
        return {"ok": False, "error": r.stderr.strip()[:300]}, 500

    # Bust cache on next list
    return {"ok": True, "key": key, "action": action}


@router.post("/{key}/configure")
async def configure_secondary_service(
    key: str,
    body: EnableSecondaryRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Save configuration for a secondary service without deploying it."""
    entry = SECONDARY_CATALOGUE.get(key)
    if not entry:
        raise HTTPException(404, f"Unknown secondary service: {key}")

    result = await db.execute(
        select(SecondaryService).where(SecondaryService.key == key)
    )
    svc = result.scalar_one_or_none()
    if not svc:
        raise HTTPException(404, "Service not found — re-run GET /api/server/secondary first")

    config = body.config or {}
    svc.config = json.dumps(config)
    svc.updated_at = datetime.utcnow()
    await db.commit()

    return {"ok": True, "key": key, "message": "Configuration saved"}
