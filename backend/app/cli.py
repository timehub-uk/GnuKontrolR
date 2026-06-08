#!/usr/bin/env python3
"""
GnuKontrolR CLI — panel administration tools for WebPanel Terminal.

Usage: panel <command> [options]

Commands:
  user          User management (list, create, reset-pass)
  domain        Domain management (list)
  service       Service status & restart
  container     Container list, logs, stats
  dns           DNS zone & record management
  sys           System info & diagnostics
  log           Log viewer
  db            Database tools (MySQL, PostgreSQL)
  help          Show this message
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys
import textwrap
from datetime import datetime

CLI_NAME = "panel"

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def header(title):
    cols = shutil_get_terminal_cols()
    sep = "─" * min(cols - 2, 60)
    print(f" ┌{sep}┐")
    print(f" │ {title:<{min(cols - 4, 58)}} │")
    print(f" └{sep}┘")

def shutil_get_terminal_cols():
    try:
        import shutil
        return shutil.get_terminal_size().columns
    except Exception:
        return 80

def print_table(rows, headers=None):
    if not rows:
        return
    if headers:
        rows = [headers] + rows
    col_widths = []
    for col_idx in range(len(rows[0])):
        width = max(len(str(r[col_idx])) for r in rows)
        col_widths.append(min(width + 2, 40))
    for r_idx, row in enumerate(rows):
        line = ""
        for c_idx, cell in enumerate(row):
            line += str(cell).ljust(col_widths[c_idx])
        print(line)
        if headers and r_idx == 0:
            print("─" * sum(col_widths))

# ── helpers ──────────────────────────────────────────────────────────────────

def _docker(cmd: list, capture=True) -> str:
    full = ["docker"] + cmd
    try:
        r = subprocess.run(full, capture_output=capture, text=True, timeout=15)
        return r.stdout.strip()
    except Exception as e:
        return f"Error: {e}"

def _docker_json(cmd: list):
    full = ["docker"] + cmd
    try:
        r = subprocess.run(full, capture_output=True, text=True, timeout=15)
        if not r.stdout.strip():
            return []
        lines = r.stdout.strip().splitlines()
        result = []
        for line in lines:
            line = line.strip()
            if line:
                result.append(json.loads(line))
        return result
    except Exception:
        return []

# ── async helpers (panel DB) ─────────────────────────────────────────────────

async def _get_db():
    sys.path.insert(0, "/app")
    from app.database import init_db, AsyncSessionLocal
    await init_db()
    return AsyncSessionLocal

async def _get_user_model():
    from app.models.user import User
    return User

async def _get_domain_model():
    from app.models.domain import Domain
    return Domain

async def _get_role():
    from app.models.user import Role
    return Role

# ── user commands ────────────────────────────────────────────────────────────

async def cmd_user_list(args):
    db = await _get_db()
    User = await _get_user_model()
    Role = await _get_role()
    async with db() as session:
        from sqlalchemy import select
        result = await session.execute(select(User).order_by(User.id))
        users = result.scalars().all()
    if not users:
        print("No users found.")
        return
    rows = []
    for u in users:
        role_str = u.role.value if hasattr(u.role, "value") else str(u.role)
        rows.append([str(u.id), u.username, u.email or "—", role_str, "✓" if u.is_active else "✗"])
    print_table(rows, ["ID", "Username", "Email", "Role", "Active"])

async def cmd_user_create(args):
    db = await _get_db()
    User = await _get_user_model()
    Role = await _get_role()
    from app.auth import hash_password
    role_map = {"user": Role.user, "admin": Role.admin, "reseller": Role.reseller, "superadmin": Role.superadmin}
    role = role_map.get(args.role, Role.user)
    async with db() as session:
        from sqlalchemy import select
        exists = (await session.execute(select(User).where(User.username == args.username))).scalar_one_or_none()
        if exists:
            eprint(f"User '{args.username}' already exists.")
            sys.exit(1)
        import secrets
        password = args.password or secrets.token_urlsafe(12)
        user = User(
            username=args.username,
            email=args.email,
            hashed_password=hash_password(password),
            role=role,
            is_active=True,
        )
        session.add(user)
        await session.commit()
    print(f"User '{args.username}' created (role={args.role}).")
    if not args.password:
        print(f"Password: {password}")

async def cmd_user_reset_pass(args):
    db = await _get_db()
    User = await _get_user_model()
    from app.auth import hash_password
    import secrets
    async with db() as session:
        from sqlalchemy import select
        result = await session.execute(select(User).where(User.username == args.username))
        user = result.scalar_one_or_none()
        if not user:
            eprint(f"User '{args.username}' not found.")
            sys.exit(1)
        password = args.password or secrets.token_urlsafe(12)
        user.hashed_password = hash_password(password)
        await session.commit()
    print(f"Password updated for '{args.username}'.")
    if not args.password:
        print(f"New password: {password}")

async def cmd_user_delete(args):
    db = await _get_db()
    User = await _get_user_model()
    async with db() as session:
        from sqlalchemy import select
        result = await session.execute(select(User).where(User.username == args.username))
        user = result.scalar_one_or_none()
        if not user:
            eprint(f"User '{args.username}' not found.")
            sys.exit(1)
        await session.delete(user)
        await session.commit()
    print(f"User '{args.username}' deleted.")

# ── domain commands ──────────────────────────────────────────────────────────

async def cmd_domain_list(args):
    db = await _get_db()
    Domain = await _get_domain_model()
    User = await _get_user_model()
    from sqlalchemy import select
    async with db() as session:
        query = select(Domain)
        user_id = getattr(args, "user_id", None)
        if user_id:
            query = query.where(Domain.owner_id == user_id)
        query = query.order_by(Domain.id)
        result = await session.execute(query)
        domains = result.scalars().all()
    if not domains:
        print("No domains found.")
        return
    rows = []
    for d in domains:
        status_str = d.status.value if hasattr(d.status, "value") else str(d.status)
        rows.append([str(d.id), d.name, str(d.owner_id), status_str])
    print_table(rows, ["ID", "Domain", "Owner", "Status"])

# ── service commands ─────────────────────────────────────────────────────────

SERVICE_CONTAINERS = {
    "traefik":  "webpanel_traefik",
    "mysql":    "webpanel_mysql",
    "postgres": "webpanel_postgres",
    "redis":    "webpanel_redis",
    "postfix":  "webpanel_postfix",
    "dovecot":  "webpanel_dovecot",
    "powerdns": "webpanel_powerdns",
    "panel":    "webpanel_api",
    "prometheus": "webpanel_prometheus",
    "grafana":  "webpanel_grafana",
}

def cmd_service_status(args):
    rows = []
    for svc, container in SERVICE_CONTAINERS.items():
        status = _docker(["inspect", "--format", "{{.State.Status}}", container])
        if "Error" in status:
            status = "not found"
        health = _docker(["inspect", "--format", "{{.State.Health.Status}}", container])
        if "Error" in health or not health:
            health = "—"
        rows.append([svc, status, health])
    print_table(rows, ["Service", "Status", "Health"])

def cmd_service_restart(args):
    container = SERVICE_CONTAINERS.get(args.name)
    if not container:
        eprint(f"Unknown service: {args.name}. Known: {', '.join(SERVICE_CONTAINERS.keys())}")
        sys.exit(1)
    print(f"Restarting {args.name} ({container})...")
    r = _docker(["restart", container])
    if r and "Error" not in r:
        print("Done.")
    else:
        eprint(f"Failed: {r}")
        sys.exit(1)

# ── container commands ───────────────────────────────────────────────────────

def cmd_container_list(args):
    containers = _docker_json(["ps", "--all", "--format", "{{json .}}"])
    if not containers:
        print("No containers.")
        return
    rows = []
    for c in containers if isinstance(containers, list) else [containers]:
        name = c.get("Names", c.get("Name", "?"))
        if isinstance(name, list):
            name = name[0] if name else "?"
        img = c.get("Image", "?")[:30]
        state = c.get("State", "?")
        status = c.get("Status", "?")
        rows.append([name, img, state, status[:35]])
    print_table(rows, ["Name", "Image", "State", "Status"])

def cmd_container_logs(args):
    tail = f"--tail={args.lines}"
    r = _docker(["logs", tail, args.name])
    print(r if r else "(no output)")

def cmd_container_stats(args):
    r = _docker_json(["stats", "--no-stream", "--format", "{{json .}}"])
    if not r:
        print("No stats available.")
        return
    rows = []
    items = r if isinstance(r, list) else [r]
    for c in items[:20]:
        name = c.get("Name", "?")
        cpu = c.get("CPUPerc", "?")
        mem = c.get("MemPerc", "?")
        mem_usage = c.get("MemUsage", "?")
        net = c.get("NetIO", "?")
        rows.append([name[:30], cpu, mem, mem_usage[:20], net[:20]])
    print_table(rows, ["Container", "CPU", "Mem%", "Mem Usage", "Net I/O"])

# ── DNS commands ─────────────────────────────────────────────────────────────

def cmd_dns_zones(args):
    key = os.environ.get("PDNS_API_KEY", "")
    url = os.environ.get("PDNS_API_URL", "http://powerdns:8081/api/v1/servers/localhost")
    import urllib.request
    req = urllib.request.Request(f"{url}/zones", headers={"X-API-Key": key})
    try:
        r = urllib.request.urlopen(req, timeout=5)
        zones = json.loads(r.read())
    except Exception as e:
        eprint(f"PowerDNS unreachable: {e}")
        sys.exit(1)
    if not zones:
        print("No zones.")
        return
    rows = []
    for z in zones:
        rows.append([z.get("name", "?"), z.get("kind", "?"), str(len(z.get("rrsets", [])))])
    print_table(rows, ["Zone", "Kind", "Records"])

def cmd_dns_records(args):
    key = os.environ.get("PDNS_API_KEY", "")
    url = os.environ.get("PDNS_API_URL", "http://powerdns:8081/api/v1/servers/localhost")
    import urllib.request
    zone_name = args.zone if args.zone.endswith(".") else args.zone + "."
    req = urllib.request.Request(f"{url}/zones/{zone_name}", headers={"X-API-Key": key})
    try:
        r = urllib.request.urlopen(req, timeout=5)
        data = json.loads(r.read())
    except Exception as e:
        eprint(f"PowerDNS unreachable: {e}")
        sys.exit(1)
    rrsets = data.get("rrsets", [])
    if not rrsets:
        print(f"No records for {args.zone}.")
        return
    rows = []
    for rr in rrsets:
        name = rr.get("name", "?").rstrip(".")
        rtype = rr.get("type", "?")
        ttl = str(rr.get("ttl", "?"))
        for record in rr.get("records", []):
            content = record.get("content", "?")
            rows.append([name, rtype, ttl, content])
    print_table(rows, ["Name", "Type", "TTL", "Content"])

# ── sys commands ─────────────────────────────────────────────────────────────

def cmd_sys_info(args):
    header("System Info")
    try:
        import platform
        uname = platform.uname()
        print(f"  Hostname:  {uname.node}")
        print(f"  Platform:  {uname.system} {uname.release} ({uname.machine})")
    except Exception:
        pass
    try:
        r = _docker(["info", "--format", "{{json .}}"])
        if r:
            d = json.loads(r)
            print(f"  Docker:    {d.get('ServerVersion', '?')}")
            print(f"  Containers: {d.get('Containers', '?')} ({d.get('ContainersRunning', '?')} running)")
            print(f"  Images:    {d.get('Images', '?')}")
    except Exception:
        pass
    try:
        import psutil
        print(f"  CPU:       {psutil.cpu_percent(interval=0.5)}%")
        mem = psutil.virtual_memory()
        print(f"  Memory:    {mem.percent}% ({mem.used // 1048576}MB / {mem.total // 1048576}MB)")
        disk = psutil.disk_usage("/")
        print(f"  Disk:      {disk.percent}% ({disk.used // 1073741824}GB / {disk.total // 1073741824}GB)")
    except ImportError:
        print("  (install psutil for resource info)")

def cmd_sys_port(args):
    port = args.port
    r = subprocess.run(
        ["ss", "-tlnp", f"sport = :{port}"],
        capture_output=True, text=True, timeout=5
    )
    if r.stdout.strip():
        print(f"Port {port}: IN USE")
        print(r.stdout.strip())
    else:
        print(f"Port {port}: FREE")

# ── log commands ─────────────────────────────────────────────────────────────

LOG_SOURCES = {
    "access": "/var/log/gnukontrolr/access.log",
    "error":  "/var/log/gnukontrolr/error.log",
    "docker": "/var/log/gnukontrolr/docker.log",
}

def cmd_log_sources(args):
    print("Available log sources:")
    for name, path in LOG_SOURCES.items():
        exists = "✓" if os.path.exists(path) else "✗"
        print(f"  {exists} {name:12s} {path}")

def cmd_log_view(args):
    source = LOG_SOURCES.get(args.source)
    if not source:
        eprint(f"Unknown source: {args.source}")
        sys.exit(1)
    if not os.path.exists(source):
        eprint(f"Log file not found: {source}")
        sys.exit(1)
    tail_cmd = ["tail", f"-n{args.lines}", source]
    r = subprocess.run(tail_cmd, capture_output=True, text=True, timeout=5)
    print(r.stdout if r.stdout else "(empty)")

# ── db commands ──────────────────────────────────────────────────────────────

async def cmd_db_status(args):
    header("Database Connections")
    checks = []
    import socket
    for name, host, port in [("MySQL", os.environ.get("MYSQL_HOST", "mysql"), 3306),
                               ("PostgreSQL", "postgres", 5432),
                               ("Redis", "redis", 6379)]:
        try:
            s = socket.create_connection((host, port), timeout=3)
            s.close()
            checks.append((name, "connected"))
        except Exception as e:
            checks.append((name, f"error: {e}"))
    rows = [[n, s] for n, s in checks]
    print_table(rows, ["Database", "Status"])

def cmd_db_mysql(args):
    pw = os.environ.get("MYSQL_ROOT_PASSWORD", "")
    host = os.environ.get("MYSQL_HOST", "mysql")
    cmd = ["mysql", f"-h{host}", "-uroot", f"-p{pw}"]
    os.execvp("mysql", cmd)

def cmd_db_postgres(args):
    pw = os.environ.get("POSTGRES_PASSWORD", "")
    cmd = ["psql", f"postgresql://webpanel:{pw}@postgres:5432/webpanel"]
    os.execvp("psql", cmd)

# ── main dispatcher ──────────────────────────────────────────────────────────

def main():
    parser = _make_parser()
    parser.epilog = textwrap.dedent("""\
        Examples:
          panel user list
          panel user create john john@example.com --role reseller
          panel user reset-pass admin
          panel domain list
          panel service status
          panel container logs webpanel_api --lines 50
          panel dns zones
          panel sys info
          panel db status
    """)
    args = parser.parse_args()
    func = getattr(args, "func", None)
    if not func:
        return cmd_shell(args)
    elif func == cmd_shell:
        cmd_shell(args)
    else:
        func(args)


def _show_tools_list():
    """Print a formatted list of all tools with descriptions."""
    tools = [
        ("user list",            "List all panel users"),
        ("user create",          "Create a new user (auto-generates password)"),
        ("user reset-pass",      "Reset a user's password"),
        ("user delete",          "Delete a user"),
        ("domain list",          "List all domains (--user-id to filter)"),
        ("service status",       "Show all services status & health"),
        ("service restart",      "Restart a service by name"),
        ("container list",       "List all Docker containers"),
        ("container stats",      "Show live container CPU/memory stats"),
        ("container logs",       "View container logs (--lines N)"),
        ("dns zones",            "List PowerDNS zones"),
        ("dns records",          "View DNS records for a zone"),
        ("sys info",             "Show system info (CPU, memory, disk, Docker)"),
        ("sys port",             "Check if a port is free/in use"),
        ("db status",            "Test MySQL, PostgreSQL, Redis connectivity"),
        ("db mysql",             "Open an interactive MySQL shell"),
        ("db postgres",          "Open an interactive PostgreSQL shell"),
        ("update",               "Pull latest code, rebuild & restart"),
        ("log sources",          "List available log sources"),
        ("log view",             "View a log source (--lines N)"),
        ("exit / quit",          "Exit the interactive shell"),
    ]
    print()
    print("  Available commands (type any command directly):")
    print("  " + "─" * 58)
    for cmd, desc in tools:
        print(f"    {cmd:<28s} {desc}")
    print()

def cmd_update(args):
    """Pull latest code, rebuild deps, rebuild Docker images, restart services."""
    from pathlib import Path
    import subprocess
    RED = "\033[0;31m"; GREEN = "\033[0;32m"; YELLOW = "\033[1;33m"
    CYAN = "\033[0;36m"; BOLD = "\033[1m"; NC = "\033[0m"
    INSTALL_DIR = "/opt/gnukontrolr"
    if not Path(INSTALL_DIR).exists():
        print(f"  {RED}Installation not found at {INSTALL_DIR}{NC}")
        return

    print(f"  {CYAN}{BOLD}Update — pulling latest code{NC}")
    r = subprocess.run(["git", "pull", "--ff-only"], cwd=INSTALL_DIR, capture_output=True, text=True)
    if r.returncode == 0:
        print(f"  {GREEN}✓{NC} Code up to date")
    else:
        print(f"  {YELLOW}!{NC} Git pull: {r.stderr.strip()}")

    print(f"\n  {CYAN}{BOLD}Update — npm dependencies{NC}")
    r = subprocess.run(["npm", "install", "--loglevel=warn"], cwd=f"{INSTALL_DIR}/frontend", capture_output=True, text=True)
    if r.returncode == 0:
        print(f"  {GREEN}✓{NC} npm deps updated")
    else:
        print(f"  {YELLOW}!{NC} npm: {(r.stderr or '').split(chr(10))[-2] if r.stderr else r.stdout.split(chr(10))[-2]}")

    print(f"\n  {CYAN}{BOLD}Update — rebuilding frontend{NC}")
    r = subprocess.run(["npm", "run", "build"], cwd=f"{INSTALL_DIR}/frontend", capture_output=True, text=True)
    if r.returncode == 0:
        print(f"  {GREEN}✓{NC} Frontend rebuilt")
    else:
        print(f"  {RED}✗{NC} Frontend build: {(r.stderr or '').split(chr(10))[-3] if r.stderr else r.stdout.split(chr(10))[-3]}")

    print(f"\n  {CYAN}{BOLD}Update — rebuilding panel image{NC}")
    r = subprocess.run(["docker", "compose", "build", "webpanel"], cwd=INSTALL_DIR, capture_output=True, text=True)
    if r.returncode == 0:
        print(f"  {GREEN}✓{NC} Panel image rebuilt")
    else:
        print(f"  {RED}✗{NC} Build: {(r.stderr or '').split(chr(10))[-2] if r.stderr else r.stdout.split(chr(10))[-2]}")

    print(f"\n  {CYAN}{BOLD}Update — restarting containers{NC}")
    r = subprocess.run(["docker", "compose", "up", "-d", "--remove-orphans"], cwd=INSTALL_DIR, capture_output=True, text=True)
    if r.returncode == 0:
        print(f"  {GREEN}✓{NC} All containers running")
    else:
        print(f"  {RED}✗{NC} Restart: {r.stderr.strip()}")

    print(f"\n  {GREEN}{BOLD}Update complete.{NC}")


def cmd_shell(args):
    """Interactive shell — type commands without the 'panel' prefix."""
    import readline
    import shutil
    histfile = os.path.expanduser("~/.panel_history")
    try:
        readline.read_history_file(histfile)
    except (FileNotFoundError, PermissionError):
        pass
    readline.set_history_length(500)

    cols = shutil.get_terminal_size().columns
    print()
    print("  GnuKontrolR CLI — type commands directly.  Type 'exit' or ^D to quit.")
    print("  " + "─" * min(cols - 2, 60))
    print()

    parser = _make_parser()
    while True:
        try:
            line = input("panel> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in ("exit", "quit", "q"):
            break
        if line in ("help", "?"):
            parser.print_help()
            print()
            continue
        if line in ("/list", "list", "/?"):
            _show_tools_list()
            print()
            continue
        try:
            readline.write_history_file(histfile)
        except (FileNotFoundError, PermissionError):
            pass
        if "|" in line or ">" in line or "<" in line:
            os.system(f"panel {line}")
            print()
            continue
        try:
            parsed = parser.parse_args(line.split())
            func = getattr(parsed, "func", None)
            if func:
                func(parsed)
            print()
        except SystemExit:
            pass
        except Exception as e:
            print(f"Error: {e}")
            print()


def _make_parser():
    """Build the argument parser (same as main's)."""
    parser = argparse.ArgumentParser(
        prog=CLI_NAME,
        description="GnuKontrolR panel administration CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--version", action="version", version="GnuKontrolR CLI 1.0")
    sub = parser.add_subparsers(dest="command")

    # ── user ──
    p_user = sub.add_parser("user", help="User management")
    p_user.set_defaults(func=lambda a: asyncio.run(cmd_user_list(a)))
    p_user_sub = p_user.add_subparsers(dest="action")
    p_user_list = p_user_sub.add_parser("list", help="List users")
    p_user_list.set_defaults(func=lambda a: asyncio.run(cmd_user_list(a)))
    p_user_create = p_user_sub.add_parser("create", help="Create user")
    p_user_create.add_argument("username")
    p_user_create.add_argument("email")
    p_user_create.add_argument("--password", "-p", help="Password (auto-generated if omitted)")
    p_user_create.add_argument("--role", "-r", default="user", choices=["user", "admin", "reseller", "superadmin"])
    p_user_create.set_defaults(func=lambda a: asyncio.run(cmd_user_create(a)))
    p_user_rp = p_user_sub.add_parser("reset-pass", help="Reset user password")
    p_user_rp.add_argument("username")
    p_user_rp.add_argument("--password", "-p", help="New password (auto-generated if omitted)")
    p_user_rp.set_defaults(func=lambda a: asyncio.run(cmd_user_reset_pass(a)))
    p_user_del = p_user_sub.add_parser("delete", help="Delete user")
    p_user_del.add_argument("username")
    p_user_del.set_defaults(func=lambda a: asyncio.run(cmd_user_delete(a)))

    # ── domain ──
    p_domain = sub.add_parser("domain", help="Domain management")
    p_domain.set_defaults(func=lambda a: asyncio.run(cmd_domain_list(a)))
    p_domain_sub = p_domain.add_subparsers(dest="action")
    p_domain_list = p_domain_sub.add_parser("list", help="List domains")
    p_domain_list.add_argument("--user-id", "-u", type=int, help="Filter by owner ID")
    p_domain_list.set_defaults(func=lambda a: asyncio.run(cmd_domain_list(a)))

    # ── service ──
    p_svc = sub.add_parser("service", help="Service management")
    p_svc.set_defaults(func=lambda a: cmd_service_status(a))
    p_svc_sub = p_svc.add_subparsers(dest="action")
    p_svc_status = p_svc_sub.add_parser("status", help="Show service status")
    p_svc_status.set_defaults(func=lambda a: cmd_service_status(a))
    p_svc_restart = p_svc_sub.add_parser("restart", help="Restart a service")
    p_svc_restart.add_argument("name", help="Service name")
    p_svc_restart.set_defaults(func=lambda a: cmd_service_restart(a))

    # ── container ──
    p_cont = sub.add_parser("container", aliases=["ct"], help="Container management")
    p_cont.set_defaults(func=lambda a: cmd_container_list(a))
    p_cont_sub = p_cont.add_subparsers(dest="action")
    p_cont_list = p_cont_sub.add_parser("list", help="List containers")
    p_cont_list.set_defaults(func=lambda a: cmd_container_list(a))
    p_cont_logs = p_cont_sub.add_parser("logs", help="Show container logs")
    p_cont_logs.add_argument("name", help="Container name")
    p_cont_logs.add_argument("--lines", "-n", type=int, default=50)
    p_cont_logs.set_defaults(func=lambda a: cmd_container_logs(a))
    p_cont_stats = p_cont_sub.add_parser("stats", help="Show container stats")
    p_cont_stats.set_defaults(func=lambda a: cmd_container_stats(a))

    # ── dns ──
    p_dns = sub.add_parser("dns", help="DNS management")
    p_dns.set_defaults(func=lambda a: cmd_dns_zones(a))
    p_dns_sub = p_dns.add_subparsers(dest="action")
    p_dns_zones = p_dns_sub.add_parser("zones", help="List DNS zones")
    p_dns_zones.set_defaults(func=lambda a: cmd_dns_zones(a))
    p_dns_records = p_dns_sub.add_parser("records", help="List DNS records")
    p_dns_records.add_argument("zone", help="Zone name (e.g. example.com)")
    p_dns_records.set_defaults(func=lambda a: cmd_dns_records(a))

    # ── sys ──
    p_sys = sub.add_parser("sys", help="System info & diagnostics")
    p_sys.set_defaults(func=lambda a: cmd_sys_info(a))
    p_sys_sub = p_sys.add_subparsers(dest="action")
    p_sys_info = p_sys_sub.add_parser("info", help="System information")
    p_sys_info.set_defaults(func=lambda a: cmd_sys_info(a))
    p_sys_port = p_sys_sub.add_parser("port", help="Check port availability")
    p_sys_port.add_argument("port", type=int)
    p_sys_port.set_defaults(func=lambda a: cmd_sys_port(a))

    # ── log ──
    p_log = sub.add_parser("log", help="Log viewer")
    p_log.set_defaults(func=lambda a: cmd_log_sources(a))
    p_log_sub = p_log.add_subparsers(dest="action")
    p_log_sources = p_log_sub.add_parser("sources", help="List log sources")
    p_log_sources.set_defaults(func=lambda a: cmd_log_sources(a))
    p_log_view = p_log_sub.add_parser("view", help="View log")
    p_log_view.add_argument("source", help="Log source")
    p_log_view.add_argument("--lines", "-n", type=int, default=50)
    p_log_view.set_defaults(func=lambda a: cmd_log_view(a))

    # ── db ──
    p_db = sub.add_parser("db", help="Database tools")
    p_db.set_defaults(func=lambda a: asyncio.run(cmd_db_status(a)))
    p_db_sub = p_db.add_subparsers(dest="action")
    p_db_status = p_db_sub.add_parser("status", help="Database connection status")
    p_db_status.set_defaults(func=lambda a: asyncio.run(cmd_db_status(a)))
    p_db_mysql = p_db_sub.add_parser("mysql", help="Open MySQL shell")
    p_db_mysql.set_defaults(func=lambda a: cmd_db_mysql(a))
    p_db_postgres = p_db_sub.add_parser("postgres", help="Open PostgreSQL shell")
    p_db_postgres.set_defaults(func=lambda a: cmd_db_postgres(a))

    # ── update ──
    p_update = sub.add_parser("update", help="Pull latest code, rebuild deps & containers, restart")
    p_update.set_defaults(func=lambda a: cmd_update(a))

    # ── shell ──
    p_shell = sub.add_parser("shell", aliases=["sh", "repl"], help="Interactive shell mode")
    p_shell.set_defaults(func=cmd_shell)

    return parser

if __name__ == "__main__":
    main()
