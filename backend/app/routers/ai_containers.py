"""
AI Container Manager — provisions dedicated secure Docker containers for AI tools.

When a user requests an AI session and the tool (opencode / claude) is not
installed in the site container, a dedicated isolated container is created:

  Container name:  ai-{tool}-{username}-{user_id}
  Image:           python:3.12-slim  (lightweight, no web server bloat)
  Network:         webpanel_net  (internal only, same as site containers)
  Lifecycle:       started on demand, auto-stopped after session ends,
                   can be reused for subsequent sessions (already-running check)

Each AI container has:
  - The AI tool binary installed (opencode or claude)
  - No external port exposure
  - Memory + CPU limits
  - Runs on webpanel_net so the panel can communicate with it

Admin-only management; start/stop triggered automatically by ai.py.
"""
import asyncio
import logging
import os
import re
import secrets
import subprocess
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin, get_current_user
from app.database import get_db
from app.models.user import User, Role

router = APIRouter(prefix="/api/ai-containers", tags=["ai-containers"])
log = logging.getLogger("webpanel")

NETWORK_NAME  = "webpanel_net"
AI_IMAGE      = "python:3.12-slim"
AI_MEMORY_MB  = 512
AI_CPUS       = "1.0"

# Known AI tool installers
_TOOL_INSTALL = {
    "opencode": (
        "apt-get update -qq && apt-get install -y -qq curl nodejs npm git 2>/dev/null "
        "&& npm install -g @opencode-ai/opencode@latest --silent 2>/dev/null "
        "&& echo DONE"
    ),
    "claude": (
        "apt-get update -qq && apt-get install -y -qq curl nodejs npm git 2>/dev/null "
        "&& npm install -g @anthropic-ai/claude-code@latest --silent 2>/dev/null "
        "&& echo DONE"
    ),
}


def _ai_container_name(tool: str, username: str, user_id: int) -> str:
    safe_user = re.sub(r'[^a-zA-Z0-9]', '_', username)[:20]
    return f"ai-{tool}-{safe_user}-{user_id}"


def _run(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _container_running(name: str) -> bool:
    r = _run(["docker", "inspect", "--format", "{{.State.Running}}", name])
    return r.stdout.strip() == "true"


def _container_exists(name: str) -> bool:
    r = _run(["docker", "inspect", "--format", "{{.Name}}", name])
    return r.returncode == 0


async def _ensure_ai_container(tool: str, user: User) -> str:
    """
    Ensure a running AI container exists for this user+tool.
    Creates it (and installs the tool) if absent.
    Returns the container name.
    """
    if tool not in _TOOL_INSTALL:
        raise HTTPException(400, f"Unknown AI tool: {tool!r}. Supported: {list(_TOOL_INSTALL)}")

    name = _ai_container_name(tool, user.username if hasattr(user, 'username') else user.email.split('@')[0], user.id)
    loop = asyncio.get_running_loop()

    # Already running — reuse
    running = await loop.run_in_executor(None, lambda: _container_running(name))
    if running:
        log.info("AI container %s already running — reusing", name)
        return name

    # Exists but stopped — start it
    exists = await loop.run_in_executor(None, lambda: _container_exists(name))
    if exists:
        log.info("AI container %s exists (stopped) — starting", name)
        r = await loop.run_in_executor(None, lambda: _run(["docker", "start", name]))
        if r.returncode != 0:
            # Start failed — remove and recreate
            await loop.run_in_executor(None, lambda: _run(["docker", "rm", "-f", name]))
        else:
            return name

    # Create fresh container
    log.info("Creating AI container %s (tool=%s, user_id=%d)", name, tool, user.id)

    def _create():
        r = _run([
            "docker", "run", "-d",
            "--name", name,
            "--network", NETWORK_NAME,
            "--restart", "no",              # don't auto-restart — lifecycle managed by panel
            "--memory", f"{AI_MEMORY_MB}m",
            "--cpus", AI_CPUS,
            "--tmpfs", "/tmp:rw,size=128m",
            "--label", f"gnukontrolr.ai_tool={tool}",
            "--label", f"gnukontrolr.ai_user={user.id}",
            "--label", f"gnukontrolr.managed=true",
            AI_IMAGE,
            "sleep", "infinity",            # keep alive; AI tool started separately
        ], timeout=60)
        return r

    result = await loop.run_in_executor(None, _create)
    if result.returncode != 0:
        raise HTTPException(500, f"Failed to create AI container: {result.stderr[:200]}")

    # Install the AI tool inside the new container
    install_cmd = _TOOL_INSTALL[tool]
    log.info("Installing %s in container %s …", tool, name)

    def _install():
        r = _run(
            ["docker", "exec", name, "sh", "-c", install_cmd],
            timeout=300,
        )
        return r

    install_result = await loop.run_in_executor(None, _install)
    if "DONE" not in (install_result.stdout + install_result.stderr):
        log.warning("Tool install may have failed for %s: %s", name, install_result.stderr[:300])
        # Non-fatal — try to use it anyway; some npm warnings look like errors

    log.info("AI container %s ready", name)
    return name


async def _stop_ai_container(name: str) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: _run(["docker", "stop", name], timeout=15))


async def _remove_ai_container(name: str) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: _run(["docker", "rm", "-f", name], timeout=15))


# ── Public helpers (used by ai.py) ─────────────────────────────────────────────

async def get_or_create_ai_container(tool: str, user: User) -> str:
    """Called by ai.py — ensures container exists and returns name."""
    return await _ensure_ai_container(tool, user)


async def release_ai_container(tool: str, user: User) -> None:
    """Stop (but don't remove) the AI container after session ends."""
    name = _ai_container_name(
        tool,
        user.username if hasattr(user, 'username') else user.email.split('@')[0],
        user.id,
    )
    await _stop_ai_container(name)


# ── Admin management endpoints ─────────────────────────────────────────────────

@router.get("")
async def list_ai_containers(_=Depends(require_admin)):
    """List all managed AI containers."""
    loop = asyncio.get_running_loop()

    def _list():
        r = _run([
            "docker", "ps", "-a",
            "--filter", "label=gnukontrolr.managed=true",
            "--filter", "label=gnukontrolr.ai_tool",
            "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Labels}}",
        ])
        rows = []
        for line in r.stdout.strip().splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            name   = parts[0] if len(parts) > 0 else ""
            status = parts[1] if len(parts) > 1 else ""
            image  = parts[2] if len(parts) > 2 else ""
            labels_raw = parts[3] if len(parts) > 3 else ""
            labels = {}
            for lbl in labels_raw.split(","):
                if "=" in lbl:
                    k, v = lbl.split("=", 1)
                    labels[k.strip()] = v.strip()
            rows.append({
                "name": name, "status": status, "image": image,
                "tool":    labels.get("gnukontrolr.ai_tool", ""),
                "user_id": labels.get("gnukontrolr.ai_user", ""),
            })
        return rows

    containers = await loop.run_in_executor(None, _list)
    return {"containers": containers}


@router.delete("/{container_name}")
async def delete_ai_container(container_name: str, _=Depends(require_admin)):
    """Force-remove an AI container."""
    if not container_name.startswith("ai-"):
        raise HTTPException(400, "Only ai-* containers can be deleted via this endpoint")
    await _remove_ai_container(container_name)
    return {"ok": True}


@router.post("/{container_name}/stop")
async def stop_ai_container(container_name: str, _=Depends(require_admin)):
    """Stop an AI container."""
    if not container_name.startswith("ai-"):
        raise HTTPException(400, "Only ai-* containers can be managed via this endpoint")
    await _stop_ai_container(container_name)
    return {"ok": True}
