"""System Logs router — streams logs from named Docker containers."""
import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from app.auth import require_admin
from app.docker_client import container_logs as docker_container_logs
from app.models.user import User

router = APIRouter(prefix="/api/logs", tags=["logs"])
log = logging.getLogger("webpanel.system_logs")

# Map source ID → Docker container name
SOURCES = {
    "panel":     "webpanel_api",
    "postgres":  "webpanel_postgres",
    "redis":     "webpanel_redis",
    "mysql":     "webpanel_mysql",
    "traefik":   "webpanel_traefik",
    "postfix":   "webpanel_postfix",
    "dovecot":   "webpanel_dovecot",
}


async def _docker_logs(container: str, tail: int = 200, search: str = "") -> list[str]:
    """Fetch container logs via Docker API and return lines."""
    try:
        raw = await docker_container_logs(container, tail=tail)
        lines = raw.splitlines()
        if search:
            lsearch = search.lower()
            lines = [l for l in lines if lsearch in l.lower()]
        return lines
    except Exception as e:
        log.exception("Error fetching docker logs for %s", container)
        return ["[error] Internal server error retrieving logs"]


@router.get("/sources")
async def list_sources(_: User = Depends(require_admin)):
    """Return available log sources."""
    return {"sources": [{"id": k, "label": k.capitalize()} for k in SOURCES]}


@router.get("/{source}")
async def get_logs(
    source: str,
    tail: int = Query(200, ge=10, le=2000),
    search: str = Query("", max_length=200),
    _: User = Depends(require_admin),
):
    """Fetch logs for a named source (system service or domain container)."""
    # Domain containers: source like "domain:example.com"
    if source.startswith("domain:"):
        domain = source.split(":", 1)[1]
        container = f"site_{domain.replace('.', '_').replace('-', '_')}"
    elif source in SOURCES:
        container = SOURCES[source]
    else:
        raise HTTPException(404, f"Unknown log source: {source}")

    lines = await _docker_logs(container, tail=tail, search=search)
    return {"source": source, "container": container, "lines": lines, "count": len(lines)}


@router.get("/{source}/download")
async def download_logs(
    source: str,
    tail: int = Query(1000, ge=100, le=10000),
    _: User = Depends(require_admin),
):
    """Download logs as a plain text file."""
    if source.startswith("domain:"):
        container = "site_" + source.split(":", 1)[1].replace(".", "_").replace("-", "_")
    elif source in SOURCES:
        container = SOURCES[source]
    else:
        raise HTTPException(404, f"Unknown log source: {source}")

    lines = await _docker_logs(container, tail=tail)
    content = "\n".join(lines)
    filename = f"{source.replace(':', '_')}.log"
    return PlainTextResponse(
        content,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
