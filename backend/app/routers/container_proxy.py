"""
Proxy to individual container internal APIs (port 9000).
Allows the main panel to communicate with each domain container
over the internal webpanel_net Docker network.
"""
import os
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth import get_current_user, require_admin
from app.models.user import User

router = APIRouter(prefix="/api/container", tags=["container-proxy"])

CONTAINER_API_PORT = 9000
CONTAINER_API_TOKEN = os.environ.get("CONTAINER_API_TOKEN", "")


def _container_api_url(domain: str, path: str) -> str:
    container = "site_" + domain.replace(".", "_").replace("-", "_")
    return f"https://{container}:{CONTAINER_API_PORT}{path}"


# Self-signed certs on container APIs — verify=False is intentional.
# Traffic is encrypted (TLS) and authenticated via the shared Bearer token.
# The Docker internal bridge network is not reachable from the public internet.
_TLS_VERIFY = False


async def _proxy_get(url: str) -> dict:
    headers = {"Authorization": f"Bearer {CONTAINER_API_TOKEN}"} if CONTAINER_API_TOKEN else {}
    async with httpx.AsyncClient(timeout=10, verify=_TLS_VERIFY) as client:
        try:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            return r.json()
        except httpx.ConnectError:
            raise HTTPException(503, "Container not reachable (is it running?)")
        except httpx.TimeoutException:
            raise HTTPException(504, "Container API timed out")
        except Exception as exc:
            raise HTTPException(500, str(exc))


async def _proxy_post(url: str, body: dict) -> dict:
    headers = {"Authorization": f"Bearer {CONTAINER_API_TOKEN}"} if CONTAINER_API_TOKEN else {}
    async with httpx.AsyncClient(timeout=30, verify=_TLS_VERIFY) as client:
        try:
            r = await client.post(url, json=body, headers=headers)
            r.raise_for_status()
            return r.json()
        except httpx.ConnectError:
            raise HTTPException(503, "Container not reachable")
        except Exception as exc:
            raise HTTPException(500, str(exc))


@router.get("/{domain}/health")
async def container_health(domain: str, _=Depends(get_current_user)):
    return await _proxy_get(_container_api_url(domain, "/health"))


@router.get("/{domain}/info")
async def container_info(domain: str, _=Depends(get_current_user)):
    return await _proxy_get(_container_api_url(domain, "/info"))


@router.get("/{domain}/services")
async def container_services(domain: str, _=Depends(get_current_user)):
    return await _proxy_get(_container_api_url(domain, "/services"))


class ServiceActionBody(BaseModel):
    action: str  # start | stop | restart | status


@router.post("/{domain}/services/{program}")
async def container_service_action(
    domain: str,
    program: str,
    body: ServiceActionBody,
    _=Depends(get_current_user),
):
    return await _proxy_post(
        _container_api_url(domain, f"/services/{program}"),
        {"action": body.action},
    )


@router.get("/{domain}/files")
async def container_files(domain: str, path: str = "", _=Depends(get_current_user)):
    url = _container_api_url(domain, "/files")
    if path:
        url += f"?path={path}"
    return await _proxy_get(url)


class ExecBody(BaseModel):
    command: str  # whitelisted command key


@router.post("/{domain}/exec")
async def container_exec(domain: str, body: ExecBody, _=Depends(require_admin)):
    """Run a whitelisted command inside the container (admin only)."""
    return await _proxy_post(_container_api_url(domain, "/exec"), {"command": body.command})


# ── Config backup / restore proxy ─────────────────────────────────────────────

@router.get("/{domain}/backups/{area}")
async def container_list_backups(domain: str, area: str, _=Depends(get_current_user)):
    """List rolling config snapshots for a given area (nginx/php/env/ssl)."""
    return await _proxy_get(_container_api_url(domain, f"/backups/{area}"))


class RestoreBody(BaseModel):
    filename: str
    ts: int


@router.post("/{domain}/restore/{area}")
async def container_restore_backup(
    domain: str,
    area: str,
    body: RestoreBody,
    _=Depends(require_admin),
):
    """Restore a config snapshot (admin only)."""
    return await _proxy_post(
        _container_api_url(domain, f"/restore/{area}"),
        {"filename": body.filename, "ts": body.ts},
    )


# ── SFTP key management proxy ──────────────────────────────────────────────────

@router.post("/{domain}/sftp/create")
async def sftp_create(domain: str, _=Depends(get_current_user)):
    """
    Generate an Ed25519 key pair and create/reset the SFTP-only OS user.
    Returns the private key (PEM) — only returned this once.
    """
    return await _proxy_post(_container_api_url(domain, "/sftp/create"), {})


@router.get("/{domain}/sftp/info")
async def sftp_info(domain: str, _=Depends(get_current_user)):
    """Return SFTP connection info for the domain (host, port, user)."""
    return await _proxy_get(_container_api_url(domain, "/sftp/info"))


@router.delete("/{domain}/sftp/revoke")
async def sftp_revoke(domain: str, _=Depends(require_admin)):
    """Revoke SFTP access — removes OS user and keys."""
    headers = {"Authorization": f"Bearer {CONTAINER_API_TOKEN}"} if CONTAINER_API_TOKEN else {}
    async with httpx.AsyncClient(timeout=15, verify=_TLS_VERIFY) as client:
        try:
            r = await client.delete(
                _container_api_url(domain, "/sftp/revoke"), headers=headers
            )
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            raise HTTPException(502, str(exc))
