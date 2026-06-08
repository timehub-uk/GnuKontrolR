"""First-time setup wizard — status, completion, and cron creation."""
import asyncio
import logging
import os
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.setup import SetupState
from app.models.user import User
from app.auth import get_current_user, require_superadmin

log = logging.getLogger("webpanel")

router = APIRouter(prefix="/api/setup", tags=["setup"])

_CRON_HEADER = "# GnuKontrolR — auto-managed crons (DO NOT EDIT BELOW THIS LINE)"
_CRON_FOOTER = "# GnuKontrolR — end auto-managed crons"


def _read_crontab() -> str:
    try:
        result = os.popen("crontab -l 2>/dev/null").read()
        return result.strip() or ""
    except Exception:
        return ""


def _write_crontab(content: str) -> None:
    proc = os.popen("crontab -", "w")
    proc.write(content + "\n")
    proc.close()


def _remove_managed_block(crontab: str) -> str:
    lines = crontab.splitlines()
    start = -1
    end = -1
    for i, line in enumerate(lines):
        if _CRON_HEADER in line:
            start = i
        if _CRON_FOOTER in line and start != -1:
            end = i
            break
    if start != -1 and end != -1:
        return "\n".join(lines[:start] + lines[end + 1:]).strip()
    return crontab


def _upsert_managed_crons(crontab: str, new_entries: list[str]) -> str:
    cleaned = _remove_managed_block(crontab)
    if cleaned:
        cleaned += "\n"
    cleaned += _CRON_HEADER + "\n"
    for entry in new_entries:
        cleaned += entry + "\n"
    cleaned += _CRON_FOOTER + "\n"
    return cleaned


async def _get_or_create_state(db: AsyncSession) -> SetupState:
    result = await db.execute(select(SetupState).limit(1))
    state = result.scalar_one_or_none()
    if not state:
        state = SetupState(completed=False, step_index=0)
        db.add(state)
        await db.commit()
        await db.refresh(state)
    return state


@router.get("/status")
async def get_setup_status(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    state = await _get_or_create_state(db)
    return {
        "completed": state.completed,
        "step_index": state.step_index,
        "steps": {
            "secrets_changed": state.secrets_changed,
            "fail2ban_done": state.fail2ban_done,
            "geo_block_done": state.geo_block_done,
            "grafana_done": state.grafana_done,
            "backup_cron_set": state.backup_cron_set,
            "cve_cron_set": state.cve_cron_set,
            "update_cron_set": state.update_cron_set,
            "services_pruned": state.services_pruned,
        },
    }


@router.post("/step")
async def update_step(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    state = await _get_or_create_state(db)
    field = body.get("field")
    value = body.get("value", True)
    if field and hasattr(state, field):
        setattr(state, field, bool(value))
        state.step_index = body.get("step_index", state.step_index)
        await db.commit()
    return {"ok": True}


@router.post("/complete")
async def complete_setup(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    state = await _get_or_create_state(db)
    state.completed = True
    state.step_index = 99
    await db.commit()
    return {"ok": True}


@router.post("/crons")
async def create_crons(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    state = await _get_or_create_state(db)
    backup_enabled = body.get("backup", True)
    cve_enabled = body.get("cve", True)
    update_enabled = body.get("update", True)

    new_entries = []

    if backup_enabled:
        new_entries.append(
            "0 2 * * * cd /opt/gnukontrolr && bash setup.sh cmd_backup >> /var/log/gnukontrolr-backup.log 2>&1"
        )

    if cve_enabled:
        new_entries.append(
            "0 6 * * 1 cd /opt/gnukontrolr && curl -s https://nvd.nist.gov/ >/dev/null 2>&1 && echo 'CVE feed check ok' >> /var/log/gnukontrolr-cve.log 2>&1"
        )

    if update_enabled:
        new_entries.append(
            "0 5 * * 0 cd /opt/gnukontrolr && panel update >> /var/log/gnukontrolr-update.log 2>&1"
        )

    current_crontab = _read_crontab()
    updated_crontab = _upsert_managed_crons(current_crontab, new_entries)
    _write_crontab(updated_crontab)

    if backup_enabled:
        state.backup_cron_set = True
    if cve_enabled:
        state.cve_cron_set = True
    if update_enabled:
        state.update_cron_set = True
    await db.commit()

    return {"ok": True, "crons": len(new_entries)}


@router.get("/crons/status")
async def cron_status(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    crontab = _read_crontab()
    has_block = _CRON_HEADER in crontab
    entries = []
    if has_block:
        in_block = False
        for line in crontab.splitlines():
            if _CRON_HEADER in line:
                in_block = True
                continue
            if _CRON_FOOTER in line:
                break
            if in_block and line.strip() and not line.startswith("#"):
                entries.append(line.strip())
    return {"enabled": has_block, "entries": entries}
