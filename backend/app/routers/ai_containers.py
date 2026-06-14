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
Uses the Docker HTTP API via docker-api-proxy (no docker.sock).
"""
import asyncio
import logging
import os
import re
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin, get_current_user
from app.database import get_db
from app.docker_client import (
    list_containers, inspect_container, create_container,
    start_container, stop_container, remove_container,
    exec_run,
)
from app.models.user import User, Role

router = APIRouter(prefix="/api/ai-containers", tags=["ai-containers"])
log = logging.getLogger("webpanel")

NETWORK_NAME  = "webpanel_net"
AI_IMAGE      = "python:3.12-slim"
AI_MEMORY_MB  = 512
AI_CPUS       = 1.0

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


async def _container_running(name: str) -> bool:
    try:
        info = await inspect_container(name)
        return info.get("State", {}).get("Running", False)
    except Exception:
        return False


async def _container_exists(name: str) -> bool:
    try:
        await inspect_container(name)
        return True
    except Exception:
        return False


async def _ensure_ai_container(tool: str, user: User) -> str:
    """
    Ensure a running AI container exists for this user+tool.
    Creates it (and installs the tool) if absent.
    Returns the container name.
    """
    if tool not in _TOOL_INSTALL:
        raise HTTPException(400, f"Unknown AI tool: {tool!r}. Supported: {list(_TOOL_INSTALL)}")

    name = _ai_container_name(
        tool,
        user.username if hasattr(user, 'username') else user.email.split('@')[0],
        user.id,
    )

    # Already running — reuse
    running = await _container_running(name)
    if running:
        log.info("AI container %s already running — reusing", name)
        return name

    # Exists but stopped — start it
    exists = await _container_exists(name)
    if exists:
        log.info("AI container %s exists (stopped) — starting", name)
        try:
            await start_container(name)
            return name
        except Exception:
            # Start failed — remove and recreate
            try:
                await remove_container(name, force=True)
            except Exception:
                pass

    # Create fresh container
    log.info("Creating AI container %s (tool=%s, user_id=%d)", name, tool, user.id)

    try:
        result = await create_container(
            name=name,
            image=AI_IMAGE,
            network=NETWORK_NAME,
            mem_limit=f"{AI_MEMORY_MB}m",
            cpus=AI_CPUS,
            tmpfs={"/tmp": "rw,size=128m"},
            labels={
                "gnukontrolr.ai_tool": tool,
                "gnukontrolr.ai_user": str(user.id),
                "gnukontrolr.managed": "true",
            },
            cmd=["sleep", "infinity"],  # keep alive; AI tool started separately
            host_config={
                "RestartPolicy": {"Name": "no"},  # lifecycle managed by panel
            },
        )
        log.info("Container created: %s", result)
        await start_container(name)
    except Exception as e:
        raise HTTPException(500, f"Failed to create AI container: {e}")

    # Install the AI tool inside the new container
    install_cmd = _TOOL_INSTALL[tool]
    log.info("Installing %s in container %s …", tool, name)

    try:
        exit_code, output = await exec_run(name, ["sh", "-c", install_cmd])
        if "DONE" not in output:
            log.warning("Tool install may have failed for %s: %s", name, output[:300])
        else:
            log.info("Tool %s installed in %s (exit=%d)", tool, name, exit_code)
    except Exception as e:
        log.warning("Tool install error for %s: %s", name, e)

    log.info("AI container %s ready", name)
    return name


async def _stop_ai_container(name: str) -> None:
    try:
        await stop_container(name, timeout=15)
    except Exception as e:
        log.warning("Failed to stop AI container %s: %s", name, e)


async def _remove_ai_container(name: str) -> None:
    try:
        await remove_container(name, force=True)
    except Exception as e:
        log.warning("Failed to remove AI container %s: %s", name, e)


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
    try:
        containers = await list_containers(
            all=True,
            filters={"label": ["gnukontrolr.managed=true"]},
        )
    except Exception as e:
        raise HTTPException(500, f"Docker error: {e}")

    rows = []
    for c in containers:
        labels = c.get("Labels", {})
        names = c.get("Names", [])
        name = names[0].lstrip("/") if names else c.get("Id", "")[:12]
        status = c.get("Status", "")
        image = c.get("Image", "")
        rows.append({
            "name": name,
            "status": status,
            "image": image,
            "tool":    labels.get("gnukontrolr.ai_tool", ""),
            "user_id": labels.get("gnukontrolr.ai_user", ""),
        })
    return {"containers": rows}


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
