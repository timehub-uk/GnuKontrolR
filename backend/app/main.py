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
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from pathlib import Path
from prometheus_client import (
    Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST,
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
else:
    # Default: ensure webpanel logger outputs INFO+ to stderr
    _handler = logging.StreamHandler()
    _handler.setLevel(logging.INFO)
    _handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s  %(message)s"
    ))
    logging.getLogger("webpanel").setLevel(logging.INFO)
    logging.getLogger("webpanel").addHandler(_handler)
# ─────────────────────────────────────────────────────────────────────────────

from app.database import init_db
from app.routers import auth, users, domains, server, docker_mgr, services, admin_content, container_proxy, security, activity_log, marketplace, ai, ai_admin, ai_containers, terminal, system_logs, dns, dns_sync, localdns, notifications, ip_rules, geo, scanner, email_security, fail2ban, cve, setup, crons, plans, compliance, mfa, data_retention, secondary_services


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


async def _apply_saved_panel_config() -> None:
    """Load panel_config.json from the data volume and apply to dns_helper module vars.

    This ensures PANEL_DOMAIN / SERVER_IP overrides set via the settings UI survive
    container restarts — Docker injects env vars from .env, but those may lag behind
    the values the admin set in the panel.
    """
    import json as _json
    import app.dns_helper as _dh
    _cfg_path = "/app/data/panel_config.json"
    try:
        with open(_cfg_path) as f:
            cfg = _json.load(f)
        if cfg.get("panel_domain"):
            _dh.PANEL_DOMAIN = cfg["panel_domain"]
        if cfg.get("server_ip"):
            _dh.SERVER_IP     = cfg["server_ip"]
            _dh._effective_ip = cfg["server_ip"]
        if cfg.get("acme_email"):
            os.environ["ACME_EMAIL"] = cfg["acme_email"]
        log.info("Panel config loaded from %s: domain=%s ip=%s",
                 _cfg_path, cfg.get("panel_domain"), cfg.get("server_ip"))
    except FileNotFoundError:
        pass  # first run — no saved config yet
    except Exception as exc:
        log.warning("Could not load panel_config.json: %s", exc)


async def _seed_consent_templates() -> None:
    """Seed default consent templates on first run."""
    from app.database import AsyncSessionLocal as _ASL
    from app.models.consent import ConsentTemplate
    from sqlalchemy import select as _sel

    templates = [
        {"consent_type": "privacy_policy", "version": "1.0", "title": "Privacy Policy Acceptance",
         "body": "I accept the Privacy Policy and agree to the processing of my personal data as described.", "is_required": True},
        {"consent_type": "terms_of_service", "version": "1.0", "title": "Terms of Service Acceptance",
         "body": "I accept the Terms of Service and agree to use the platform in accordance with them.", "is_required": True},
        {"consent_type": "cookies", "version": "1.0", "title": "Cookie Consent",
         "body": "I consent to the use of essential cookies required for platform functionality.", "is_required": True},
        {"consent_type": "marketing", "version": "1.0", "title": "Marketing Communications",
         "body": "I consent to receive marketing communications about platform features and updates.", "is_required": False},
        {"consent_type": "data_processing", "version": "1.0", "title": "Data Processing Consent",
         "body": "I consent to the processing of my personal data for the purposes of providing platform services.", "is_required": True},
    ]

    async with _ASL() as session:
        for t in templates:
            existing = await session.execute(
                _sel(ConsentTemplate).where(ConsentTemplate.consent_type == t["consent_type"])
            )
            if not existing.scalar_one_or_none():
                session.add(ConsentTemplate(**t))
        await session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Seed default consent templates
    try:
        await _seed_consent_templates()
    except Exception:
        pass
    await _apply_saved_panel_config()
    await _sync_acme_email()
    # Start DNS sync background task (reconciles DB ↔ PowerDNS every 180 s)
    task     = asyncio.create_task(dns_sync.dns_sync_loop(interval=180))
    # Check external IP every 60 s. On change: rewrite .env, full DNS sync, notify.
    ns_task  = asyncio.create_task(dns_sync.ip_check_loop(interval=60))
    # Start data retention scheduled cleanup every 24 hours
    ret_task = asyncio.create_task(data_retention.scheduled_cleanup())
    yield
    task.cancel()
    ns_task.cancel()
    ret_task.cancel()
    for t in (task, ns_task, ret_task):
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
async def _request_body_size_limit(request: Request, call_next):
    """Reject API requests with body larger than MAX_REQUEST_BODY_SIZE (default 10MB)."""
    MAX_BODY = int(os.environ.get("MAX_REQUEST_BODY_SIZE", str(10 * 1024 * 1024)))
    if request.method in ("POST", "PUT", "PATCH") and request.url.path.startswith("/api/"):
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit():
            if int(content_length) > MAX_BODY:
                return JSONResponse(
                    status_code=413,
                    content={"detail": f"Request body too large. Maximum size is {MAX_BODY // (1024*1024)}MB."},
                )
    response = await call_next(request)
    return response


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

    # Security headers (applied to every response including the SPA)
    response.headers["X-Content-Type-Options"]         = "nosniff"
    response.headers["X-Frame-Options"]                = "DENY"
    response.headers["Referrer-Policy"]                = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"]             = "camera=(), microphone=(), geolocation=(), payment=()"
    response.headers["Cross-Origin-Opener-Policy"]     = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"]   = "same-site"
    response.headers["Cross-Origin-Embedder-Policy"]   = "require-corp"
    # CSP — strict policy: no unsafe-inline for scripts (bundled JS only),
    # inline styles allowed for Tailwind/framer-motion, data URIs for images/fonts
    is_dev = not _IS_PRODUCTION
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        f"script-src 'self'{' \'unsafe-inline\'' if is_dev else ''}; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self' data:; "
        "connect-src 'self' wss: ws:; "
        "frame-ancestors 'none';"
    )
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

@app.middleware("http")
async def _csrf_protection(request: Request, call_next):
    """Lightweight CSRF protection for state-changing API requests.

    Requires X-Requested-With header on all POST/PUT/PATCH/DELETE requests
    to the API. This header is set automatically by fetch/XHR but cannot be
    added by simple HTML forms, preventing CSRF attacks.
    """
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/api/"):
        # Allow auth endpoints (login/register/MFA don't need CSRF)
        if not any(request.url.path.startswith(p) for p in ("/api/auth/token", "/api/auth/mfa-verify", "/api/auth/register")):
            x_requested_with = request.headers.get("X-Requested-With", "")
            if x_requested_with.lower() != "xmlhttprequest":
                log.warning("CSRF check failed for %s %s (missing X-Requested-With)", request.method, request.url.path)
                # Check if Authorization header is present as fallback proof of intent
                auth = request.headers.get("Authorization", "")
                if not auth.startswith("Bearer "):
                    return JSONResponse(status_code=403, content={"detail": "CSRF check failed"})
    response = await call_next(request)
    return response


@app.middleware("http")
async def _session_idle_timeout(request: Request, call_next):
    """Enforce session idle timeout for authenticated API requests.

    If the JWT was issued (iat) more than SESSION_IDLE_MINUTES ago, the
    request is rejected with 401. This prevents stale sessions from remaining
    active beyond the configured idle window.
    Default idle timeout: 60 minutes (configurable via SESSION_IDLE_MINUTES env).
    """
    _SESSION_IDLE_SECONDS = int(os.environ.get("SESSION_IDLE_MINUTES", "60")) * 60

    # Only check API routes (not static files, metrics, auth/login endpoints)
    exempt_paths = ("/api/metrics", "/api/auth/token", "/api/auth/mfa-verify", "/api/auth/register")
    if request.url.path.startswith("/api/") and not request.url.path.startswith(exempt_paths):
        auth_header = request.headers.get("Authorization", "") or ""
        token = auth_header.removeprefix("Bearer ").strip()
        if token:
            try:
                from jose import jwt as _jwt
                from app.auth import SECRET_KEY, ALGORITHM
                payload = _jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                now = __import__("time").time()
                iat = payload.get("iat", 0)
                if iat and (now - iat) > _SESSION_IDLE_SECONDS:
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Session expired due to inactivity. Please log in again."},
                        headers={"WWW-Authenticate": "Bearer"},
                    )
            except Exception:
                pass  # Let the endpoint's auth dependency handle invalid tokens

    response = await call_next(request)
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
app.include_router(notifications.router)
app.include_router(ip_rules.router)
app.include_router(geo.router)
app.include_router(scanner.router)
app.include_router(email_security.router)
app.include_router(fail2ban.router)
app.include_router(cve.router)
app.include_router(ai_containers.router)
app.include_router(setup.router)
app.include_router(crons.router)
app.include_router(plans.router)
app.include_router(compliance.router)
app.include_router(mfa.router)
app.include_router(data_retention.router)
app.include_router(secondary_services.router)


@app.get("/health", include_in_schema=False)
async def health():
    """Health check endpoint used by Docker HEALTHCHECK."""
    return {"status": "ok", "version": "1.0.0"}


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
