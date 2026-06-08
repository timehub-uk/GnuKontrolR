"""Cron job management — list, add, edit, delete, toggle system crontab entries."""
import logging
import os
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.models.user import User
from app.auth import get_current_user

log = logging.getLogger("webpanel")

router = APIRouter(prefix="/api/crons", tags=["crons"])

_CRON_HEADER = "# GnuKontrolR — auto-managed crons (DO NOT EDIT BELOW THIS LINE)"
_CRON_FOOTER = "# GnuKontrolR — end auto-managed crons"
_CRON_PATTERN = re.compile(
    r"^(\s*(?:#?\s*)?)"
    r"((?:@(?:reboot|yearly|annually|monthly|weekly|daily|hourly|midnight))\s+|"
    r"(?:[0-9*,/\-]+)\s+(?:[0-9*,/\-]+)\s+(?:[0-9*,/\-]+)\s+(?:[0-9*,/\-]+)\s+(?:[0-9*,/\-]+)\s+)"
    r"(.*)$"
)


class CronEntry(BaseModel):
    id: str
    schedule: str
    command: str
    comment: Optional[str] = None
    enabled: bool = True
    managed: bool = False


class CronCreate(BaseModel):
    schedule: str
    command: str
    comment: Optional[str] = None


class CronUpdate(BaseModel):
    schedule: Optional[str] = None
    command: Optional[str] = None
    comment: Optional[str] = None
    enabled: Optional[bool] = None


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


def _parse_crontab() -> tuple[list[CronEntry], set[str], str]:
    raw = _read_crontab()
    lines = raw.splitlines()
    entries: list[CronEntry] = []
    in_managed = False
    managed_ids: set[str] = set()

    # First pass — assign stable IDs based on line content hash
    for i, line in enumerate(lines):
        stripped = line.strip()
        if _CRON_HEADER in stripped:
            in_managed = True
            continue
        if _CRON_FOOTER in stripped:
            in_managed = False
            continue
        if not stripped or stripped.startswith("#") and not _CRON_PATTERN.match(stripped):
            continue

        match = _CRON_PATTERN.match(stripped)
        if not match:
            continue

        prefix = match.group(1).strip()
        schedule = match.group(2).strip()
        command = match.group(3).strip()
        is_commented = stripped.startswith("#")
        enabled = not is_commented
        comment = None

        label = f"{schedule} {command}"
        label_hash = str(uuid.uuid5(uuid.NAMESPACE_DNS, label))

        if in_managed:
            managed_ids.add(label_hash)

        entries.append(CronEntry(
            id=label_hash,
            schedule=schedule,
            command=command,
            comment=comment,
            enabled=enabled,
            managed=in_managed,
        ))

    return entries, managed_ids, raw


def _format_cron_line(entry: CronEntry) -> str:
    line = f"{entry.schedule} {entry.command}"
    if not entry.enabled:
        line = "# " + line
    return line


def _rebuild_crontab(entries: list[CronEntry]) -> str:
    managed: list[str] = []
    user: list[str] = []
    for e in entries:
        if e.managed:
            managed.append(_format_cron_line(e))
        else:
            user.append(_format_cron_line(e))

    parts = []
    if user:
        parts.append("\n".join(user))
    if managed:
        parts.append(_CRON_HEADER)
        parts.append("\n".join(managed))
        parts.append(_CRON_FOOTER)
    return "\n".join(parts) + "\n"


@router.get("/")
async def list_crons(current: User = Depends(get_current_user)):
    entries, managed_ids, raw = _parse_crontab()
    return {
        "entries": [e.model_dump() for e in entries],
        "managed_ids": list(managed_ids),
        "raw": raw,
    }


@router.post("/", status_code=201)
async def create_cron(
    body: CronCreate,
    current: User = Depends(get_current_user),
):
    if not body.schedule.strip() or not body.command.strip():
        raise HTTPException(400, "schedule and command are required")

    label = f"{body.schedule.strip()} {body.command.strip()}"
    entry_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, label))
    new_entry = CronEntry(
        id=entry_id,
        schedule=body.schedule.strip(),
        command=body.command.strip(),
        comment=body.comment,
        enabled=True,
        managed=False,
    )

    entries, _, _ = _parse_crontab()
    entries.append(new_entry)
    _write_crontab(_rebuild_crontab(entries))
    return new_entry


@router.put("/{entry_id}")
async def update_cron(
    entry_id: str,
    body: CronUpdate,
    current: User = Depends(get_current_user),
):
    entries, _, _ = _parse_crontab()
    found = None
    for e in entries:
        if e.id == entry_id:
            found = e
            break
    if not found:
        raise HTTPException(404, "Cron entry not found")

    if body.schedule is not None:
        found.schedule = body.schedule.strip()
    if body.command is not None:
        found.command = body.command.strip()
    if body.comment is not None:
        found.comment = body.comment
    if body.enabled is not None:
        found.enabled = body.enabled

    _write_crontab(_rebuild_crontab(entries))
    return found


@router.delete("/{entry_id}", status_code=204)
async def delete_cron(
    entry_id: str,
    current: User = Depends(get_current_user),
):
    entries, _, _ = _parse_crontab()
    new_entries = [e for e in entries if e.id != entry_id]
    if len(new_entries) == len(entries):
        raise HTTPException(404, "Cron entry not found")
    _write_crontab(_rebuild_crontab(new_entries))


@router.post("/{entry_id}/toggle")
async def toggle_cron(
    entry_id: str,
    current: User = Depends(get_current_user),
):
    entries, _, _ = _parse_crontab()
    found = None
    for e in entries:
        if e.id == entry_id:
            found = e
            break
    if not found:
        raise HTTPException(404, "Cron entry not found")
    found.enabled = not found.enabled
    _write_crontab(_rebuild_crontab(entries))
    return found
