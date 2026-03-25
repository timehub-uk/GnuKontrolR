"""Server stats and service control endpoints — with Redis caching + thread pool."""
import asyncio
import subprocess
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
import psutil

from app.auth import require_admin, get_current_user
from app.cache import cache_get, cache_set, cached

router = APIRouter(prefix="/api/server", tags=["server"])

SERVICES = ["nginx", "apache2", "mysql", "php8.2-fpm", "postfix", "dovecot", "redis"]

# Thread pool for blocking psutil / subprocess calls
_pool = ThreadPoolExecutor(max_workers=4)


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
    results = {}
    futures = {svc: loop.run_in_executor(_pool, _check_service, svc) for svc in SERVICES}
    for svc, fut in futures.items():
        results[svc] = await fut
    await cache_set("server:services", results, ttl=10)
    return results


@router.post("/services/{service}/{action}")
async def control_service(service: str, action: str, _=Depends(require_admin)):
    if service not in SERVICES:
        return JSONResponse({"error": "Unknown service"}, status_code=400)
    if action not in ("start", "stop", "restart", "reload"):
        return JSONResponse({"error": "Invalid action"}, status_code=400)
    loop = asyncio.get_running_loop()
    def _run():
        return subprocess.run(
            ["systemctl", action, service],
            capture_output=True, text=True, timeout=10,
        )
    r = await loop.run_in_executor(_pool, _run)
    if r.returncode != 0:
        return JSONResponse({"error": r.stderr.strip()}, status_code=500)
    # Invalidate services cache
    from app.cache import cache_delete
    await cache_delete("server:services")
    return {"ok": True, "service": service, "action": action}


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
