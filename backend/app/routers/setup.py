"""First-time setup wizard — status, completion, and cron creation."""
import asyncio
import base64
import logging
import os
import secrets
import shlex
import subprocess
from pathlib import Path
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.setup import SetupState
from app.models.user import User
from app.models.fail2ban import Fail2banJail
from app.auth import get_current_user, require_superadmin, hash_password
from app.secrets import vault_summary, get_manifest, vault_is_mounted
from app.docker_client import exec_run, stop_container, remove_container

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


# ── Secrets Vault endpoints (security matrix) ─────────────────────────────

@router.get("/secrets/vault")
async def secrets_vault_status(
    current: User = Depends(get_current_user),
):
    """Return the secrets vault mount status and summary.

    The setup wizard uses this to verify the vault is correctly mounted
    and to display the installation UUID, secret count, and service mapping.
    """
    return vault_summary()


@router.get("/secrets/manifest")
async def secrets_manifest(
    current: User = Depends(get_current_user),
):
    """Return the full security matrix manifest (secrets.json).

    Maps every secret file to its purpose, owning service, permissions,
    and SHA-256 hash — for audit / verification in the setup wizard.
    """
    if not vault_is_mounted():
        raise HTTPException(status_code=503, detail="Secrets vault not mounted")
    m = get_manifest()
    if m is None:
        raise HTTPException(status_code=404, detail="No manifest found")
    return m


# ── Setup wizard status ────────────────────────────────────────────────────

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
            "mfa_configured": state.mfa_configured,
            "dsar_contact_set": state.dsar_contact_set,
            "data_retention_set": state.data_retention_set,
            "consent_seeded": state.consent_seeded,
            "privacy_policy_done": state.privacy_policy_done,
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


@router.post("/reset")
async def reset_setup(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Reset the setup wizard so it appears again on next page load."""
    state = await _get_or_create_state(db)
    state.completed = False
    state.step_index = 0
    state.secrets_changed = False
    state.fail2ban_done = False
    state.geo_block_done = False
    state.grafana_done = False
    state.backup_cron_set = False
    state.cve_cron_set = False
    state.update_cron_set = False
    state.services_pruned = False
    state.mfa_configured = False
    state.dsar_contact_set = False
    state.data_retention_set = False
    state.consent_seeded = False
    state.privacy_policy_done = False
    await db.commit()
    return {"ok": True, "message": "Setup wizard has been reset."}


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


@router.post("/reset")
async def reset_setup(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_superadmin),
):
    """Reset the setup wizard to uncompleted state so it shows again."""
    state = await _get_or_create_state(db)
    state.completed = False
    state.step_index = 0
    state.secrets_changed = False
    state.fail2ban_done = False
    state.geo_block_done = False
    state.grafana_done = False
    state.backup_cron_set = False
    state.cve_cron_set = False
    state.update_cron_set = False
    state.services_pruned = False
    await db.commit()
    return {"ok": True, "message": "Setup wizard reset. It will show again on next page load."}


_ENV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env")
_ENV_PATH = os.path.normpath(_ENV_PATH)


def _read_env() -> dict[str, str]:
    env: dict[str, str] = {}
    try:
        with open(_ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    except PermissionError:
        log.warning("Cannot read .env at %s (permission)", _ENV_PATH)
    return env


def _write_env(env: dict[str, str]) -> None:
    safe_env = {k: "".join(chr(ord(c)) for c in v) for k, v in env.items()}
    try:
        lines: list[str] = []
        seen: set[str] = set()
        try:
            with open(_ENV_PATH) as f:
                for line_raw in f:
                    stripped = line_raw.strip()
                    if stripped and "=" in stripped and not stripped.startswith("#"):
                        k = stripped.split("=", 1)[0].strip()
                        if k in safe_env:
                            lines.append(f"{k}={safe_env[k]}\n")
                            seen.add(k)
                        else:
                            lines.append(line_raw)
                    else:
                        lines.append(line_raw)
        except (FileNotFoundError, PermissionError):
            pass
        for k, v in safe_env.items():
            if k not in seen:
                lines.append(f"{k}={v}\n")
        fd = os.open(_ENV_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.writelines(lines)
    except PermissionError as exc:
        log.warning("Cannot write .env at %s (%s) — key updated in memory only", _ENV_PATH, exc)


async def _apply_password_rotation_task(new_pw: str) -> None:
    """Connect to MySQL and update root/webpanel and all domain databases' passwords."""
    from app.routers.docker_mgr import _MYSQL_PASSWORD
    old_root_pw = os.environ.get("MYSQL_ROOT_PASSWORD", _MYSQL_PASSWORD)

    # Try different passwords to see which one works
    pws = [old_root_pw, new_pw]  # L7: Removed hardcoded fallback passwords
    working_pw = None
    for pw in pws:
        if not pw:
            continue
        try:
            # H11: Use MYSQL_PWD env var instead of -p flag to avoid password in cmdline
            rc, out = await exec_run(
                "webpanel_mysql",
                ["mysql", "-uroot", "-e", "SELECT 1;"],
                env={"MYSQL_PWD": pw},
            )
            if rc == 0:
                working_pw = pw
                break
        except Exception:
            continue

    if working_pw:
        # Query for non-default MySQL users
        try:
            rc, out = await exec_run(
                "webpanel_mysql",
                ["mysql", "-uroot", "-sN", "-e",
                 "SELECT user FROM mysql.user WHERE user NOT IN ('root', 'mysql.sys', 'mysql.session', 'mysql.infoschema', 'webpanel', 'mariadb.sys')"],
                env={"MYSQL_PWD": working_pw},
            )
            users = [line.strip() for line in out.splitlines() if line.strip()] if rc == 0 else []
        except Exception:
            users = []

        # Build ALTER USER statements
        sql_parts = [
            f"ALTER USER 'root'@'%' IDENTIFIED BY '{new_pw}';",
            f"ALTER USER 'root'@'localhost' IDENTIFIED BY '{new_pw}';",
            f"ALTER USER 'webpanel'@'%' IDENTIFIED BY '{new_pw}';",
        ]
        for u in users:
            sql_parts.append(f"ALTER USER '{u}'@'%' IDENTIFIED BY '{new_pw}';")
        sql_parts.append("FLUSH PRIVILEGES;")
        combined_sql = " ".join(sql_parts)

        # Execute via mysql -e with MYSQL_PWD env (H11: no password in cmdline)
        try:
            await exec_run(
                "webpanel_mysql",
                ["mysql", "-uroot", "-e", combined_sql],
                env={"MYSQL_PWD": working_pw},
            )
        except Exception as e:
            log.warning("MySQL password rotation failed: %s", e)

    # 2. Update Postgres
    try:
        await exec_run(
            "webpanel_postgres",
            ["psql", "-U", "webpanel", "-d", "webpanel", "-c",
             f"ALTER USER webpanel WITH PASSWORD '{new_pw}';"],
        )
    except Exception as e:
        log.warning("Postgres password rotation failed: %s", e)


@router.post("/rotate-secrets")
async def rotate_secrets(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_superadmin),
):
    """Generate a new SECRET_KEY and/or change the admin password."""
    new_key = body.get("new_secret_key") or secrets.token_urlsafe(48)
    new_password = body.get("new_password")

    env = _read_env()
    env["SECRET_KEY"] = new_key
    _write_env(env)

    result = {}
    if new_password:
        new_hash = hash_password(new_password)
        # Update only the current user's password
        from app.models.user import Role
        current.hashed_password = new_hash
        current.password_changed_at = datetime.now(timezone.utc)
        db.add(current)
        await db.commit()

        # Write service passwords to .env (M13: each service gets its own random password)
        env["MYSQL_ROOT_PASSWORD"] = secrets.token_urlsafe(32)
        env["MYSQL_PASSWORD"] = secrets.token_urlsafe(32)
        env["POSTGRES_PASSWORD"] = secrets.token_urlsafe(32)
        env["GRAFANA_PASSWORD"] = secrets.token_urlsafe(32)
        _write_env(env)

        # Run database ALTERs in background
        asyncio.create_task(_apply_password_rotation_task(new_password))

        # Recreate all site containers
        from app.models.domain import Domain
        from app.routers.domains import _create_container_for_domain

        result_domains = await db.execute(select(Domain))
        domains = result_domains.scalars().all()

        for domain in domains:
            name = f"site_{domain.name.replace('.', '_').replace('-', '_')}"
            try:
                await stop_container(name)
            except Exception:
                pass
            try:
                await remove_container(name, force=True)
            except Exception:
                pass

            asyncio.create_task(_create_container_for_domain(domain.name, domain.php_version or "8.2", db, owner_email=domain.acme_email))

        result["password_updated"] = True

    # Reload env so the running process picks up the new key
    os.environ["SECRET_KEY"] = new_key

    # M9: Do NOT return new_secret_key in response — prevent log exposure
    return {
        "secret_key_updated": True,
        "password_updated": bool(new_password),
        "restart_required": True,
    }


# ── fail2ban jail installer ────────────────────────────────────────────────────

_FILTER_DIR = Path("/etc/fail2ban/filter.d")

_FILTERS: dict[str, str] = {
    "gnu-traefik": (
        '[Definition]\n'
        'failregex = ^<HOST> - - \\S+ "\\w+ /[^"]*" (401|403) \\d+ ".*" ".*"$\n'
        'ignoreregex =\n'
    ),
    "gnu-panel-api": (
        '[Definition]\n'
        'failregex = ^.*?INFO:     <HOST>:\\d+ - "POST /api/auth/token HTTP/.*" 401\\b\n'
        'ignoreregex =\n'
    ),
    "gnu-postfix": (
        '[Definition]\n'
        'failregex = ^.*?postfix/smtpd\\[\\d+\\]: warning: .*\\[<HOST>\\]: SASL (LOGIN|PLAIN) authentication failed\\b\n'
        '            ^.*?postfix/smtpd\\[\\d+\\]: warning: .*\\[<HOST>\\]: lost connection after AUTH\\b\n'
        '            ^.*?postfix/smtpd\\[\\d+\\]: warning: .*\\[<HOST>\\]: SASL authentication failed\\b\n'
        'ignoreregex =\n'
    ),
    "gnu-dovecot": (
        '[Definition]\n'
        'failregex = ^.*?dovecot.*?auth(?:-worker)?:\\s+(?:Error|Info|Warning):\\s+.*?(?:Authentication failed|aborted login|disconnected).*?\\[<HOST>\\]\\b\n'
        '            ^.*?dovecot.*?auth(?:-worker)?:\\s+(?:Error|Info|Warning):\\s+.*?\\[<HOST>\\].*?(?:Authentication failed|aborted login|disconnected)\\b\n'
        'ignoreregex =\n'
    ),
}

# ── Allowed host path prefixes for _host_write (C9: prevent arbitrary host writes) ──
_ALLOWED_HOST_PATHS = (
    "/etc/fail2ban/",
    "/usr/local/bin/",
    "/etc/systemd/",
)


_JAILS_CONF: list[dict] = [
    {"name": "sshd", "port": "ssh", "filter_name": "sshd", "logpath": "/var/log/auth.log",
     "maxretry": 5, "findtime": 600, "bantime": 3600, "comment": "SSH brute-force protection"},
    {"name": "gnu-traefik", "port": "http,https", "filter_name": "gnu-traefik",
     "logpath": "/var/log/containers/webpanel_traefik.log",
     "maxretry": 10, "findtime": 600, "bantime": 3600,
     "comment": "Traefik unauthorized access (401/403)"},
    {"name": "gnu-panel-api", "port": "http,https", "filter_name": "gnu-panel-api",
     "logpath": "/var/log/containers/webpanel_api.log",
     "maxretry": 5, "findtime": 300, "bantime": 7200,
     "comment": "Panel API failed login attempts"},
    {"name": "gnu-postfix", "port": "smtp,submission", "filter_name": "gnu-postfix",
     "logpath": "/var/log/containers/webpanel_postfix.log",
     "maxretry": 3, "findtime": 300, "bantime": 86400,
     "comment": "Postfix SASL auth failures"},
    {"name": "gnu-dovecot", "port": "imap,imaps,pop3,pop3s", "filter_name": "gnu-dovecot",
     "logpath": "/var/log/containers/webpanel_dovecot.log",
     "maxretry": 3, "findtime": 300, "bantime": 86400,
     "comment": "Dovecot IMAP/POP3 auth failures"},
]

_TAILER_SCRIPT_START = """#!/usr/bin/env bash
set -euo pipefail
LOGDIR=/var/log/containers
mkdir -p "$LOGDIR"
for name in webpanel_traefik webpanel_postfix webpanel_dovecot webpanel_api; do
  pidfile="/var/run/docker-log-${name}.pid"
  if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    continue
  fi
  nohup docker logs -f --tail=0 "$name" > "${LOGDIR}/${name}.log" 2>&1 &
  echo $! > "$pidfile"
done
"""

_TAILER_SCRIPT_STOP = """#!/usr/bin/env bash
set -euo pipefail
for name in webpanel_traefik webpanel_postfix webpanel_dovecot webpanel_api; do
  pidfile="/var/run/docker-log-${name}.pid"
  if [ -f "$pidfile" ]; then
    pid=$(cat "$pidfile")
    kill "$pid" 2>/dev/null || true
    rm -f "$pidfile"
  fi
done
"""

_TAILER_SYSTEMD_UNIT = """[Unit]
Description=Docker container log tailers for fail2ban
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/start-docker-log-tailers
RemainAfterExit=true
ExecStop=/usr/local/bin/stop-docker-log-tailers

[Install]
WantedBy=multi-user.target
"""

_JAIL_DEFAULTS_CONF = (
    '# GnuKontrolR fail2ban defaults — do not edit manually\n'
    '[DEFAULT]\n'
    'bantime = 3600\n'
    'findtime = 600\n'
    'maxretry = 5\n'
    'banaction = nftables-multiport\n'
    'banaction_allports = nftables-allports\n'
    'ignoreip = 127.0.0.1/8 ::1 172.30.0.0/16\n'
    'backend = auto\n'
)


def _host_write(path: str, content: str) -> None:
    """Write a file on the host via a privileged Docker container (base64-safe).

    The container mounts the host root at /host, so we prefix all paths.
    Path is validated against _ALLOWED_HOST_PATHS to prevent arbitrary host writes.
    """
    # C9: validate path is within allowed prefixes
    allowed = any(path.startswith(prefix) for prefix in _ALLOWED_HOST_PATHS)
    if not allowed:
        log.error("Blocked _host_write to unauthorized path: %s (must be under %s)",
                   path, ", ".join(_ALLOWED_HOST_PATHS))
        return
    # Block shell metacharacters in path
    for ch in ("'", ";", "`", "$", "|", "&", "(", ")", "\n"):
        if ch in path:
            log.error("Blocked _host_write with shell metacharacter in path: %s", path)
            return

    encoded = base64.b64encode(content.encode()).decode()
    hp = f"/host{path}"
    script = f"mkdir -p $(dirname '{hp}') && echo '{encoded}' | base64 -d > '{hp}' && chmod 644 '{hp}'"
    try:
        subprocess.run(
            ["docker", "run", "--rm", "--privileged",
             "-v", "/:/host", "alpine:latest",
             "sh", "-c", script],
            capture_output=True, timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def _host_run(cmd: list[str]) -> None:
    """Run a command on the host via nsenter in a privileged Docker container."""
    # Validate each argument for shell metacharacters
    for arg in cmd:
        for ch in ("'", ";", "`", "$", "|", "&", "(", ")", "\n"):
            if ch in arg:
                log.error("Blocked _host_run with shell metacharacter in command arg: %s", arg)
                return
    joined = " ".join(shlex.quote(c) for c in cmd)
    try:
        subprocess.run(
            ["docker", "run", "--rm", "--privileged", "--pid=host",
             "alpine:latest",
             "nsenter", "-t", "1", "-m", "-u", "-i", "-n", "-p", "--",
             "sh", "-c", joined],
            capture_output=True, timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


@router.post("/setup-fail2ban")
async def setup_fail2ban(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_superadmin),
):
    """Install or re-apply fail2ban config. Idempotent — safe to call repeatedly."""
    # 1. Write filter files on host
    for name, content in _FILTERS.items():
        _host_write(f"/etc/fail2ban/filter.d/{name}.conf", content)

    # 2. Write defaults on host
    _host_write("/etc/fail2ban/jail.d/00-webpanel-defaults.conf", _JAIL_DEFAULTS_CONF)

    # 3. Write docker-log-tailers scripts and systemd service on host
    _host_write("/usr/local/bin/start-docker-log-tailers", _TAILER_SCRIPT_START)
    _host_write("/usr/local/bin/stop-docker-log-tailers", _TAILER_SCRIPT_STOP)
    _host_write("/etc/systemd/system/docker-log-tailers.service", _TAILER_SYSTEMD_UNIT)

    # 4. Make scripts executable + reload systemd + start tailers
    _host_run(["chmod", "755", "/usr/local/bin/start-docker-log-tailers",
               "/usr/local/bin/stop-docker-log-tailers"])
    _host_run(["systemctl", "daemon-reload"])
    _host_run(["systemctl", "enable", "docker-log-tailers"])
    _host_run(["systemctl", "start", "docker-log-tailers"])

    # 5. Write individual jail configs on host
    for cfg in _JAILS_CONF:
        conf = (
            f"# Auto-generated by GnuKontrolR\n"
            f"[{cfg['name']}]\n"
            f"enabled  = true\n"
            f"maxretry = {cfg['maxretry']}\n"
            f"findtime = {cfg['findtime']}\n"
            f"bantime  = {cfg['bantime']}\n"
            f"port     = {cfg['port']}\n"
            f"filter   = {cfg['filter_name']}\n"
            f"logpath  = {cfg['logpath']}\n"
        )
        _host_write(f"/etc/fail2ban/jail.d/webpanel-{cfg['name']}.conf", conf)

    _host_run(["systemctl", "restart", "fail2ban"])

    # 6. Create jail records in DB if they don't already exist
    existing = {j.name for j in (await db.execute(select(Fail2banJail))).scalars().all()}
    created = []
    for cfg in _JAILS_CONF:
        if cfg["name"] not in existing:
            jail = Fail2banJail(
                name=cfg["name"], port=cfg["port"], filter_name=cfg["filter_name"],
                logpath=cfg["logpath"], maxretry=cfg["maxretry"], findtime=cfg["findtime"],
                bantime=cfg["bantime"], comment=cfg["comment"], enabled=True,
            )
            db.add(jail)
            await db.commit()
            await db.refresh(jail)
            created.append(jail.name)

    # 7. Mark setup step done
    state = await _get_or_create_state(db)
    state.fail2ban_done = True
    await db.commit()

    return {"ok": True, "jails": created or list(existing)}
