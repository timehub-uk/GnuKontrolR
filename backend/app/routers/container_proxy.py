"""
Proxy to individual container internal APIs (port 9000).
Allows the main panel to communicate with each domain container
over the internal webpanel_net Docker network.
"""
import os
import httpx
from app.http_client import panel_client
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models.user import User, Role
from app.models.domain import Domain

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


async def _assert_domain_access(domain: str, user: User, db: AsyncSession) -> None:
    """Raise 403 if user doesn't own domain (admins/superadmins bypass)."""
    if user.role in (Role.superadmin, Role.admin):
        return
    result = await db.execute(
        select(Domain).where(Domain.name == domain, Domain.owner_id == user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(403, "Access denied: domain not owned by you")


async def _proxy_get(url: str) -> dict:
    headers = {"Authorization": f"Bearer {CONTAINER_API_TOKEN}"} if CONTAINER_API_TOKEN else {}
    async with panel_client(timeout=10, verify=_TLS_VERIFY) as client:
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
    async with panel_client(timeout=30, verify=_TLS_VERIFY) as client:
        try:
            r = await client.post(url, json=body, headers=headers)
            r.raise_for_status()
            return r.json()
        except httpx.ConnectError:
            raise HTTPException(503, "Container not reachable")
        except Exception as exc:
            raise HTTPException(500, str(exc))


@router.get("/{domain}/health")
async def container_health(domain: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _assert_domain_access(domain, user, db)
    return await _proxy_get(_container_api_url(domain, "/health"))


@router.get("/{domain}/info")
async def container_info(domain: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _assert_domain_access(domain, user, db)
    return await _proxy_get(_container_api_url(domain, "/info"))


@router.get("/{domain}/services")
async def container_services(domain: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _assert_domain_access(domain, user, db)
    return await _proxy_get(_container_api_url(domain, "/services"))


class ServiceActionBody(BaseModel):
    action: str  # start | stop | restart | status


@router.post("/{domain}/services/{program}")
async def container_service_action(
    domain: str,
    program: str,
    body: ServiceActionBody,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _assert_domain_access(domain, user, db)
    return await _proxy_post(
        _container_api_url(domain, f"/services/{program}"),
        {"action": body.action},
    )


@router.get("/{domain}/files")
async def container_files(
    domain: str,
    path: str = "",
    area: str = "public",   # public | uploads | private
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List directory contents.  area=public → /var/www/html, uploads, private."""
    await _assert_domain_access(domain, user, db)
    area = area if area in ("public", "uploads", "private") else "public"
    qs = f"?path={path}" if path else ""
    return await _proxy_get(_container_api_url(domain, f"/files/{area}{qs}"))


class FileWriteBody(BaseModel):
    path: str
    content: str


@router.get("/{domain}/files/read")
async def container_file_read(
    domain: str,
    path: str,
    area: str = "public",
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Read a text file's content (≤ 512 KB)."""
    await _assert_domain_access(domain, user, db)
    area = area if area in ("public", "uploads", "private") else "public"
    return await _proxy_get(_container_api_url(domain, f"/files/{area}/read?path={path}"))


@router.post("/{domain}/files/write")
async def container_file_write(
    domain: str,
    body: FileWriteBody,
    area: str = "public",
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Write / create a text file."""
    await _assert_domain_access(domain, user, db)
    area = area if area in ("public", "uploads", "private") else "public"
    return await _proxy_post(
        _container_api_url(domain, f"/files/{area}/write"),
        {"path": body.path, "content": body.content},
    )


@router.delete("/{domain}/files")
async def container_file_delete(
    domain: str,
    path: str,
    area: str = "public",
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a file or directory."""
    await _assert_domain_access(domain, user, db)
    area = area if area in ("public", "uploads", "private") else "public"
    headers = {"Authorization": f"Bearer {CONTAINER_API_TOKEN}"} if CONTAINER_API_TOKEN else {}
    async with panel_client(timeout=15, verify=_TLS_VERIFY) as client:
        try:
            r = await client.delete(
                _container_api_url(domain, f"/files/{area}?path={path}"),
                headers=headers,
            )
            r.raise_for_status()
            return r.json()
        except httpx.ConnectError:
            raise HTTPException(503, "Container not reachable")
        except Exception as exc:
            raise HTTPException(500, str(exc))


class MkdirBody(BaseModel):
    path: str


@router.post("/{domain}/files/mkdir")
async def container_mkdir(
    domain: str,
    body: MkdirBody,
    area: str = "public",
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a directory (and parents)."""
    await _assert_domain_access(domain, user, db)
    area = area if area in ("public", "uploads", "private") else "public"
    return await _proxy_post(
        _container_api_url(domain, f"/files/{area}/mkdir"),
        {"path": body.path},
    )


@router.post("/{domain}/files/upload")
async def container_file_upload(
    domain: str,
    request: Request,
    area: str = "public",
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Forward a multipart file upload to the container (includes ClamAV scan)."""
    await _assert_domain_access(domain, user, db)
    if area not in ("public", "uploads", "private"):
        area = "public"
    headers = {"Authorization": f"Bearer {CONTAINER_API_TOKEN}"} if CONTAINER_API_TOKEN else {}
    body = await request.body()
    content_type = request.headers.get("content-type", "multipart/form-data")
    async with panel_client(timeout=60, verify=_TLS_VERIFY) as client:
        try:
            r = await client.post(
                _container_api_url(domain, f"/files/{area}/upload"),
                content=body,
                headers={**headers, "content-type": content_type},
            )
            if r.status_code == 400:
                raise HTTPException(400, r.json().get("error", "Upload rejected"))
            r.raise_for_status()
            return r.json()
        except HTTPException:
            raise
        except httpx.ConnectError:
            raise HTTPException(503, "Container not reachable")
        except Exception as exc:
            raise HTTPException(500, str(exc))


class ExecBody(BaseModel):
    command: str  # whitelisted command key


@router.post("/{domain}/exec")
async def container_exec(domain: str, body: ExecBody, _=Depends(require_admin)):
    """Run a whitelisted command inside the container (admin only)."""
    return await _proxy_post(_container_api_url(domain, "/exec"), {"command": body.command})


# ── Config backup / restore proxy ─────────────────────────────────────────────

@router.get("/{domain}/backups/{area}")
async def container_list_backups(domain: str, area: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """List rolling config snapshots for a given area (nginx/php/env/ssl)."""
    await _assert_domain_access(domain, user, db)
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
async def sftp_create(domain: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    Generate an Ed25519 key pair and create/reset the SFTP-only OS user.
    Returns the private key (PEM) — only returned this once.
    """
    await _assert_domain_access(domain, user, db)
    return await _proxy_post(_container_api_url(domain, "/sftp/create"), {})


@router.get("/{domain}/sftp/info")
async def sftp_info(domain: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Return SFTP connection info for the domain (host, port, user)."""
    await _assert_domain_access(domain, user, db)
    return await _proxy_get(_container_api_url(domain, "/sftp/info"))


# ── SSL certificate upload proxy ──────────────────────────────────────────────

class SslUploadBody(BaseModel):
    cert: str = ""
    key: str = ""


@router.post("/{domain}/secure/ssl")
async def upload_ssl(domain: str, body: SslUploadBody, _=Depends(require_admin)):
    """Upload a custom SSL certificate + private key to the domain container."""
    return await _proxy_post(_container_api_url(domain, "/secure/ssl"), {"cert": body.cert, "key": body.key})


# ── Site backup proxy ──────────────────────────────────────────────────────────

@router.get("/{domain}/site-backup/list")
async def list_site_backups(domain: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """List available full-site backups for the domain container."""
    await _assert_domain_access(domain, user, db)
    return await _proxy_get(_container_api_url(domain, "/site-backup/list"))


class SiteBackupCreateBody(BaseModel):
    type: str = "website"   # website | files | db | full


@router.post("/{domain}/site-backup/create")
async def create_site_backup(
    domain: str,
    body: SiteBackupCreateBody = SiteBackupCreateBody(),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a site backup in the domain container.  type: website|files|db|full.
    Records the backup in the DB with a unique ID and CSC verification token.
    """
    await _assert_domain_access(domain, user, db)
    result = await _proxy_post(_container_api_url(domain, "/site-backup/create"), {"type": body.type})

    # Record in DB with unique_id + csc_token for verification
    from app.models.site_backup import SiteBackup
    record = SiteBackup(
        domain=domain,
        filename=result.get("filename", ""),
        backup_type=body.type,
        size=result.get("size"),
        created_by=user.id,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    return {
        **result,
        "unique_id":  record.unique_id,
        "csc_token":  record.csc_token,
        "db_id":      record.id,
    }


@router.delete("/{domain}/site-backup/{filename}")
async def delete_site_backup(domain: str, filename: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Delete a named site backup file from the domain container."""
    await _assert_domain_access(domain, user, db)
    headers = {"Authorization": f"Bearer {CONTAINER_API_TOKEN}"} if CONTAINER_API_TOKEN else {}
    async with panel_client(timeout=15, verify=_TLS_VERIFY) as client:
        try:
            r = await client.delete(
                _container_api_url(domain, f"/site-backup/{filename}"), headers=headers
            )
            r.raise_for_status()
            return r.json()
        except httpx.ConnectError:
            raise HTTPException(503, "Container not reachable")
        except Exception as exc:
            raise HTTPException(500, str(exc))


@router.get("/{domain}/site-backup/download/{filename}")
async def download_site_backup(domain: str, filename: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Stream a site backup file from the domain container."""
    await _assert_domain_access(domain, user, db)
    from fastapi.responses import StreamingResponse
    headers = {"Authorization": f"Bearer {CONTAINER_API_TOKEN}"} if CONTAINER_API_TOKEN else {}
    async with panel_client(timeout=120, verify=_TLS_VERIFY) as client:
        try:
            r = await client.get(
                _container_api_url(domain, f"/site-backup/download/{filename}"), headers=headers
            )
            r.raise_for_status()
            return StreamingResponse(
                iter([r.content]),
                media_type="application/octet-stream",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        except httpx.ConnectError:
            raise HTTPException(503, "Container not reachable")
        except Exception as exc:
            raise HTTPException(500, str(exc))


@router.delete("/{domain}/sftp/revoke")
async def sftp_revoke(domain: str, _=Depends(require_admin)):
    """Revoke SFTP access — removes OS user and keys."""
    headers = {"Authorization": f"Bearer {CONTAINER_API_TOKEN}"} if CONTAINER_API_TOKEN else {}
    async with panel_client(timeout=15, verify=_TLS_VERIFY) as client:
        try:
            r = await client.delete(
                _container_api_url(domain, "/sftp/revoke"), headers=headers
            )
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            raise HTTPException(502, str(exc))
