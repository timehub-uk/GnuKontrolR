"""
Secondary (optional) services — add-on containers the admin can discover
and deploy through the services page.  Each has a config modal with setup
fields, then runs as a Docker container on webpanel_net.

All docker operations use the Docker HTTP API via docker-api-proxy.
"""
import asyncio
import json
import logging
import os
import secrets
import string
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.database import get_db
from app.docker_client import (
    inspect_container, create_container, start_container,
    stop_container, remove_container, container_logs, exec_run_sync,
)
from app.models.secondary_service import SecondaryService
from app.models.secondary_service_blob import SecondaryServiceBlob

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
    "mediamtx": {
        "name": "MediaMTX",
        "description": "Media server that allows to publish, read and share live video and audio streams over RTSP, RTMP, HLS, WebRTC, and SRT.",
        "icon": "🎥",
        "category": "media",
        "docker_image": "bluenviron/mediamtx:latest",
        "default_container_name": "webpanel_mediamtx",
        "config_schema": [
            {"key": "rtsp_port", "label": "RTSP Port", "type": "number", "default": 8554, "required": True,
             "description": "Port for RTSP publishing/reading (TCP+UDP)"},
            {"key": "rtmp_port", "label": "RTMP Port", "type": "number", "default": 1935, "required": True,
             "description": "Port for RTMP publishing/reading (TCP)"},
            {"key": "hls_port", "label": "HLS Port", "type": "number", "default": 8888, "required": True,
             "description": "Port for HLS playback (TCP)"},
            {"key": "webrtc_port", "label": "WebRTC Port", "type": "number", "default": 8889, "required": True,
             "description": "Port for WebRTC signaling (TCP)"},
            {"key": "webrtc_udp_port", "label": "WebRTC UDP Port", "type": "number", "default": 8189, "required": True,
             "description": "Port for WebRTC media transfer (UDP)"},
            {"key": "srt_port", "label": "SRT Port", "type": "number", "default": 8890, "required": True,
             "description": "Port for SRT publishing/reading (UDP)"},
        ],
        "web_port": "{{hls_port}}",
        "description_full": "MediaMTX (formerly rtsp-simple-server) is a ready-to-use, zero-dependency media server and media proxy that allows to publish, read, and share live video and audio streams.",
    },
    "mediadump": {
        "name": "Media Dump",
        "description": "Media dump and conversion service. Scales video to 720p/1080p and encodes audio to 48k/96k/128k with matching UUIDs.",
        "icon": "📁",
        "category": "media",
        "docker_image": "webpanel/mediadump:latest",
        "default_container_name": "webpanel_mediadump",
        "config_schema": [
            {"key": "port", "label": "Web UI Port", "type": "number", "default": 5001, "required": True,
             "description": "Port for the Media Dump web interface"},
        ],
        "web_port": "{{port}}",
        "description_full": "Media Dump is an automated file scaler and transcoder. Upload any video or audio file, and it dynamically converts it to 720p and 1080p video profiles, plus 48kbps, 96kbps, and 128kbps audio profiles, organized inside a unique folder named by UUID.",
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
    """Return Docker container state via Docker API."""
    try:
        info = inspect_container(container_name)
        # Since inspect_container is async but we're sync, use wrapper
        import httpx
        with httpx.Client(timeout=5, verify=False) as client:
            from app.docker_client import DOCKER_API_URL
            resp = client.get(f"{DOCKER_API_URL}/containers/{container_name}/json")
            if resp.status_code == 404:
                return "not installed"
            resp.raise_for_status()
            state = resp.json().get("State", {}).get("Status", "")
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
        import httpx
        from app.docker_client import DOCKER_API_URL
        with httpx.Client(timeout=5, verify=False) as client:
            resp = client.get(f"{DOCKER_API_URL}/containers/{container_name}/json")
            if resp.status_code != 200:
                return None
            info = resp.json()
            ports = info.get("NetworkSettings", {}).get("Ports", {})
            mapping = ports.get(f"{container_port}/tcp")
            if mapping and len(mapping) > 0:
                return mapping[0].get("HostPort")
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

def _build_container_config(key: str, config: dict) -> dict:
    """Build a Docker API container config from the catalogue + user config."""
    entry = SECONDARY_CATALOGUE.get(key)
    if not entry:
        raise ValueError(f"Unknown secondary service: {key}")

    # Labels
    labels = {
        "gnukontrolr.secondary": key,
        "gnukontrolr.managed": "true",
    }

    # Port bindings
    port_bindings = {}
    exposed_ports = {}
    for pm in entry.get("port_mappings", []):
        host_port = config.get(pm["config_key"], pm.get("default_host_port"))
        host_port = _substitute(str(host_port), config)
        proto = pm.get("protocol", "tcp")
        cp = f"{pm['container_port']}/{proto}"
        port_bindings[cp] = [{"HostIp": "0.0.0.0", "HostPort": str(host_port)}]
        exposed_ports[cp] = {}

    # Volumes
    volumes = []
    for vol in entry.get("volumes", []):
        src = _substitute(vol["host_path"], config)
        dst = _substitute(vol["container_path"], config)
        volumes.append(f"{src}:{dst}")

    # Environment variables
    env = []
    for env_var in entry.get("env_vars", []):
        val = config.get(env_var["config_key"], env_var.get("default", ""))
        env.append(f"{env_var['var_name']}={_substitute(str(val), config)}")

    # Build config dict
    container_config: dict = {
        "Image": _substitute(entry["docker_image"], config),
        "Hostname": entry.get("default_container_name", f"webpanel_{key}")[:64],
        "Labels": labels,
        "Env": env,
        "ExposedPorts": exposed_ports,
        "HostConfig": {
            "NetworkMode": "webpanel_net",
            "RestartPolicy": {"Name": "unless-stopped"},
            "PortBindings": port_bindings,
            "Binds": volumes,
        },
    }

    # Extra args: convert --flag value pairs into HostConfig entries
    extra_args = entry.get("extra_args", [])
    i = 0
    while i < len(extra_args):
        arg = extra_args[i]
        if arg == "--memory" and i + 1 < len(extra_args):
            container_config["HostConfig"]["Memory"] = int(
                extra_args[i + 1].rstrip("m")) * 1024 * 1024
            i += 2
        elif arg == "--cpus" and i + 1 < len(extra_args):
            container_config["HostConfig"]["NanoCpus"] = int(
                float(extra_args[i + 1]) * 1e9)
            i += 2
        elif arg == "--tmpfs" and i + 1 < len(extra_args):
            if "Tmpfs" not in container_config["HostConfig"]:
                container_config["HostConfig"]["Tmpfs"] = {}
            parts = extra_args[i + 1].split(":", 1)
            container_config["HostConfig"]["Tmpfs"][parts[0]] = parts[1] if len(parts) > 1 else ""
            i += 2
        elif arg == "--user" and i + 1 < len(extra_args):
            container_config["User"] = extra_args[i + 1]
            i += 2
        elif arg == "--cap-drop" and i + 1 < len(extra_args):
            if "CapDrop" not in container_config["HostConfig"]:
                container_config["HostConfig"]["CapDrop"] = []
            container_config["HostConfig"]["CapDrop"].append(extra_args[i + 1])
            i += 2
        elif arg == "--cap-add" and i + 1 < len(extra_args):
            if "CapAdd" not in container_config["HostConfig"]:
                container_config["HostConfig"]["CapAdd"] = []
            container_config["HostConfig"]["CapAdd"].append(extra_args[i + 1])
            i += 2
        elif arg == "--read-only" and i + 1 < len(extra_args):
            container_config["HostConfig"]["ReadonlyRootfs"] = extra_args[i + 1].lower() == "true"
            i += 2
        elif arg.startswith("--"):
            i += 2  # skip flag + value
        else:
            i += 1

    # Command override
    cmd_override = entry.get("command")
    if cmd_override:
        cmd_str = _substitute(cmd_override, config)
        container_config["Cmd"] = cmd_str.split()

    return container_config


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
        "mediamtx": [
            {"config_key": "rtsp_port", "container_port": 8554, "default_host_port": 8554, "protocol": "tcp"},
            {"config_key": "rtsp_port", "container_port": 8554, "default_host_port": 8554, "protocol": "udp"},
            {"config_key": "rtmp_port", "container_port": 1935, "default_host_port": 1935, "protocol": "tcp"},
            {"config_key": "hls_port", "container_port": 8888, "default_host_port": 8888, "protocol": "tcp"},
            {"config_key": "webrtc_port", "container_port": 8889, "default_host_port": 8889, "protocol": "tcp"},
            {"config_key": "webrtc_udp_port", "container_port": 8189, "default_host_port": 8189, "protocol": "udp"},
            {"config_key": "srt_port", "container_port": 8890, "default_host_port": 8890, "protocol": "udp"},
        ],
        "mediadump": [
            {"config_key": "port", "container_port": 5001, "default_host_port": 5001},
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
        "mediadump": [
            {"host_path": "mediadump_data", "container_path": "/data"},
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
        "mediamtx": [
            {"var_name": "MTX_RTSPADDRESS", "config_key": "_rtsp_addr", "default": ":{{rtsp_port}}"},
            {"var_name": "MTX_RTMPADDRESS", "config_key": "_rtmp_addr", "default": ":{{rtmp_port}}"},
            {"var_name": "MTX_HLSADDRESS", "config_key": "_hls_addr", "default": ":{{hls_port}}"},
            {"var_name": "MTX_WEBRTCADDRESS", "config_key": "_webrtc_addr", "default": ":{{webrtc_port}}"},
            {"var_name": "MTX_WEBRTCLOCALUDPADDRESS", "config_key": "_webrtc_udp_addr", "default": ":{{webrtc_udp_port}}"},
            {"var_name": "MTX_SRTADDRESS", "config_key": "_srt_addr", "default": ":{{srt_port}}"},
            {"var_name": "MTX_METRICS", "config_key": "_metrics_enable", "default": "yes"},
            {"var_name": "MTX_METRICSADDRESS", "config_key": "_metrics_addr", "default": ":9998"},
        ],
        "mediadump": [
            {"var_name": "HOME", "config_key": "_home", "default": "/tmp"},
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
        "mediamtx": [
            "--user", "65534:65534",
            "--cap-drop", "ALL",
            "--read-only", "true",
            "--tmpfs", "/tmp:noexec,nosuid,size=16M",
        ],
        "mediadump": [
            "--user", "65534:65534",
            "--cap-drop", "ALL",
            "--read-only", "true",
            "--tmpfs", "/tmp:noexec,nosuid,size=16M",
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

    # Build container config
    try:
        container_config = _build_container_config(key, config)
    except ValueError as e:
        raise HTTPException(400, str(e))

    log.info("Deploying secondary service %s → container %s", key, container_name)

    loop = asyncio.get_running_loop()

    # Check if we have a cached database blob for this service
    blob_result = await db.execute(
        select(SecondaryServiceBlob).where(SecondaryServiceBlob.service_key == key)
    )
    blob_entry = blob_result.scalar_one_or_none()

    temp_path = None
    if blob_entry:
        temp_path = f"/tmp/{blob_entry.filename}"
        log.info("Found database blob for %s, extracting to %s...", key, temp_path)
        def _write_temp():
            with open(temp_path, "wb") as f:
                f.write(blob_entry.blob_data)
        await loop.run_in_executor(None, _write_temp)

    def _deploy(t_path=None):
        import httpx
        from app.docker_client import DOCKER_API_URL

        with httpx.Client(timeout=300, verify=False) as client:
            loaded_successfully = False
            is_docker = True

            if t_path and os.path.exists(t_path):
                try:
                    if t_path.endswith(".tar"):
                        log.info("Loading image from temporary location %s into Docker...", t_path)
                        with open(t_path, "rb") as f:
                            load_resp = client.post(
                                f"{DOCKER_API_URL}/images/load",
                                content=f,
                                headers={"Content-Type": "application/x-tar"},
                                timeout=300,
                            )
                            if load_resp.status_code in (200, 201):
                                log.info("Successfully loaded image from database blob into Docker.")
                                loaded_successfully = True
                            else:
                                log.warning("Image load from blob returned status %d: %s", load_resp.status_code, load_resp.text[:300])
                    else:
                        # Non-Docker installer file
                        is_docker = False
                        dest_dir = f"/var/webpanel/services/{key}"
                        os.makedirs(dest_dir, exist_ok=True)
                        dest_path = os.path.join(dest_dir, os.path.basename(t_path))

                        log.info("Copying installer from temp %s to destination %s...", t_path, dest_path)
                        import shutil
                        shutil.copy2(t_path, dest_path)

                        # If it is a shell script, make it executable and run it to install/setup
                        if dest_path.endswith(".sh"):
                            log.info("Running installer script %s...", dest_path)
                            os.chmod(dest_path, 0o755)
                            import subprocess
                            sub_res = subprocess.run(
                                [dest_path],
                                cwd=dest_dir,
                                env={**os.environ, "GNUKONTROLR_SERVICE_DIR": dest_dir},
                                capture_output=True,
                                text=True,
                                timeout=300
                            )
                            if sub_res.returncode == 0:
                                log.info("Installer script succeeded: %s", sub_res.stdout[:500])
                            else:
                                log.error("Installer script failed (code %d): %s", sub_res.returncode, sub_res.stderr[:500])
                                raise RuntimeError(f"Installer script failed: {sub_res.stderr[:300]}")

                        loaded_successfully = True
                except Exception as ex:
                    log.error("Failed to load/install from temporary location %s: %s", t_path, ex)
                    if not is_docker:
                        raise ex
                finally:
                    # Clean up temp file
                    try:
                        if os.path.exists(t_path):
                            os.remove(t_path)
                    except Exception:
                        pass

            # Fallback to remote pull if not loaded from blob (only for Docker services)
            if is_docker and not loaded_successfully:
                log.info("Pulling remote image %s...", entry["docker_image"])
                pull_resp = client.post(
                    f"{DOCKER_API_URL}/images/create",
                    params={"fromImage": entry["docker_image"]},
                    timeout=300,
                )
                if pull_resp.status_code not in (200, 201):
                    log.warning("Image pull returned %d for %s", pull_resp.status_code, entry["docker_image"])

        if is_docker:
            # Remove existing container with same name if any
            try:
                with httpx.Client(timeout=10, verify=False) as client:
                    client.delete(f"{DOCKER_API_URL}/containers/{container_name}?force=true")
            except Exception:
                pass

            # Build the container config
            container_config = _build_container_config(key, config)

            # Create and start via API
            with httpx.Client(timeout=30, verify=False) as client:
                params = {"name": container_name}
                resp = client.post(
                    f"{DOCKER_API_URL}/containers/create",
                    params=params,
                    json=container_config,
                )
                if resp.status_code not in (200, 201):
                    raise RuntimeError(f"Create failed: {resp.text[:300]}")
                log.info("Container %s created: %s", container_name, resp.json())

                # Start the container
                start_resp = client.post(f"{DOCKER_API_URL}/containers/{container_name}/start")
                if start_resp.status_code not in (200, 204):
                    raise RuntimeError(f"Start failed: {start_resp.text[:300]}")

            return resp
        else:
            return {"status": "installed_locally"}

    try:
        result = await loop.run_in_executor(None, _deploy, temp_path)
    except Exception as e:
        log.error("Failed to deploy %s: %s", key, e)
        # Ensure temp file is cleaned up if it still exists
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        raise HTTPException(500, f"Failed to deploy {key}: {e}")

    # Save to DB
    svc.enabled = True
    svc.config = json.dumps(config)
    svc.container_name = container_name
    svc.docker_image = entry["docker_image"]
    svc.updated_at = datetime.now(timezone.utc)
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
            import httpx
            from app.docker_client import DOCKER_API_URL
            with httpx.Client(timeout=30, verify=False) as client:
                try:
                    client.post(f"{DOCKER_API_URL}/containers/{container_name}/stop")
                except Exception:
                    pass
                try:
                    client.delete(f"{DOCKER_API_URL}/containers/{container_name}?force=true")
                except Exception:
                    pass

        await loop.run_in_executor(None, _remove)

    svc.enabled = False
    svc.container_name = ""
    svc.config = "{}"
    svc.updated_at = datetime.now(timezone.utc)
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
        import httpx
        from app.docker_client import DOCKER_API_URL
        with httpx.Client(timeout=30, verify=False) as client:
            # For start, check if container exists
            if action == "start":
                insp_resp = client.get(f"{DOCKER_API_URL}/containers/{container}/json")
                if insp_resp.status_code == 404:
                    # Container was removed, need to re-create it from saved config
                    try:
                        config = json.loads(svc.config) if svc.config else {}
                        container_config = _build_container_config(key, config)
                        # Create
                        c_resp = client.post(
                            f"{DOCKER_API_URL}/containers/create",
                            params={"name": container},
                            json=container_config,
                        )
                        if c_resp.status_code not in (200, 201):
                            return c_resp, c_resp.text[:300]
                    except Exception as e:
                        return None, str(e)

            # Start/stop/restart
            resp = client.post(f"{DOCKER_API_URL}/containers/{container}/{action}")
            if resp.status_code not in (200, 204):
                return resp, resp.text[:300]
            return resp, ""

    r, err = await loop.run_in_executor(None, _control)
    if err:
        return {"ok": False, "error": err}, 500

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
    svc.updated_at = datetime.now(timezone.utc)
    await db.commit()

    return {"ok": True, "key": key, "message": "Configuration saved"}


@router.post("/{key}/cache")
async def cache_secondary_service_image(
    key: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Pull the remote image for a secondary service, export it to a temporary tar file,
    and save the tar file as a binary blob in the database for offline installation.
    """
    entry = SECONDARY_CATALOGUE.get(key)
    if not entry:
        raise HTTPException(404, f"Unknown secondary service: {key}")

    image_name = entry["docker_image"]
    log.info("Caching image %s to DB as blob...", image_name)

    loop = asyncio.get_running_loop()

    def _pull_and_save():
        import httpx
        from app.docker_client import DOCKER_API_URL
        temp_path = f"/tmp/{key}_cache.tar"

        with httpx.Client(timeout=300, verify=False) as client:
            # 1. Pull the remote image
            log.info("Pulling remote image %s...", image_name)
            pull_resp = client.post(
                f"{DOCKER_API_URL}/images/create",
                params={"fromImage": image_name},
                timeout=300,
            )
            if pull_resp.status_code not in (200, 201):
                log.warning("Image pull returned status %d for %s. Attempting local export...", pull_resp.status_code, image_name)

            # 2. Export to temporary tarball file
            log.info("Exporting image %s to temporary location %s...", image_name, temp_path)
            with open(temp_path, "wb") as f:
                with client.stream("GET", f"{DOCKER_API_URL}/images/{image_name}/get", timeout=300) as r:
                    if r.status_code not in (200, 201):
                        raise RuntimeError(f"Failed to export image: status {r.status_code}")
                    for chunk in r.iter_bytes(chunk_size=8192):
                        f.write(chunk)

            # Read bytes of temp file
            log.info("Reading exported image tar archive...")
            with open(temp_path, "rb") as f:
                blob_bytes = f.read()

            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)

            return blob_bytes

    try:
        blob_bytes = await loop.run_in_executor(None, _pull_and_save)
    except Exception as e:
        log.error("Failed to cache %s: %s", key, e)
        raise HTTPException(500, f"Failed to cache service image: {e}")

    # Save to Database (insert or update)
    result = await db.execute(
        select(SecondaryServiceBlob).where(SecondaryServiceBlob.service_key == key)
    )
    blob_entry = result.scalar_one_or_none()
    if not blob_entry:
        blob_entry = SecondaryServiceBlob(
            service_key=key,
            filename=f"{key}_image.tar",
            blob_data=blob_bytes,
        )
        db.add(blob_entry)
    else:
        blob_entry.filename = f"{key}_image.tar"
        blob_entry.blob_data = blob_bytes
        blob_entry.updated_at = datetime.utcnow()

    await db.commit()

    return {
        "ok": True,
        "key": key,
        "message": f"Successfully pulled and cached {image_name} as blob in DB",
        "size_bytes": len(blob_bytes),
    }
