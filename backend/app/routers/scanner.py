"""
Master Security Scanner — antivirus, malware heuristics, and file sanitizer.

ALL endpoints require admin or superadmin role.

Architecture:
  - Scan requests are forwarded to each domain's container via container_proxy helpers.
  - Container's clamscan + heuristic pattern engine scans the file tree.
  - Results are stored in ScanJob / MalwareAlert DB tables for audit history.
  - Sanitizer strips known-malicious PHP/JS patterns and logs every change.
"""
import asyncio
import json
import os
import re
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin, get_current_user
from app.database import get_db
from app.models.scanner import ScanJob, MalwareAlert, SanitizeLog
from app.http_client import panel_client

router = APIRouter(prefix="/api/scanner", tags=["scanner"])

CONTAINER_API_PORT = 9000
CONTAINER_API_TOKEN = os.environ.get("CONTAINER_API_TOKEN", "")
_TLS_VERIFY = False


def _container_url(domain: str, path: str) -> str:
    container = "site_" + domain.replace(".", "_").replace("-", "_")
    return f"https://{container}:{CONTAINER_API_PORT}{path}"


def _auth_headers():
    return {"Authorization": f"Bearer {CONTAINER_API_TOKEN}"} if CONTAINER_API_TOKEN else {}


# ── Heuristic patterns that the sanitizer can strip ───────────────────────────
_HEURISTIC_PATTERNS = [
    # PHP execution functions
    (re.compile(r"\beval\s*\(", re.IGNORECASE),               "php_eval"),
    (re.compile(r"\bbase64_decode\s*\(", re.IGNORECASE),      "php_base64_decode"),
    (re.compile(r"\bsystem\s*\(", re.IGNORECASE),             "php_system"),
    (re.compile(r"\bexec\s*\(", re.IGNORECASE),               "php_exec"),
    (re.compile(r"\bpassthru\s*\(", re.IGNORECASE),           "php_passthru"),
    (re.compile(r"\bshell_exec\s*\(", re.IGNORECASE),         "php_shell_exec"),
    (re.compile(r"\bproc_open\s*\(", re.IGNORECASE),          "php_proc_open"),
    # Obfuscation markers
    (re.compile(r"\$\w+\s*=\s*base64_decode\s*\(", re.IGNORECASE), "obfuscated_var"),
    # Known webshell strings
    (re.compile(r"c99shell|r57shell|FilesMan|phpspy", re.IGNORECASE), "webshell_marker"),
    # JS obfuscation
    (re.compile(r"document\.write\s*\(\s*unescape\s*\(", re.IGNORECASE), "js_unescape_write"),
    (re.compile(r"String\.fromCharCode\s*\(", re.IGNORECASE),          "js_fromcharcode"),
]


def _heuristic_scan_content(content: str) -> list[dict]:
    """Return list of {pattern, line, col} for each heuristic match."""
    findings = []
    for pattern, name in _HEURISTIC_PATTERNS:
        for m in pattern.finditer(content):
            line_no = content[: m.start()].count("\n") + 1
            findings.append({"pattern": name, "line": line_no, "match": m.group()[:80]})
    return findings


# ── GET /api/scanner/jobs ─────────────────────────────────────────────────────

@router.get("/jobs")
async def list_scan_jobs(
    domain: str = "",
    limit: int = 50,
    _=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List recent scan jobs, optionally filtered by domain."""
    stmt = select(ScanJob).order_by(ScanJob.started_at.desc()).limit(limit)
    if domain:
        stmt = stmt.where(ScanJob.domain == domain)
    rows = (await db.execute(stmt)).scalars().all()
    return {"jobs": [_job_dict(j) for j in rows]}


def _job_dict(j: ScanJob) -> dict:
    return {
        "id": j.id, "domain": j.domain, "area": j.area,
        "status": j.status, "started_at": j.started_at.isoformat() if j.started_at else None,
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
        "total_files": j.total_files, "infected": j.infected,
        "clean": j.clean, "errors": j.errors,
        "summary": json.loads(j.summary) if j.summary else [],
    }


# ── POST /api/scanner/scan ────────────────────────────────────────────────────

class ScanRequest(BaseModel):
    domain: str
    area: str = "all"   # public | uploads | private | all


@router.post("/scan")
async def start_scan(
    body: ScanRequest,
    user=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger a ClamAV + heuristic scan of a domain container.
    Creates a ScanJob, dispatches to container, stores results.
    """
    areas = ["public", "uploads", "private"] if body.area == "all" else [body.area]
    if body.area not in ("public", "uploads", "private", "all"):
        raise HTTPException(400, "area must be public | uploads | private | all")

    job = ScanJob(
        domain=body.domain,
        area=body.area,
        status="running",
        triggered_by=user.id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    findings: list[dict] = []
    total = clean = infected = errors = 0

    for area in areas:
        try:
            async with panel_client(timeout=120, verify=_TLS_VERIFY) as client:
                r = await client.post(
                    _container_url(body.domain, f"/scanner/scan"),
                    json={"area": area},
                    headers=_auth_headers(),
                )
                r.raise_for_status()
                result = r.json()
        except httpx.ConnectError:
            job.status = "failed"
            job.summary = json.dumps([{"error": f"Container unreachable for area={area}"}])
            await db.commit()
            raise HTTPException(503, f"Container not reachable (domain={body.domain})")
        except Exception as exc:
            errors += 1
            findings.append({"area": area, "error": str(exc)})
            continue

        for item in result.get("results", []):
            total += 1
            filepath = item.get("file", "")
            threat   = item.get("threat")
            if threat:
                infected += 1
                alert = MalwareAlert(
                    scan_job_id=job.id,
                    domain=body.domain,
                    area=area,
                    filepath=filepath,
                    threat_name=threat,
                    detection="clamav",
                    severity=_classify_severity(threat),
                )
                db.add(alert)
                findings.append({
                    "area": area, "file": filepath,
                    "threat": threat, "severity": alert.severity,
                })
            else:
                clean += 1

    job.status = "done"
    job.finished_at = datetime.utcnow()
    job.total_files = total
    job.infected = infected
    job.clean = clean
    job.errors = errors
    job.summary = json.dumps(findings)
    await db.commit()

    return _job_dict(job)


def _classify_severity(threat: str) -> str:
    t = threat.lower()
    if any(k in t for k in ("webshell", "backdoor", "trojan", "ransomware")):
        return "critical"
    if any(k in t for k in ("exploit", "rootkit", "dropper")):
        return "high"
    if any(k in t for k in ("malware", "virus", "worm")):
        return "medium"
    return "low"


# ── GET /api/scanner/alerts ───────────────────────────────────────────────────

@router.get("/alerts")
async def list_alerts(
    domain: str = "",
    resolved: bool = False,
    _=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(MalwareAlert)
        .where(MalwareAlert.resolved == resolved)
        .order_by(MalwareAlert.detected_at.desc())
        .limit(200)
    )
    if domain:
        stmt = stmt.where(MalwareAlert.domain == domain)
    rows = (await db.execute(stmt)).scalars().all()
    return {"alerts": [_alert_dict(a) for a in rows]}


def _alert_dict(a: MalwareAlert) -> dict:
    return {
        "id": a.id, "domain": a.domain, "area": a.area,
        "filepath": a.filepath, "threat_name": a.threat_name,
        "detection": a.detection, "severity": a.severity,
        "quarantined": a.quarantined, "resolved": a.resolved,
        "detected_at": a.detected_at.isoformat() if a.detected_at else None,
        "notes": a.notes,
    }


# ── POST /api/scanner/alerts/{id}/resolve ─────────────────────────────────────

@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: int,
    user=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    alert = await db.get(MalwareAlert, alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")
    alert.resolved = True
    alert.resolved_at = datetime.utcnow()
    alert.resolved_by = user.id
    await db.commit()
    return {"ok": True}


# ── POST /api/scanner/alerts/{id}/quarantine ──────────────────────────────────

@router.post("/alerts/{alert_id}/quarantine")
async def quarantine_file(
    alert_id: int,
    user=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Move the flagged file into the container's quarantine directory."""
    alert = await db.get(MalwareAlert, alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")
    try:
        async with panel_client(timeout=30, verify=_TLS_VERIFY) as client:
            r = await client.post(
                _container_url(alert.domain, "/scanner/quarantine"),
                json={"area": alert.area, "path": alert.filepath},
                headers=_auth_headers(),
            )
            r.raise_for_status()
    except httpx.ConnectError:
        raise HTTPException(503, "Container not reachable")
    except Exception as exc:
        raise HTTPException(500, str(exc))

    alert.quarantined = True
    alert.notes = (alert.notes or "") + f"\nQuarantined by admin (user_id={user.id})"
    await db.commit()
    return {"ok": True, "detail": "File moved to quarantine"}


# ── POST /api/scanner/heuristic ───────────────────────────────────────────────

class HeuristicScanRequest(BaseModel):
    domain: str
    area: str = "public"
    path: str = ""      # relative path within area; empty = root


@router.post("/heuristic")
async def heuristic_scan(
    body: HeuristicScanRequest,
    user=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Run heuristic (pattern-based) malware scan on PHP/JS files.
    Reads files via the container API, applies regex patterns in-process.
    Stores MalwareAlert rows for anything matching.
    """
    if body.area not in ("public", "uploads", "private"):
        raise HTTPException(400, "Invalid area")

    # Get directory listing
    try:
        async with panel_client(timeout=30, verify=_TLS_VERIFY) as client:
            r = await client.get(
                _container_url(body.domain, f"/files/{body.area}"),
                params={"path": body.path} if body.path else {},
                headers=_auth_headers(),
            )
            r.raise_for_status()
            listing = r.json()
    except httpx.ConnectError:
        raise HTTPException(503, "Container not reachable")
    except Exception as exc:
        raise HTTPException(500, str(exc))

    entries = listing.get("entries", listing.get("files", []))
    php_files = [
        e["name"] for e in entries
        if (e.get("type") == "file" or e.get("is_file")) and
        any(e["name"].endswith(ext) for ext in (".php", ".php5", ".phtml", ".js"))
    ]

    alerts_created = []
    for fname in php_files[:50]:  # cap at 50 per call to limit load
        fpath = f"{body.path}/{fname}".lstrip("/") if body.path else fname
        try:
            async with panel_client(timeout=15, verify=_TLS_VERIFY) as client:
                r = await client.get(
                    _container_url(body.domain, f"/files/{body.area}/read"),
                    params={"path": fpath},
                    headers=_auth_headers(),
                )
                r.raise_for_status()
                content = r.json().get("content", "")
        except Exception:
            continue

        hits = _heuristic_scan_content(content)
        if hits:
            alert = MalwareAlert(
                domain=body.domain,
                area=body.area,
                filepath=fpath,
                threat_name=", ".join({h["pattern"] for h in hits}),
                detection="heuristic",
                severity="medium",
            )
            db.add(alert)
            alerts_created.append({
                "file": fpath,
                "patterns": hits[:10],
            })

    await db.commit()
    return {
        "domain": body.domain,
        "area": body.area,
        "files_scanned": len(php_files),
        "alerts_created": len(alerts_created),
        "findings": alerts_created,
    }


# ── POST /api/scanner/sanitize ────────────────────────────────────────────────

class SanitizeRequest(BaseModel):
    domain: str
    area: str = "public"
    path: str             # specific file path to sanitize
    actions: list[str] = ["strip_eval", "strip_base64_decode", "strip_system"]


_SANITIZE_ACTIONS: dict[str, tuple[re.Pattern, str]] = {
    "strip_eval":           (re.compile(r"\beval\s*\([^)]*\)\s*;", re.IGNORECASE), "/* [SANITIZED:eval] */"),
    "strip_base64_decode":  (re.compile(r"\bbase64_decode\s*\([^)]*\)\s*;?", re.IGNORECASE), "/* [SANITIZED:base64_decode] */"),
    "strip_system":         (re.compile(r"\bsystem\s*\([^)]*\)\s*;", re.IGNORECASE), "/* [SANITIZED:system] */"),
    "strip_exec":           (re.compile(r"\bexec\s*\([^)]*\)\s*;", re.IGNORECASE), "/* [SANITIZED:exec] */"),
    "strip_passthru":       (re.compile(r"\bpassthru\s*\([^)]*\)\s*;", re.IGNORECASE), "/* [SANITIZED:passthru] */"),
    "strip_shell_exec":     (re.compile(r"\bshell_exec\s*\([^)]*\)\s*;", re.IGNORECASE), "/* [SANITIZED:shell_exec] */"),
    "strip_proc_open":      (re.compile(r"\bproc_open\s*\([^)]*\)\s*;", re.IGNORECASE), "/* [SANITIZED:proc_open] */"),
    "strip_js_unescape":    (re.compile(r"document\.write\s*\(\s*unescape\s*\([^)]+\)\s*\)\s*;?", re.IGNORECASE), "/* [SANITIZED:js_unescape] */"),
}


@router.post("/sanitize")
async def sanitize_file(
    body: SanitizeRequest,
    user=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Read a file from the container, apply sanitization patterns, write it back.
    Original is backed up as <file>.bak-<timestamp>.
    All changes are logged to sanitize_log.
    """
    if body.area not in ("public", "uploads", "private"):
        raise HTTPException(400, "Invalid area")

    # Read original
    try:
        async with panel_client(timeout=15, verify=_TLS_VERIFY) as client:
            r = await client.get(
                _container_url(body.domain, f"/files/{body.area}/read"),
                params={"path": body.path},
                headers=_auth_headers(),
            )
            r.raise_for_status()
            original = r.json().get("content", "")
    except httpx.ConnectError:
        raise HTTPException(503, "Container not reachable")
    except Exception as exc:
        raise HTTPException(500, str(exc))

    # Write backup
    ts = int(datetime.utcnow().timestamp())
    backup_path = f"{body.path}.bak-{ts}"
    try:
        async with panel_client(timeout=15, verify=_TLS_VERIFY) as client:
            r = await client.post(
                _container_url(body.domain, f"/files/{body.area}/write"),
                json={"path": backup_path, "content": original},
                headers=_auth_headers(),
            )
            r.raise_for_status()
    except Exception:
        pass  # backup failure is non-fatal

    # Apply sanitization actions
    sanitized = original
    actions_applied = []
    for action in body.actions:
        if action not in _SANITIZE_ACTIONS:
            continue
        pattern, replacement = _SANITIZE_ACTIONS[action]
        new_content, count = pattern.subn(replacement, sanitized)
        if count > 0:
            sanitized = new_content
            actions_applied.append({"action": action, "replacements": count})

    lines_changed = sum(a["replacements"] for a in actions_applied)

    if lines_changed == 0:
        return {"ok": True, "changed": False, "detail": "No patterns found — file is clean"}

    # Write sanitized file back
    try:
        async with panel_client(timeout=15, verify=_TLS_VERIFY) as client:
            r = await client.post(
                _container_url(body.domain, f"/files/{body.area}/write"),
                json={"path": body.path, "content": sanitized},
                headers=_auth_headers(),
            )
            r.raise_for_status()
    except httpx.ConnectError:
        raise HTTPException(503, "Container not reachable during write")
    except Exception as exc:
        raise HTTPException(500, str(exc))

    # Log
    for act in actions_applied:
        log_entry = SanitizeLog(
            domain=body.domain,
            area=body.area,
            filepath=body.path,
            action=act["action"],
            lines_changed=act["replacements"],
            performed_by=user.id,
            backup_path=backup_path,
        )
        db.add(log_entry)
    await db.commit()

    return {
        "ok": True,
        "changed": True,
        "actions": actions_applied,
        "lines_changed": lines_changed,
        "backup": backup_path,
    }


# ── GET /api/scanner/sanitize/log ─────────────────────────────────────────────

@router.get("/sanitize/log")
async def sanitize_log(
    domain: str = "",
    limit: int = 100,
    _=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(SanitizeLog).order_by(SanitizeLog.performed_at.desc()).limit(limit)
    if domain:
        stmt = stmt.where(SanitizeLog.domain == domain)
    rows = (await db.execute(stmt)).scalars().all()
    return {"log": [
        {
            "id": r.id, "domain": r.domain, "area": r.area,
            "filepath": r.filepath, "action": r.action,
            "lines_changed": r.lines_changed,
            "performed_at": r.performed_at.isoformat() if r.performed_at else None,
            "backup_path": r.backup_path,
        } for r in rows
    ]}
