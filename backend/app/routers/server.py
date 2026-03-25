"""Server stats and service control endpoints — with Redis caching + thread pool."""
import asyncio
import json
import os
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse
import psutil

from app.auth import require_admin, get_current_user
from app.cache import cache_get, cache_set, cached

router = APIRouter(prefix="/api/server", tags=["server"])

# Map service key → Docker container name
CONTAINER_SERVICES = {
    "traefik":  "webpanel_traefik",
    "mysql":    "webpanel_mysql",
    "postgres": "webpanel_postgres",
    "redis":    "webpanel_redis",
    "postfix":  "webpanel_postfix",
    "dovecot":  "webpanel_dovecot",
    "powerdns": "webpanel_powerdns",
}

# Thread pool for blocking psutil / subprocess calls
_pool = ThreadPoolExecutor(max_workers=4)


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


def _collect_stats() -> dict:
    """Blocking stats collection — runs in thread pool."""
    cpu  = psutil.cpu_percent(interval=0.5)
    mem  = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net  = psutil.net_io_counters()
    return {
        "cpu_percent":    cpu,
        "mem_total_mb":   mem.total  // (1024 * 1024),
        "mem_used_mb":    mem.used   // (1024 * 1024),
        "mem_percent":    mem.percent,
        "disk_total_gb":  disk.total // (1024 ** 3),
        "disk_used_gb":   disk.used  // (1024 ** 3),
        "disk_percent":   disk.percent,
        "net_sent_mb":    net.bytes_sent // (1024 * 1024),
        "net_recv_mb":    net.bytes_recv // (1024 * 1024),
        "boot_timestamp": int(psutil.boot_time()),
    }


def _check_service(svc: str) -> str:
    try:
        r = subprocess.run(
            ["systemctl", "is-active", svc],
            capture_output=True, text=True, timeout=3,
        )
        return r.stdout.strip()
    except Exception:
        return "unknown"


@router.get("/stats")
async def server_stats(_=Depends(get_current_user)):
    # Cache for 3 seconds to absorb rapid dashboard polls
    cached_val = await cache_get("server:stats")
    if cached_val:
        return cached_val
    loop = asyncio.get_running_loop()
    stats = await loop.run_in_executor(_pool, _collect_stats)
    await cache_set("server:stats", stats, ttl=3)
    return stats


@router.get("/services")
async def service_status(_=Depends(require_admin)):
    cached_val = await cache_get("server:services")
    if cached_val:
        return cached_val
    loop = asyncio.get_running_loop()
    futures = {
        key: loop.run_in_executor(_pool, _container_state, cname)
        for key, cname in CONTAINER_SERVICES.items()
    }
    results = {key: await fut for key, fut in futures.items()}
    await cache_set("server:services", results, ttl=10)
    return results


@router.post("/services/{service}/{action}")
async def control_service(service: str, action: str, _=Depends(require_admin)):
    if service not in CONTAINER_SERVICES:
        return JSONResponse({"error": "Unknown service"}, status_code=400)
    if action not in ("start", "stop", "restart"):
        return JSONResponse({"error": "Invalid action"}, status_code=400)
    container = CONTAINER_SERVICES[service]
    loop = asyncio.get_running_loop()
    def _run():
        return subprocess.run(
            ["docker", action, container],
            capture_output=True, text=True, timeout=30,
        )
    r = await loop.run_in_executor(_pool, _run)
    if r.returncode != 0:
        return JSONResponse({"error": r.stderr.strip()}, status_code=500)
    from app.cache import cache_delete
    await cache_delete("server:services")
    return {"ok": True, "service": service, "action": action}


def _tcp_check(host: str, port: int, timeout: float = 2.0) -> tuple[bool, float]:
    """Try a TCP connection; return (success, latency_ms)."""
    t0 = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, round((time.monotonic() - t0) * 1000, 1)
    except OSError:
        return False, -1


def _container_uptime(cname: str) -> int | None:
    """Return container uptime in seconds, or None if not available."""
    try:
        r = subprocess.run(
            ["docker", "inspect", "--format",
             "{{.State.StartedAt}}", cname],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return None
        started = r.stdout.strip()
        from datetime import datetime, timezone
        # Format: 2025-06-10T12:34:56.123456789Z
        dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
        return int((datetime.now(timezone.utc) - dt).total_seconds())
    except Exception:
        return None


def _collect_diagnostic() -> dict:
    """Full diagnostic — runs in thread pool."""
    stats     = _collect_stats()
    services  = {}
    uptimes   = {}
    for key, cname in CONTAINER_SERVICES.items():
        services[key] = _container_state(cname)
        uptimes[key]  = _container_uptime(cname)

    # TCP health checks for key services
    checks = {
        "mysql":    _tcp_check("webpanel_mysql",    3306),
        "redis":    _tcp_check("redis",             6379),
        "postfix":  _tcp_check("webpanel_postfix",  25),
        "powerdns": _tcp_check("webpanel_powerdns", 53),
        "traefik":  _tcp_check("webpanel_traefik",  80),
    }

    # Count customer containers on webpanel_net
    try:
        r = subprocess.run(
            ["docker", "ps", "-a",
             "--filter", "network=webpanel_net",
             "--format", "{{.Status}}"],
            capture_output=True, text=True, timeout=5,
        )
        lines  = [l.strip() for l in r.stdout.splitlines() if l.strip()]
        cust_total  = len(lines)
        cust_up     = sum(1 for l in lines if l.startswith("Up"))
        cust_down   = cust_total - cust_up
    except Exception:
        cust_total = cust_up = cust_down = 0

    # Derive overall health level
    def _level(pct: float) -> str:
        if pct >= 90: return "critical"
        if pct >= 75: return "warning"
        return "ok"

    return {
        "timestamp": int(time.time()),
        "stats": stats,
        "services": services,
        "service_uptimes": uptimes,
        "tcp_checks": {
            k: {"ok": ok, "latency_ms": lat}
            for k, (ok, lat) in checks.items()
        },
        "customer_containers": {
            "total": cust_total,
            "up":    cust_up,
            "down":  cust_down,
        },
        "health": {
            "cpu":  _level(stats["cpu_percent"]),
            "mem":  _level(stats["mem_percent"]),
            "disk": _level(stats["disk_percent"]),
        },
    }


_STATUS_FILE = "/app/data/status.json"


@router.get("/diagnostic")
async def system_diagnostic(_=Depends(require_admin)):
    """Full system diagnostic — services, resources, TCP health checks.
    Also writes /app/data/status.json for external monitoring."""
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(_pool, _collect_diagnostic)
    # Persist for external consumers / monitoring
    try:
        os.makedirs(os.path.dirname(_STATUS_FILE), exist_ok=True)
        with open(_STATUS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass
    return data


@router.get("/status.json", include_in_schema=False)
async def status_json(_=Depends(require_admin)):
    """Serve the last-written status.json snapshot."""
    if os.path.exists(_STATUS_FILE):
        return FileResponse(_STATUS_FILE, media_type="application/json")
    return JSONResponse({"error": "No status snapshot yet — run /api/server/diagnostic first"}, status_code=404)


@router.websocket("/ws/stats")
async def ws_stats(websocket: WebSocket):
    await websocket.accept()
    loop = asyncio.get_running_loop()
    try:
        while True:
            stats = await loop.run_in_executor(_pool, _collect_stats)
            await websocket.send_json({
                "cpu":        stats["cpu_percent"],
                "mem":        stats["mem_percent"],
                "mem_used_mb": stats["mem_used_mb"],
                "disk":       stats["disk_percent"],
                "net_sent":   stats["net_sent_mb"],
                "net_recv":   stats["net_recv_mb"],
            })
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
