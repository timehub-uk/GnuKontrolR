"""WebPanel — FastAPI application entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from prometheus_client import (
    Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST,
    CollectorRegistry, multiprocess
)
import psutil

from app.database import init_db
from app.routers import auth, users, domains, server, docker_mgr, services, admin_content, container_proxy


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(domains.router)
app.include_router(server.router)
app.include_router(docker_mgr.router)
app.include_router(services.router)
app.include_router(admin_content.router)
app.include_router(container_proxy.router)


@app.get("/api/metrics", include_in_schema=False)
async def prometheus_metrics():
    """Prometheus scrape endpoint — exposes host CPU/mem/disk gauges."""
    _cpu_gauge.set(psutil.cpu_percent())
    _mem_gauge.set(psutil.virtual_memory().percent)
    _disk_gauge.set(psutil.disk_usage("/").percent)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

# Serve built React frontend in production
STATIC_DIR = Path(__file__).parent.parent.parent / "frontend" / "dist"
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        index = STATIC_DIR / "index.html"
        return FileResponse(index)
