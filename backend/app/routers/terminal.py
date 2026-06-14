"""
WebSocket terminal — spawns an interactive bash shell inside the container,
proxies stdin/stdout, and sends a custom MOTD with user + domain status.
Superadmin/admin only.

M12: WebSocket connections use a short-lived token (30s TTL) obtained from a
REST endpoint, instead of passing the full JWT in the query string.  This
prevents credential leakage via server logs, Referer headers, or browser
history.
"""
import asyncio
import json
import os
import pty
import secrets
import struct
import fcntl
import termios

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.cache import get_redis
from app.database import get_db
from app.models.user import User, Role
from app.models.domain import Domain, DomainStatus

router = APIRouter(prefix="/api/terminal", tags=["terminal"])

_WS_TOKEN_TTL = 30  # seconds — short-lived WS token


async def _build_motd(user: User, db: AsyncSession) -> str:
    """Build a colourful MOTD from user info and domain status."""
    # Fetch domain counts
    result = await db.execute(
        select(Domain).where(Domain.owner_id == user.id)
        if user.role not in (Role.superadmin, Role.admin)
        else select(Domain)
    )
    all_domains = result.scalars().all()
    active  = sum(1 for d in all_domains if d.status == DomainStatus.active)
    total   = len(all_domains)

    reset  = "\x1b[0m"
    bold   = "\x1b[1m"
    dim    = "\x1b[2m"
    cyan   = "\x1b[36m"
    green  = "\x1b[32m"
    yellow = "\x1b[33m"
    magenta= "\x1b[35m"
    white  = "\x1b[97m"

    role_color = {
        "superadmin": "\x1b[35m",   # magenta
        "admin":      "\x1b[34m",   # blue
        "reseller":   "\x1b[33m",   # yellow
        "user":       "\x1b[32m",   # green
    }.get(user.role.value if hasattr(user.role, "value") else str(user.role), white)

    lines = [
        "",
        f"  {bold}{cyan}GnuKontrolR{reset}  {dim}Web Hosting Control Panel{reset}",
        f"  {'─' * 40}",
        f"  {white}User   {reset}  {bold}{user.username}{reset}  "
        f"{role_color}[{user.role.value if hasattr(user.role, 'value') else user.role}]{reset}",
        f"  {white}Email  {reset}  {dim}{user.email or '—'}{reset}",
        f"  {white}Domains{reset}  {green}{active} active{reset} / {yellow}{total} total{reset}",
        f"  {'─' * 40}",
        f"  {dim}Type {bold}exit{reset}{dim} to close the session.{reset}",
        "",
    ]
    return "\r\n".join(lines) + "\r\n"


@router.get("/token")
async def generate_ws_token(user: User = Depends(get_current_user)):
    """M12: Exchange your authenticated session for a short-lived WebSocket token
    (30-second TTL).  The frontend uses this token in ?ws_token= instead of
    passing the real JWT in the query string."""
    if user.role not in (Role.superadmin, Role.admin):
        raise HTTPException(403, "Only admins and superadmins can access the terminal")

    ws_token = secrets.token_urlsafe(32)
    r = await get_redis()
    if r is not None:
        try:
            await r.setex(f"ws_token:{ws_token}", _WS_TOKEN_TTL, user.id)
        except Exception:
            pass
    return JSONResponse({"ws_token": ws_token, "expires_in": _WS_TOKEN_TTL})


@router.websocket("/ws")
async def terminal_ws(websocket: WebSocket, db: AsyncSession = Depends(get_db)):
    """
    Authenticated WebSocket terminal.
    - Accepts short-lived token via ?ws_token= query param (M12).
    - Spawns /bin/bash in a PTY; proxies data bidirectionally.
    - Sends MOTD on connect.
    """
    ws_token = websocket.query_params.get("ws_token", "")

    # Validate short-lived token from Redis
    user_id = None
    r = await get_redis()
    if r is not None:
        try:
            user_id_str = await r.get(f"ws_token:{ws_token}")
            if user_id_str:
                user_id = int(user_id_str)
                await r.delete(f"ws_token:{ws_token}")  # single-use
        except Exception:
            pass

    if not user_id:
        # M12: Fallback: accept a full JWT via ?token= for backward compat during
        # rollout (remove this fallback in a future release).
        token = websocket.query_params.get("token", "")
        if token:
            from app.auth import _decode_token
            user_id = _decode_token(token)

    if not user_id:
        await websocket.close(code=4001)
        return

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        await websocket.close(code=4001)
        return

    # Only admins and superadmins get shell access
    if user.role not in (Role.superadmin, Role.admin):
        await websocket.close(code=4003)
        return

    await websocket.accept()

    # Send MOTD
    try:
        motd = await _build_motd(user, db)
        await websocket.send_text(motd)
    except Exception:
        pass

    # Spawn PTY + bash
    master_fd, slave_fd = pty.openpty()
    _set_winsize(master_fd, 24, 80)

    proc = await asyncio.create_subprocess_exec(
        "/bin/bash", "--login", "+m",
        stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
        close_fds=True,
        env={**os.environ, "TERM": "xterm-256color", "HOME": "/app", "USER": "panelapi"},
    )
    os.close(slave_fd)

    loop = asyncio.get_running_loop()

    async def read_pty():
        """Read from PTY and forward to WebSocket."""
        while True:
            try:
                data = await loop.run_in_executor(None, _read_fd, master_fd)
                if not data:
                    break
                await websocket.send_text(data.decode("utf-8", errors="replace"))
            except Exception:
                break

    async def read_ws():
        """Read from WebSocket and write to PTY."""
        while True:
            try:
                msg = await websocket.receive_text()
                # Resize message: {"type":"resize","cols":N,"rows":M}
                try:
                    d = json.loads(msg)
                    if d.get("type") == "resize":
                        _set_winsize(master_fd, d.get("rows", 24), d.get("cols", 80))
                        continue
                except (json.JSONDecodeError, TypeError):
                    pass
                os.write(master_fd, msg.encode("utf-8"))
            except (WebSocketDisconnect, RuntimeError):
                break
            except Exception:
                break

    pty_task = asyncio.create_task(read_pty())
    ws_task  = asyncio.create_task(read_ws())

    done, pending = await asyncio.wait(
        [pty_task, ws_task],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for t in pending:
        t.cancel()

    try:
        proc.kill()
    except Exception:
        pass
    try:
        os.close(master_fd)
    except Exception:
        pass
    try:
        await websocket.close()
    except Exception:
        pass


def _set_winsize(fd: int, rows: int, cols: int):
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    except Exception:
        pass


def _read_fd(fd: int) -> bytes:
    try:
        return os.read(fd, 1024)
    except OSError:
        return b""
