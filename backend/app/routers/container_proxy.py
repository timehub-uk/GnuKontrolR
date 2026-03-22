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
    return f"http://{container}:{CONTAINER_API_PORT}{path}"


async def _proxy_get(url: str) -> dict:
    headers = {"Authorization": f"Bearer {CONTAINER_API_TOKEN}"} if CONTAINER_API_TOKEN else {}
    async with httpx.AsyncClient(timeout=10) as client:
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
    async with httpx.AsyncClient(timeout=30) as client:
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
