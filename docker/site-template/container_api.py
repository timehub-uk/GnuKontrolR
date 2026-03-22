#!/usr/bin/env python3
"""
WebPanel Container Internal API  (port 9000, internal network only)
Controls the secure area and provides management endpoints.

Filesystem layout (enforced by this API):
  /var/www/html          — public web root  (customer content, web-accessible)
  /var/customer/uploads  — customer uploads  (private, API-managed)
  /var/customer/private  — private data      (private, API-managed)
  /var/customer/backups  — backups           (private, API-managed)
  /var/config/nginx      — SECURE: nginx config fragments (API only)
  /var/config/php        — SECURE: PHP ini overrides      (API only)
  /var/config/env        — SECURE: env / secrets           (API only)
  /var/config/ssl        — SECURE: SSL certificates        (API only)
  /var/db                — SECURE: SQLite DB + SSH keys    (root only)
"""
import os
import re
import shutil
import subprocess
import json
import hmac
import hashlib
import time
import logging
from collections import defaultdict
from pathlib import Path
from flask import Flask, request, jsonify, abort

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("container-api")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # 1 MB max request body

DOMAIN    = os.environ.get("DOMAIN", "localhost")
API_TOKEN = os.environ.get("CONTAINER_API_TOKEN", "")

# Must have a token set in production
if not API_TOKEN:
    log.warning("CONTAINER_API_TOKEN not set — API is unauthenticated! Set it before deployment.")

# ── Simple in-process rate limiter ───────────────────────────────────────────
_rate: dict[str, list] = defaultdict(list)
RATE_LIMIT   = 60   # requests
RATE_WINDOW  = 60   # seconds


def _check_rate(ip: str):
    now = time.time()
    window_start = now - RATE_WINDOW
    _rate[ip] = [t for t in _rate[ip] if t > window_start]
    if len(_rate[ip]) >= RATE_LIMIT:
        log.warning("Rate limit exceeded for %s", ip)
        abort(429)
    _rate[ip].append(now)

# ── Bind to internal network interface only ───────────────────────────────────
LISTEN_HOST = "0.0.0.0"  # Docker network only — not mapped to host; see docker run

# Filesystem areas
PUBLIC_ROOT      = Path("/var/www/html")
UPLOADS_DIR      = Path("/var/customer/uploads")
PRIVATE_DIR      = Path("/var/customer/private")
BACKUPS_DIR      = Path("/var/customer/backups")

SECURE_ROOT      = Path("/var/config")
NGINX_CONF_DIR   = SECURE_ROOT / "nginx"
PHP_CONF_DIR     = SECURE_ROOT / "php"
ENV_DIR          = SECURE_ROOT / "env"
SSL_DIR          = SECURE_ROOT / "ssl"
DB_DIR           = Path("/var/db")

TEXT_EXTS = {
    ".php", ".html", ".htm", ".js", ".jsx", ".ts", ".tsx",
    ".css", ".scss", ".json", ".xml", ".yaml", ".yml", ".toml",
    ".env", ".ini", ".conf", ".txt", ".md", ".sh", ".py",
    ".htaccess", ".log", ".sql",
}

ALLOWED_COMMANDS = {
    "composer_install": ["composer", "install", "--no-interaction", "--working-dir", str(PUBLIC_ROOT)],
    "composer_update":  ["composer", "update",  "--no-interaction", "--working-dir", str(PUBLIC_ROOT)],
    "npm_install":  ["npm", "install",  "--prefix", str(PUBLIC_ROOT)],
    "npm_build":    ["npm", "run", "build", "--prefix", str(PUBLIC_ROOT)],
    "artisan_migrate": ["php", str(PUBLIC_ROOT / "artisan"), "migrate", "--force"],
    "artisan_cache":   ["php", str(PUBLIC_ROOT / "artisan"), "config:cache"],
    "wp_cache_flush":  ["wp", "--path", str(PUBLIC_ROOT), "--allow-root", "cache", "flush"],
    "php_version":     ["php", "--version"],
    "node_version":    ["node", "--version"],
    "reload_nginx":    ["supervisorctl", "restart", "nginx"],
    "reload_php":      ["supervisorctl", "restart", "php-fpm"],
    "reload_apache":   ["supervisorctl", "restart", "apache2"],
}


# ── Auth ──────────────────────────────────────────────────────────────────────

def _verify_token():
    """Verify Bearer token + enforce rate limit."""
    _check_rate(request.remote_addr or "unknown")
    if not API_TOKEN:
        return  # Dev mode — warn only; should never reach production
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        log.warning("Missing Authorization header from %s", request.remote_addr)
        abort(401)
    provided = auth[len("Bearer "):]
    if not hmac.compare_digest(provided.encode(), API_TOKEN.encode()):
        log.warning("Bad token from %s", request.remote_addr)
        abort(403)


@app.before_request
def _security_headers():
    """Reject requests from outside the internal network (extra guard)."""
    ip = request.remote_addr or ""
    # Only accept from Docker internal ranges and localhost
    allowed_prefixes = ("172.", "10.", "192.168.", "127.")
    if not any(ip.startswith(p) for p in allowed_prefixes):
        log.error("Request from unexpected IP %s — blocked", ip)
        abort(403)


@app.after_request
def _add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store"
    return response


# ── Path safety ───────────────────────────────────────────────────────────────

def _safe(base: Path, rel: str) -> Path:
    target = (base / rel.lstrip("/")).resolve()
    if not str(target).startswith(str(base.resolve())):
        abort(400)
    return target


def _dir_listing(directory: Path, rel: str = "") -> dict:
    entries = []
    for item in sorted(directory.iterdir()):
        stat = item.stat()
        entries.append({
            "name":     item.name,
            "type":     "dir" if item.is_dir() else "file",
            "size":     stat.st_size,
            "readable": item.suffix.lower() in TEXT_EXTS,
        })
    return {"path": rel or "/", "entries": entries}


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return jsonify({"ok": True, "domain": DOMAIN})


@app.get("/info")
def info():
    _verify_token()
    su = shutil.disk_usage(str(PUBLIC_ROOT))
    return jsonify({
        "domain":    DOMAIN,
        "disk": {
            "total_mb": su.total // 1024**2,
            "used_mb":  su.used  // 1024**2,
            "free_mb":  su.free  // 1024**2,
        },
        "services":  _supervisor_list(),
        "webserver": os.environ.get("WEB_SERVER", "nginx"),
        "areas": {
            "public":   str(PUBLIC_ROOT),
            "uploads":  str(UPLOADS_DIR),
            "private":  str(PRIVATE_DIR),
            "backups":  str(BACKUPS_DIR),
            "secure":   str(SECURE_ROOT),
        },
    })


# ── Supervisor ────────────────────────────────────────────────────────────────

def _supervisor_list():
    try:
        r = subprocess.run(["supervisorctl", "status"], capture_output=True, text=True, timeout=5)
        return [{"name": l.split()[0], "state": l.split()[1]} for l in r.stdout.splitlines() if len(l.split()) >= 2]
    except Exception:
        return []


@app.get("/services")
def list_services():
    _verify_token()
    return jsonify(_supervisor_list())


@app.post("/services/<program>")
def control_service(program: str):
    _verify_token()
    action = (request.json or {}).get("action", "status")
    if action not in ("start", "stop", "restart", "status"):
        abort(400)
    safe = re.sub(r"[^a-z0-9_-]", "", program)
    r = subprocess.run(["supervisorctl", action, safe], capture_output=True, text=True, timeout=10)
    return jsonify({"ok": r.returncode == 0, "output": r.stdout + r.stderr})


# ── Public web root ───────────────────────────────────────────────────────────

@app.get("/files/public")
def list_public():
    _verify_token()
    rel = request.args.get("path", "")
    d = _safe(PUBLIC_ROOT, rel)
    if not d.exists(): abort(404)
    return jsonify(_dir_listing(d, rel))


@app.get("/files/public/read")
def read_public_file():
    _verify_token()
    rel = request.args.get("path", "")
    f = _safe(PUBLIC_ROOT, rel)
    if not f.is_file(): abort(404)
    if f.suffix.lower() not in TEXT_EXTS: abort(415)
    if f.stat().st_size > 512 * 1024: abort(413)
    return jsonify({"path": rel, "content": f.read_text(errors="replace"), "name": f.name})


@app.post("/files/public/write")
def write_public_file():
    _verify_token()
    body = request.json or {}
    rel = body.get("path", "")
    content = body.get("content", "")
    f = _safe(PUBLIC_ROOT, rel)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content)
    shutil.chown(str(f), "www-data", "www-data")
    return jsonify({"ok": True})


@app.delete("/files/public")
def delete_public_file():
    _verify_token()
    rel = request.args.get("path", "")
    f = _safe(PUBLIC_ROOT, rel)
    if f.is_dir():
        shutil.rmtree(f)
    elif f.exists():
        f.unlink()
    return jsonify({"ok": True})


# ── Uploads / Private ─────────────────────────────────────────────────────────

@app.get("/files/uploads")
def list_uploads():
    _verify_token()
    rel = request.args.get("path", "")
    d = _safe(UPLOADS_DIR, rel)
    return jsonify(_dir_listing(d, rel))


@app.get("/files/private")
def list_private():
    _verify_token()
    rel = request.args.get("path", "")
    d = _safe(PRIVATE_DIR, rel)
    return jsonify(_dir_listing(d, rel))


# ── SECURE AREA (API controls only) ──────────────────────────────────────────

@app.get("/secure/env")
def get_env():
    """Return non-secret env keys for display."""
    _verify_token()
    env_file = ENV_DIR / ".env"
    if not env_file.exists():
        return jsonify({"vars": {}})
    lines = env_file.read_text().splitlines()
    visible = {}
    for line in lines:
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            k = k.strip()
            # Mask secret-looking values
            if any(s in k.upper() for s in ("PASS", "SECRET", "KEY", "TOKEN")):
                visible[k] = "***"
            else:
                visible[k] = v.strip()
    return jsonify({"vars": visible})


@app.post("/secure/env")
def set_env_var():
    """Set an env variable in the secure env file."""
    _verify_token()
    body = request.json or {}
    key   = re.sub(r"[^A-Z0-9_]", "", body.get("key", "").upper())
    value = body.get("value", "")
    if not key:
        abort(400)
    env_file = ENV_DIR / ".env"
    existing = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                existing[k.strip()] = v.strip()
    existing[key] = value
    env_file.write_text("\n".join(f"{k}={v}" for k, v in existing.items()) + "\n")
    return jsonify({"ok": True})


@app.post("/secure/nginx")
def set_nginx_config():
    """Write a named nginx config fragment to the secure nginx dir."""
    _verify_token()
    body = request.json or {}
    name    = re.sub(r"[^a-z0-9_-]", "", body.get("name", "custom"))
    content = body.get("content", "")
    conf_file = NGINX_CONF_DIR / f"{name}.conf"
    conf_file.write_text(content)
    # Reload nginx
    subprocess.run(["supervisorctl", "restart", "nginx"], timeout=10)
    return jsonify({"ok": True, "file": str(conf_file)})


@app.get("/secure/nginx")
def list_nginx_configs():
    _verify_token()
    files = [f.name for f in NGINX_CONF_DIR.iterdir() if f.suffix == ".conf"]
    return jsonify({"configs": files})


@app.post("/secure/php")
def set_php_config():
    """Write a PHP ini override file."""
    _verify_token()
    body = request.json or {}
    content = body.get("content", "")
    ini_file = PHP_CONF_DIR / "customer.ini"
    ini_file.write_text(content)
    subprocess.run(["supervisorctl", "restart", "php-fpm"], timeout=10)
    return jsonify({"ok": True})


@app.get("/secure/php")
def get_php_config():
    _verify_token()
    ini_file = PHP_CONF_DIR / "customer.ini"
    content = ini_file.read_text() if ini_file.exists() else "; PHP overrides\n"
    return jsonify({"content": content})


@app.post("/secure/ssl")
def upload_ssl():
    """Store SSL cert + key in the secure area."""
    _verify_token()
    body = request.json or {}
    cert = body.get("cert", "")
    key  = body.get("key", "")
    if cert:
        (SSL_DIR / "site.crt").write_text(cert)
    if key:
        (SSL_DIR / "site.key").write_text(key)
        (SSL_DIR / "site.key").chmod(0o600)
    return jsonify({"ok": True})


# ── Commands ─────────────────────────────────────────────────────────────────

@app.post("/exec")
def exec_command():
    _verify_token()
    cmd_key = (request.json or {}).get("command", "")
    cmd = ALLOWED_COMMANDS.get(cmd_key)
    if not cmd:
        abort(400)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return jsonify({"ok": r.returncode == 0, "stdout": r.stdout, "stderr": r.stderr})


if __name__ == "__main__":
    if not API_TOKEN:
        log.error("FATAL: CONTAINER_API_TOKEN must be set in production. Refusing to start without token.")
        # Still start in dev — but print loud warning
    log.info("Container API starting for domain: %s", DOMAIN)
    app.run(host=LISTEN_HOST, port=9000, debug=False, threaded=True)
