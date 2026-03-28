"""WebPanel — FastAPI application entry point."""
import logging
import os
import time
import uuid
import asyncio
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from pathlib import Path
from prometheus_client import (
    Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST,
    CollectorRegistry, multiprocess
)
import psutil

log = logging.getLogger("webpanel")

# ── Debug level 5 → comprehensive.log ────────────────────────────────────────
_DEBUG_LEVEL = int(os.environ.get("DEBUG_LEVEL", "0"))
if _DEBUG_LEVEL >= 5:
    _comp_handler = logging.FileHandler("/tmp/comprehensive.log", mode="a")
    _comp_handler.setLevel(logging.DEBUG)
    _comp_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s  %(message)s"
    ))
    # Capture everything: webpanel, sqlalchemy, httpx, uvicorn, fastapi
    for _lg_name in ("webpanel", "sqlalchemy.engine", "httpx", "uvicorn", "fastapi"):
        _lg = logging.getLogger(_lg_name)
        _lg.setLevel(logging.DEBUG)
        _lg.addHandler(_comp_handler)
    logging.getLogger().setLevel(logging.DEBUG)
    logging.getLogger().addHandler(_comp_handler)
    log.info("DEBUG_LEVEL=5: comprehensive logging active → /tmp/comprehensive.log")
# ─────────────────────────────────────────────────────────────────────────────

from app.database import init_db
from app.routers import auth, users, domains, server, docker_mgr, services, admin_content, container_proxy, security, activity_log, marketplace, ai, ai_admin, terminal, system_logs, dns, dns_sync, localdns


# Prometheus metrics
_req_counter = Counter("webpanel_http_requests_total", "Total HTTP requests", ["method", "path"])
_cpu_gauge   = Gauge("webpanel_host_cpu_percent",  "Host CPU usage %")
_mem_gauge   = Gauge("webpanel_host_mem_percent",  "Host memory usage %")
_disk_gauge  = Gauge("webpanel_host_disk_percent", "Host disk usage %")


async def _sync_acme_email() -> None:
    """Read the superadmin's email from the DB and write it to .env as ACME_EMAIL.

    Traefik reads ACME_EMAIL from its environment (passed via docker-compose).
    This keeps the LE account email in sync with whoever owns the panel.
    """
    try:
        from app.database import AsyncSessionLocal
        from app.models.user import User, Role
        from sqlalchemy import select as _select
        import re as _re

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                _select(User).where(User.role == Role.superadmin, User.is_active == True).limit(1)
            )
            admin = result.scalar_one_or_none()
            if not admin or not admin.email or "@" not in admin.email:
                return
            email = admin.email

        env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
        env_path = os.path.normpath(env_path)
        if not os.path.exists(env_path):
            return

        with open(env_path) as f:
            content = f.read()

        if f"ACME_EMAIL={email}" in content:
            return  # already set

        new_content = _re.sub(r"^ACME_EMAIL=.*$", f"ACME_EMAIL={email}", content, flags=_re.MULTILINE)
        if new_content == content:
            new_content += f"\nACME_EMAIL={email}\n"

        with open(env_path, "w") as f:
            f.write(new_content)

        logging.getLogger("webpanel").info("ACME_EMAIL synced to %s from superadmin DB record", email)
    except Exception as exc:
        logging.getLogger("webpanel").warning("ACME_EMAIL sync failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await _sync_acme_email()
    # Start DNS sync background task (reconciles DB ↔ PowerDNS every 180 s)
    task     = asyncio.create_task(dns_sync.dns_sync_loop(interval=180))
    # Start NS IP sync background task (updates NS1/NS2/NS3 records every 3600 s)
    ns_task  = asyncio.create_task(dns_sync.ns_ip_sync_loop(interval=3600))
    yield
    task.cancel()
    ns_task.cancel()
    for t in (task, ns_task):
        try:
            await t
        except asyncio.CancelledError:
            pass


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

    # Accept a client-supplied ID only if it looks like a UUID (36 chars, safe characters)
    import re as _re
    _client_id = request.headers.get("X-Request-ID", "")
    event_id = _client_id if (_re.match(r'^[0-9a-f-]{36}$', _client_id)) else str(uuid.uuid4())
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

    if _DEBUG_LEVEL >= 5:
        _qs = str(request.url.query)
        log.debug(
            "[D5] %s %s%s → %s [%sms] headers=%s event=%s",
            request.method, request.url.path,
            ("?" + _qs) if _qs else "",
            response.status_code, elapsed_ms,
            dict(request.headers),
            event_id,
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
app.include_router(ai.router)
app.include_router(ai_admin.router)
app.include_router(terminal.router)
app.include_router(system_logs.router)
app.include_router(dns.router)
app.include_router(dns_sync.router)
app.include_router(localdns.router)


@app.get("/api/metrics", include_in_schema=False)
async def prometheus_metrics(request: Request):
    """Prometheus scrape endpoint — exposes host CPU/mem/disk gauges."""
    metrics_token = os.environ.get("METRICS_TOKEN", "")
    if metrics_token:
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {metrics_token}":
            return Response(status_code=401)
    _cpu_gauge.set(psutil.cpu_percent())
    _mem_gauge.set(psutil.virtual_memory().percent)
    _disk_gauge.set(psutil.disk_usage("/").percent)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

# Serve built React frontend in production
STATIC_DIR = Path(__file__).parent.parent / "frontend" / "dist"
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str, request: Request):
        # For API/WS paths: redirect no-trailing-slash to trailing-slash so the
        # actual API route gets a chance to match, rather than serving HTML.
        if full_path.startswith("api/") or full_path.startswith("ws/"):
            url = request.url
            url_str = str(url)
            # Only redirect if the URL does NOT already end with "/" to prevent infinite redirect loops
            if not url_str.endswith("/"):
                return RedirectResponse(url_str + "/", status_code=307)
        index = STATIC_DIR / "index.html"
        return FileResponse(index)
