"""WebPanel — FastAPI application entry point."""
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pathlib import Path
from prometheus_client import (
    Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST,
    CollectorRegistry, multiprocess
)
import psutil

log = logging.getLogger("webpanel")

from app.database import init_db
from app.routers import auth, users, domains, server, docker_mgr, services, admin_content, container_proxy, security, activity_log, marketplace


# Prometheus metrics
_req_counter = Counter("webpanel_http_requests_total", "Total HTTP requests", ["method", "path"])
_cpu_gauge   = Gauge("webpanel_host_cpu_percent",  "Host CPU usage %")
_mem_gauge   = Gauge("webpanel_host_mem_percent",  "Host memory usage %")
_disk_gauge  = Gauge("webpanel_host_disk_percent", "Host disk usage %")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="WebPanel",
    description="Multi-domain, multi-user web hosting control panel",
    version="1.0.0",
    lifespan=lifespan,
)

_IS_PRODUCTION = os.environ.get("ENVIRONMENT", "development").lower() == "production"

# Force HTTPS in production (Traefik handles TLS termination; this redirect
# catches any direct HTTP reaches that bypass Traefik)
if _IS_PRODUCTION:
    app.add_middleware(HTTPSRedirectMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=(
        [os.environ.get("PANEL_ORIGIN", "https://panel.example.com")]
        if _IS_PRODUCTION
        else ["http://localhost:5173", "http://localhost:3000"]
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _request_lifecycle(request: Request, call_next):
    """
    Per-request lifecycle middleware:
      1. Assign / accept a UUID event ID (X-Request-ID header).
      2. Time the request.
      3. Echo the event ID in the response header.
      4. Add security headers.
      5. Write an entry to the requesting user's private activity log.
      6. Structured-log every request with event ID for server-side tracing.
    """
    import hashlib
    from app.auth import _decode_token   # local import to avoid circular at module level

    # Accept a client-supplied ID or mint a fresh UUID
    event_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.event_id = event_id

    t0 = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

    # Propagate the event ID back
    response.headers["X-Request-ID"] = event_id

    # Security headers
    response.headers["X-Content-Type-Options"]    = "nosniff"
    response.headers["X-Frame-Options"]           = "DENY"
    response.headers["Referrer-Policy"]           = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"]        = "camera=(), microphone=(), geolocation=()"
    if _IS_PRODUCTION:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

    log.info(
        "%s %s → %s  [%sms] event=%s",
        request.method, request.url.path,
        response.status_code, elapsed_ms, event_id,
    )

    # Write to per-user private activity log for authenticated API requests
    if request.url.path.startswith("/api/") and request.url.path != "/api/metrics":
        try:
            token = (request.headers.get("Authorization", "") or "").removeprefix("Bearer ").strip()
            user_id = _decode_token(token) if token else None
            if user_id:
                ip_raw  = request.client.host if request.client else "unknown"
                ip_hash = hashlib.sha256(ip_raw.encode()).hexdigest()[:16]
                from app.database import AsyncSessionLocal
                from app.routers.activity_log import record_request
                async with AsyncSessionLocal() as db:
                    await record_request(
                        db, user_id, event_id,
                        request.method, request.url.path,
                        response.status_code, elapsed_ms, ip_hash,
                    )
        except Exception:
            pass   # logging must never break the request

    return response

# API routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(domains.router)
app.include_router(server.router)
app.include_router(docker_mgr.router)
app.include_router(services.router)
app.include_router(admin_content.router)
app.include_router(container_proxy.router)
app.include_router(security.router)
app.include_router(activity_log.router)
app.include_router(marketplace.router)


@app.get("/api/metrics", include_in_schema=False)
async def prometheus_metrics():
    """Prometheus scrape endpoint — exposes host CPU/mem/disk gauges."""
    _cpu_gauge.set(psutil.cpu_percent())
    _mem_gauge.set(psutil.virtual_memory().percent)
    _disk_gauge.set(psutil.disk_usage("/").percent)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

# Serve built React frontend in production
STATIC_DIR = Path(__file__).parent.parent / "frontend" / "dist"
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        index = STATIC_DIR / "index.html"
        return FileResponse(index)
