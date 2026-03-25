"""
WebSocket terminal — spawns an interactive bash shell inside the container,
proxies stdin/stdout, and sends a custom MOTD with user + domain status.
Superadmin/admin only.
"""
import asyncio
import os
import pty
import struct
import fcntl
import termios
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models.user import User, Role
from app.models.domain import Domain, DomainStatus

router = APIRouter(prefix="/api/terminal", tags=["terminal"])


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


@router.websocket("/ws")
async def terminal_ws(websocket: WebSocket, db: AsyncSession = Depends(get_db)):
    """
    Authenticated WebSocket terminal.
    - Accepts token via ?token= query param (browsers can't set WS headers).
    - Spawns /bin/bash in a PTY; proxies data bidirectionally.
    - Sends MOTD on connect.
    """
    token = websocket.query_params.get("token", "")
    # Validate token before accepting
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
        "/bin/bash", "--login",
        stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
        close_fds=True,
        env={**os.environ, "TERM": "xterm-256color", "HOME": "/root", "USER": "root"},
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
