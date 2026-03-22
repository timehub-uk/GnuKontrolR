"""
Admin domain content viewer.
Superadmin can browse domain file trees and view file contents,
but ONLY after verifying a personal 6-digit support PIN.

PIN is stored as a bcrypt hash on the superadmin's user record.
A successful verify returns a short-lived JWT scoped to content-viewing.
"""
import os
import secrets
import mimetypes
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from passlib.context import CryptContext
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.auth import get_current_user, SECRET_KEY, ALGORITHM
from app.database import get_db
from app.models.user import User, Role

router = APIRouter(prefix="/api/admin/content", tags=["admin-content"])

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
SITES_ROOT = os.environ.get("SITES_ROOT", "/var/webpanel/sites")

PIN_TOKEN_EXPIRE_MINUTES = 15
PIN_TOKEN_SCOPE = "content_viewer"

ALLOWED_TEXT_EXTS = {
    ".php", ".html", ".htm", ".js", ".jsx", ".ts", ".tsx",
    ".css", ".scss", ".json", ".xml", ".yaml", ".yml", ".toml",
    ".env", ".ini", ".conf", ".txt", ".md", ".sh", ".py",
    ".rb", ".java", ".go", ".rs", ".sql", ".log", ".htaccess",
}
MAX_FILE_READ_BYTES = 512 * 1024  # 512 KB


# ────────────────────────────────────────────────────────────────────────────
# PIN helpers
# ────────────────────────────────────────────────────────────────────────────

def _hash_pin(pin: str) -> str:
    return pwd_ctx.hash(pin)


def _verify_pin(pin: str, hashed: str) -> bool:
    return pwd_ctx.verify(pin, hashed)


def _create_pin_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "scope": PIN_TOKEN_SCOPE,
        "exp": datetime.utcnow() + timedelta(minutes=PIN_TOKEN_EXPIRE_MINUTES),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _decode_pin_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("scope") != PIN_TOKEN_SCOPE:
            raise ValueError("wrong scope")
        return payload
    except (JWTError, ValueError):
        raise HTTPException(401, "PIN token invalid or expired. Please re-verify your PIN.")


# ────────────────────────────────────────────────────────────────────────────
# Path guard — never leave SITES_ROOT
# ────────────────────────────────────────────────────────────────────────────

def _safe_path(domain: str, rel: str = "") -> Path:
    root = Path(SITES_ROOT).resolve()
    target = (root / domain / rel).resolve()
    if not str(target).startswith(str(root)):
        raise HTTPException(400, "Path traversal detected")
    return target


# ────────────────────────────────────────────────────────────────────────────
# Models
# ────────────────────────────────────────────────────────────────────────────

class SetPinRequest(BaseModel):
    pin: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    current_pin: str | None = None  # required if PIN already set


class VerifyPinRequest(BaseModel):
    pin: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


# ────────────────────────────────────────────────────────────────────────────
# Require superadmin
# ────────────────────────────────────────────────────────────────────────────

async def require_superadmin(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.superadmin:
        raise HTTPException(403, "Superadmin only")
    return user


# ────────────────────────────────────────────────────────────────────────────
# Routes
# ────────────────────────────────────────────────────────────────────────────

@router.post("/pin/set")
async def set_support_pin(
    body: SetPinRequest,
    user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """Set or change the 6-digit support PIN for the superadmin account."""
    # If PIN already set, require old PIN first
    if user.support_pin_hash:
        if not body.current_pin:
            raise HTTPException(400, "Current PIN required to change PIN")
        if not _verify_pin(body.current_pin, user.support_pin_hash):
            raise HTTPException(403, "Current PIN incorrect")

    new_hash = _hash_pin(body.pin)
    await db.execute(
        update(User).where(User.id == user.id).values(support_pin_hash=new_hash)
    )
    await db.commit()
    return {"ok": True, "message": "Support PIN updated."}


@router.post("/pin/verify")
async def verify_support_pin(
    body: VerifyPinRequest,
    user: User = Depends(require_superadmin),
):
    """Verify the 6-digit PIN and receive a short-lived content-viewer token (15 min)."""
    if not user.support_pin_hash:
        raise HTTPException(400, "No support PIN set. Use /pin/set first.")
    if not _verify_pin(body.pin, user.support_pin_hash):
        raise HTTPException(403, "Incorrect PIN")
    token = _create_pin_token(user.id)
    return {
        "ok": True,
        "content_token": token,
        "expires_in": PIN_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.get("/domains")
async def list_viewable_domains(
    x_content_token: str = Header(..., alias="X-Content-Token"),
    user: User = Depends(require_superadmin),
):
    """List all domain directories available for browsing."""
    _decode_pin_token(x_content_token)
    root = Path(SITES_ROOT)
    if not root.exists():
        return {"domains": []}
    domains = [d.name for d in sorted(root.iterdir()) if d.is_dir()]
    return {"domains": domains}


@router.get("/domains/{domain}/files")
async def list_files(
    domain: str,
    path: str = "",
    x_content_token: str = Header(..., alias="X-Content-Token"),
    user: User = Depends(require_superadmin),
):
    """List files/directories inside a domain's file tree."""
    _decode_pin_token(x_content_token)
    target = _safe_path(domain, path)
    if not target.exists():
        raise HTTPException(404, "Path not found")
    if not target.is_dir():
        raise HTTPException(400, "Not a directory")

    entries = []
    for item in sorted(target.iterdir()):
        stat = item.stat()
        entries.append({
            "name": item.name,
            "type": "dir" if item.is_dir() else "file",
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "ext": item.suffix.lower(),
            "readable": item.suffix.lower() in ALLOWED_TEXT_EXTS,
        })
    return {
        "domain": domain,
        "path": path or "/",
        "entries": entries,
    }


@router.get("/domains/{domain}/read")
async def read_file(
    domain: str,
    path: str,
    x_content_token: str = Header(..., alias="X-Content-Token"),
    user: User = Depends(require_superadmin),
):
    """Read a text file from a domain's file tree."""
    _decode_pin_token(x_content_token)
    target = _safe_path(domain, path)
    if not target.exists():
        raise HTTPException(404, "File not found")
    if not target.is_file():
        raise HTTPException(400, "Not a file")
    if target.suffix.lower() not in ALLOWED_TEXT_EXTS:
        raise HTTPException(415, f"File type {target.suffix} not viewable")
    if target.stat().st_size > MAX_FILE_READ_BYTES:
        raise HTTPException(413, "File too large to view inline (>512 KB)")

    content = target.read_text(errors="replace")
    mime, _ = mimetypes.guess_type(str(target))
    return {
        "domain": domain,
        "path": path,
        "name": target.name,
        "content": content,
        "mime": mime or "text/plain",
        "size": target.stat().st_size,
    }
