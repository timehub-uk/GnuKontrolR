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
import threading
import secrets
import string
import urllib.request
import tempfile
from collections import defaultdict
from pathlib import Path
from flask import Flask, request, jsonify, abort

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("container-api")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # 1 MB max request body

DOMAIN    = os.environ.get("DOMAIN", "localhost")
API_TOKEN = os.environ.get("CONTAINER_API_TOKEN", "")

# Refuse to start without a token — unauthenticated container APIs are a critical risk
if not API_TOKEN:
    import sys
    log.critical("CONTAINER_API_TOKEN is not set. Refusing to start — all requests would be unauthenticated.")
    sys.exit(1)

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


@app.post("/files/public/mkdir")
def mkdir_public():
    _verify_token()
    body = request.json or {}
    rel = body.get("path", "")
    d = _safe(PUBLIC_ROOT, rel)
    d.mkdir(parents=True, exist_ok=True)
    shutil.chown(str(d), "www-data", "www-data")
    return jsonify({"ok": True})


@app.post("/files/public/upload")
def upload_public_file():
    """Upload a file into the public web root.
    Optionally scans with ClamAV (clamscan) if available.
    Multipart form: file=<binary>, path=<target directory (relative)>.
    """
    _verify_token()
    if "file" not in request.files:
        abort(400)
    from flask import Request as _Req
    f = request.files["file"]
    rel_dir = request.form.get("path", "")
    dest_dir = _safe(PUBLIC_ROOT, rel_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Sanitise filename
    fname = Path(f.filename).name if f.filename else "upload"
    fname = re.sub(r'[^\w.\-]', '_', fname)
    dest = dest_dir / fname

    # Save to temp location first for scanning
    with tempfile.NamedTemporaryFile(delete=False, suffix=fname) as tmp:
        tmp_path = tmp.name
        f.save(tmp_path)

    # ClamAV scan (best-effort — if clamscan not installed, skip)
    scan_result = "skipped"
    try:
        result = subprocess.run(
            ["clamscan", "--no-summary", tmp_path],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 1:
            os.unlink(tmp_path)
            return jsonify({"ok": False, "error": "Malware detected — file rejected", "scan": "infected"}), 400
        scan_result = "clean"
    except FileNotFoundError:
        scan_result = "clamscan_not_installed"
    except subprocess.TimeoutExpired:
        scan_result = "scan_timeout"

    # Move to destination + fix ownership
    shutil.move(tmp_path, str(dest))
    shutil.chown(str(dest), "www-data", "www-data")

    return jsonify({
        "ok":       True,
        "filename": dest.name,
        "path":     str(dest.relative_to(PUBLIC_ROOT)),
        "scan":     scan_result,
    })


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


# ── Config backup helpers ─────────────────────────────────────────────────────

CONFIG_BACKUPS_ROOT = SECURE_ROOT / ".backups"
BACKUP_KEEP         = 3   # rolling window depth

AREA_DIRS = {
    "nginx": NGINX_CONF_DIR,
    "php":   PHP_CONF_DIR,
    "env":   ENV_DIR,
    "ssl":   SSL_DIR,
}


def _backup_file(filepath: Path):
    """Snapshot filepath into .backups/{area}/{filename}/, keeping BACKUP_KEEP versions."""
    if not filepath.exists():
        return
    area = filepath.parent.name          # nginx / php / env / ssl
    snap_dir = CONFIG_BACKUPS_ROOT / area / filepath.name
    snap_dir.mkdir(parents=True, exist_ok=True)
    ts   = str(int(time.time()))
    dest = snap_dir / f"{ts}.bak"
    shutil.copy2(str(filepath), str(dest))
    # Purge oldest beyond the keep limit
    snaps = sorted(snap_dir.glob("*.bak"), key=lambda p: int(p.stem))
    for old in snaps[:-BACKUP_KEEP]:
        old.unlink(missing_ok=True)
    log.info("Backed up %s → %s", filepath, dest)


@app.get("/backups/<area>")
def list_backups(area: str):
    """List rolling snapshots for a config area (nginx/php/env/ssl)."""
    _verify_token()
    if area not in AREA_DIRS:
        abort(400)
    backup_root = CONFIG_BACKUPS_ROOT / area
    if not backup_root.exists():
        return jsonify({"area": area, "files": []})
    result = []
    for file_dir in sorted(backup_root.iterdir()):
        if not file_dir.is_dir():
            continue
        snaps = sorted(file_dir.glob("*.bak"), key=lambda p: int(p.stem), reverse=True)
        if snaps:
            result.append({
                "filename": file_dir.name,
                "snapshots": [
                    {
                        "ts":       int(s.stem),
                        "size":     s.stat().st_size,
                        "datetime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(s.stem))),
                    }
                    for s in snaps
                ],
            })
    return jsonify({"area": area, "files": result})


@app.post("/restore/<area>")
def restore_backup(area: str):
    """Restore a named snapshot — saves current state first, then overwrites."""
    _verify_token()
    if area not in AREA_DIRS:
        abort(400)
    body     = request.json or {}
    filename = re.sub(r"[^a-zA-Z0-9._-]", "", body.get("filename", ""))
    ts_raw   = re.sub(r"[^0-9]",          "", str(body.get("ts", "")))
    if not filename or not ts_raw:
        abort(400)
    snap = CONFIG_BACKUPS_ROOT / area / filename / f"{ts_raw}.bak"
    if not snap.exists():
        abort(404)
    target = AREA_DIRS[area] / filename
    _backup_file(target)   # snapshot current before overwriting
    shutil.copy2(str(snap), str(target))
    # Reload affected service
    if area == "nginx":
        subprocess.run(["supervisorctl", "restart", "nginx"],   timeout=10)
    elif area == "php":
        subprocess.run(["supervisorctl", "restart", "php-fpm"], timeout=10)
    log.info("Restored %s/%s from ts=%s", area, filename, ts_raw)
    return jsonify({"ok": True, "restored": filename, "from_ts": int(ts_raw)})


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
    _backup_file(env_file)
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
    _backup_file(conf_file)
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
    _backup_file(ini_file)
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
        _backup_file(SSL_DIR / "site.crt")
        (SSL_DIR / "site.crt").write_text(cert)
    if key:
        _backup_file(SSL_DIR / "site.key")
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


# ══════════════════════════════════════════════════════════════════════════════
# ── One-Click App Marketplace ─────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

APP_CACHE_DIR       = Path("/var/cache/gnukontrolr/apps")
DOMAIN_TMP_DIR      = Path("/var/customer/tmp")   # per-domain tmp — real FS, not tmpfs
INSTALLED_APPS_FILE = DB_DIR / "installed_apps.json"
_MYSQL_PASS_FILE    = DB_DIR / "mysql_root_pass"

def _mysql_root_pass() -> str:
    """Read the private MariaDB root password (written by entrypoint on first boot)."""
    if _MYSQL_PASS_FILE.exists():
        return _MYSQL_PASS_FILE.read_text().strip()
    return os.environ.get("MYSQL_ROOT_PASSWORD", "")

# In-memory job tracking (survives until container restart)
_install_jobs: dict = {}

APP_DOWNLOADS = {
    "wordpress":  ("https://wordpress.org/latest.tar.gz",                                               "wordpress.tar.gz"),
    "joomla":     ("https://downloads.joomla.org/cms/joomla5/latest/Joomla_latest-Stable-Full_Package.tar.gz", "joomla.tar.gz"),
    "drupal":     ("https://www.drupal.org/download-latest/tar.gz",                                      "drupal.tar.gz"),
    "grav":       ("https://getgrav.org/download/core/grav/latest",                                      "grav.zip"),
    "roundcube":  ("https://github.com/roundcube/roundcubemail/releases/download/1.6.9/roundcubemail-1.6.9-complete.tar.gz", "roundcube.tar.gz"),
    "snappymail": ("https://github.com/the-djmaze/snappymail/releases/download/v2.38.2/snappymail-2.38.2.tar.gz", "snappymail.tar.gz"),
    "phpmyadmin": ("https://files.phpmyadmin.net/phpMyAdmin/5.2.2/phpMyAdmin-5.2.2-all-languages.tar.gz",  "phpmyadmin.tar.gz"),
    "adminer":    ("https://github.com/vrana/adminer/releases/download/v4.8.1/adminer-4.8.1.php",         "adminer.php"),
    "ghost":        ("https://github.com/TryGhost/Ghost/releases/download/v5.82.2/Ghost-5.82.2.zip",                                                                "ghost.zip"),
    "october":      ("https://github.com/octobercms/october/archive/refs/tags/v3.5.30.tar.gz",                                                                      "october.tar.gz"),
    "concrete":     ("https://www.concretecms.org/download_file/-/view/110619/",                                                                                     "concrete.zip"),
    "typo3":        ("https://get.typo3.org/12/tar.gz",                                                                                                              "typo3.tar.gz"),
    "strapi":       ("https://registry.npmjs.org/create-strapi-app/-/create-strapi-app-4.25.4.tgz",                                                                  "strapi.tgz"),
    "matomo":       ("https://builds.matomo.org/matomo-5.0.3.zip",                                                                                                   "matomo.zip"),
    "umami":        ("https://github.com/umami-software/umami/archive/refs/tags/v2.10.2.tar.gz",                                                                     "umami.tar.gz"),
    "freshrss":     ("https://github.com/FreshRSS/FreshRSS/archive/refs/tags/1.24.1.tar.gz",                                                                        "freshrss.tar.gz"),
    "nextcloud":    ("https://download.nextcloud.com/server/releases/nextcloud-28.0.3.tar.bz2",                                                                      "nextcloud.tar.bz2"),
    "bookstack":    ("https://github.com/BookStackApp/BookStack/archive/refs/tags/v23.12.2.tar.gz",                                                                  "bookstack.tar.gz"),
    "wikijs":       ("https://github.com/requarks/wiki/releases/download/v2.5.303/wiki-js.tar.gz",                                                                   "wikijs.tar.gz"),
    "gitea":        ("https://dl.gitea.com/gitea/1.21.11/gitea-1.21.11-linux-amd64",                                                                                "gitea-bin"),
    "codeserver":   ("https://github.com/coder/code-server/releases/download/v4.22.1/code-server-4.22.1-linux-amd64.tar.gz",                                        "codeserver.tar.gz"),
    "n8n":          ("https://registry.npmjs.org/n8n/-/n8n-1.36.4.tgz",                                                                                             "n8n.tgz"),
    "nodered":      ("https://registry.npmjs.org/@node-red/node-red/-/node-red-3.1.9.tgz",                                                                           "nodered.tgz"),
    "filebrowser":  ("https://github.com/filebrowser/filebrowser/releases/download/v2.27.0/linux-amd64-filebrowser.tar.gz",                                         "filebrowser.tar.gz"),
    "uptime":       ("https://github.com/louislam/uptime-kuma/archive/refs/tags/1.23.11.tar.gz",                                                                     "uptime-kuma.tar.gz"),
    "vaultwarden":  ("https://github.com/dani-garcia/vaultwarden/releases/download/1.30.5/vaultwarden-1.30.5-linux-amd64.tar.gz",                                   "vaultwarden.tar.gz"),
    "invoiceninja": ("https://github.com/invoiceninja/invoiceninja/releases/download/v5.8.40/invoiceninja.zip",                                                      "invoiceninja.zip"),
    "prestashop":  ("https://github.com/PrestaShop/PrestaShop/releases/download/8.1.7/prestashop_8.1.7.zip", "prestashop.zip"),
    "opencart":    ("https://github.com/opencart/opencart/releases/download/4.0.2.3/opencart-4.0.2.3.tar.gz", "opencart.tar.gz"),
    "woocommerce": ("https://wordpress.org/latest.tar.gz", "wordpress-woo.tar.gz"),  # WP+WooCommerce
    "piwigo":      ("https://piwigo.org/download/dlcounter.php?code=latest", "piwigo.zip"),
    "lychee":      ("https://github.com/LycheeOrg/Lychee/releases/download/v5.5.1/Lychee.zip", "lychee.zip"),
    "jellyfin":    ("https://github.com/jellyfin/jellyfin/releases/download/v10.9.2/jellyfin_10.9.2_linux-amd64.tar.gz", "jellyfin.tar.gz"),
    "moodle":      ("https://download.moodle.org/download.php/direct/stable404/moodle-latest-404.tgz", "moodle.tgz"),
    "monica":      ("https://github.com/monicahq/monica/releases/download/v4.1.2/monica-v4.1.2.tar.gz", "monica.tar.gz"),
    "yourls":      ("https://github.com/YOURLS/YOURLS/releases/download/1.9.2/yourls-1.9.2.zip", "yourls.zip"),
    "grafana":     ("https://dl.grafana.com/oss/release/grafana-10.4.2.linux-amd64.tar.gz", "grafana.tar.gz"),
    "netdata":     ("https://github.com/netdata/netdata/releases/download/v1.45.0/netdata-v1.45.0.tar.gz", "netdata.tar.gz"),
}


def _rand_str(n: int = 20) -> str:
    return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(n))


def _push(job_id: str, msg: str):
    log.info("[install:%s] %s", job_id, msg)
    if job_id in _install_jobs:
        _install_jobs[job_id]["messages"].append(msg)


def _mysql_exec(sql: str) -> tuple[bool, str]:
    """Execute SQL on the private local MariaDB instance via unix socket."""
    root_pass = _mysql_root_pass()
    cmd = ["mysql", "--socket=/var/run/mysqld/mysqld.sock", "-uroot", "--batch", "--silent"]
    if root_pass:
        cmd += [f"-p{root_pass}"]
    cmd += ["-e", sql]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return r.returncode == 0, (r.stderr or r.stdout).strip()


def _safe_sql_identifier(s: str, max_len: int = 32) -> str:
    """Strip all non-alphanumeric/underscore chars to make a safe SQL identifier."""
    import re as _re2
    clean = _re2.sub(r'[^\w]', '_', s)[:max_len]
    if not clean or not clean[0].isalpha():
        clean = 'db_' + clean[:max_len - 3]
    return clean


def _escape_sql_string(s: str) -> str:
    """Escape a value for use inside single quotes in SQL (last-resort guard)."""
    return s.replace('\\', '\\\\').replace("'", "\\'").replace('\0', '').replace('\n', '\\n')


def _create_db(db_name: str, db_user: str, db_pass: str) -> tuple[bool, str]:
    # Sanitise identifiers — must be alphanumeric/underscore only
    safe_name = _safe_sql_identifier(db_name)
    safe_user = _safe_sql_identifier(db_user)
    # Escape password string value
    safe_pass = _escape_sql_string(db_pass)
    sql = (
        f"CREATE DATABASE IF NOT EXISTS `{safe_name}` "
        f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; "
        f"CREATE USER IF NOT EXISTS '{safe_user}'@'localhost' IDENTIFIED BY '{safe_pass}'; "
        f"GRANT ALL PRIVILEGES ON `{safe_name}`.* TO '{safe_user}'@'localhost'; "
        f"FLUSH PRIVILEGES;"
    )
    return _mysql_exec(sql)


def _download_cached(app_id: str, url: str, filename: str, job_id: str) -> Path:
    APP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = APP_CACHE_DIR / filename
    if dest.exists():
        _push(job_id, f"Using cached package ({dest.stat().st_size // 1024} KB)")
    else:
        _push(job_id, f"Downloading {app_id} from official source…")
        req = urllib.request.Request(url, headers={"User-Agent": "GnuKontrolR/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp, open(str(dest), "wb") as fh:
            shutil.copyfileobj(resp, fh)
        _push(job_id, f"Downloaded {dest.stat().st_size // 1024} KB")
    return dest


def _set_permissions(path: Path):
    subprocess.run(["chown", "-R", "www-data:www-data", str(path)], timeout=60, check=False)
    subprocess.run(["find", str(path), "-type", "d", "-exec", "chmod", "755", "{}", "+"], timeout=60, check=False)
    subprocess.run(["find", str(path), "-type", "f", "-exec", "chmod", "644", "{}", "+"], timeout=60, check=False)


def _target_dir(install_path: str) -> Path:
    """Resolve the webroot install target safely."""
    rel = install_path.strip("/") or ""
    if rel:
        tgt = (PUBLIC_ROOT / rel).resolve()
        if not str(tgt).startswith(str(PUBLIC_ROOT.resolve())):
            raise ValueError("Invalid install path")
        tgt.mkdir(parents=True, exist_ok=True)
        return tgt
    return PUBLIC_ROOT


def _record_installed(app_id: str, result: dict):
    data: dict = {}
    if INSTALLED_APPS_FILE.exists():
        try:
            data = json.loads(INSTALLED_APPS_FILE.read_text())
        except Exception:
            pass
    data.setdefault("apps", [])
    data["apps"] = [a for a in data["apps"] if a.get("id") != app_id]
    data["apps"].append({"id": app_id, "installed_at": int(time.time()), **result})
    INSTALLED_APPS_FILE.write_text(json.dumps(data, indent=2))


# ── Per-app installers ────────────────────────────────────────────────────────

def _install_wordpress(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["wordpress"]
    archive = _download_cached("wordpress", url, filename, job_id)

    _push(job_id, "Extracting WordPress…")
    tgt = _target_dir(cfg.get("install_path", "/"))
    DOMAIN_TMP_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(DOMAIN_TMP_DIR)) as tmp:
        subprocess.run(["tar", "-xzf", str(archive), "-C", tmp], check=True, timeout=120)
        wp_src = Path(tmp) / "wordpress"
        for item in wp_src.iterdir():
            dst = tgt / item.name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            (shutil.copytree if item.is_dir() else shutil.copy2)(str(item), str(dst))

    db_name, db_user, db_pass = cfg["db_name"], cfg["db_user"], cfg["db_pass"]
    _push(job_id, f"Creating database `{db_name}`…")
    ok, err = _create_db(db_name, db_user, db_pass)
    if not ok:
        raise RuntimeError(f"Database creation failed: {err}")

    _push(job_id, "Writing wp-config.php…")
    sample = tgt / "wp-config-sample.php"
    if not sample.exists():
        raise RuntimeError("wp-config-sample.php not found — extraction may have failed")
    content = sample.read_text()
    for old, new in [("database_name_here", db_name), ("username_here", db_user),
                     ("password_here", db_pass)]:
        content = content.replace(old, new, 1)
    # DB_HOST in wp-config stays as 'localhost' — MariaDB socket on same container
    # Replace placeholder security keys with random values
    for _ in range(8):
        content = content.replace("put your unique phrase here", _rand_str(64), 1)
    (tgt / "wp-config.php").write_text(content)

    _push(job_id, "Setting file permissions…")
    _set_permissions(tgt)

    # Try WP-CLI for headless install
    wp_cli = shutil.which("wp")
    if wp_cli:
        _push(job_id, "Running wp-cli installer…")
        r = subprocess.run([
            wp_cli, "core", "install",
            f"--url=https://{DOMAIN}", f"--title={cfg.get('site_title','My Site')}",
            f"--admin_user={cfg.get('admin_user','admin')}",
            f"--admin_password={cfg['admin_pass']}",
            f"--admin_email={cfg.get('admin_email','admin@'+DOMAIN)}",
            "--path", str(tgt), "--allow-root",
        ], capture_output=True, text=True, timeout=120)
        if r.returncode == 0:
            _push(job_id, "WordPress fully installed via WP-CLI ✓")
        else:
            _push(job_id, "WP-CLI step failed — complete setup via browser wizard")
    else:
        _push(job_id, "WP-CLI not found — visit the site URL to complete setup via browser wizard")

    return {"url": f"https://{DOMAIN}", "admin_url": f"https://{DOMAIN}/wp-admin/"}


def _install_joomla(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["joomla"]
    archive = _download_cached("joomla", url, filename, job_id)
    tgt = _target_dir(cfg.get("install_path", "/"))

    _push(job_id, "Extracting Joomla…")
    DOMAIN_TMP_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(["tar", "-xzf", str(archive), "-C", str(tgt)], check=True, timeout=120)

    db_name, db_user, db_pass = cfg["db_name"], cfg["db_user"], cfg["db_pass"]
    _push(job_id, f"Creating database `{db_name}`…")
    ok, err = _create_db(db_name, db_user, db_pass)
    if not ok:
        raise RuntimeError(f"Database creation failed: {err}")

    _push(job_id, "Setting file permissions…")
    _set_permissions(tgt)
    _push(job_id, "Joomla files extracted ✓ — visit the site URL to complete the web installer")

    return {"url": f"https://{DOMAIN}", "admin_url": f"https://{DOMAIN}/administrator/"}


def _install_drupal(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["drupal"]
    archive = _download_cached("drupal", url, filename, job_id)
    tgt = _target_dir(cfg.get("install_path", "/"))

    _push(job_id, "Extracting Drupal…")
    DOMAIN_TMP_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(DOMAIN_TMP_DIR)) as tmp:
        subprocess.run(["tar", "-xzf", str(archive), "-C", tmp], check=True, timeout=120)
        extracted = sorted(Path(tmp).iterdir())[0]  # drupal-10.x.y/
        for item in extracted.iterdir():
            dst = tgt / item.name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            (shutil.copytree if item.is_dir() else shutil.copy2)(str(item), str(dst))

    db_name, db_user, db_pass = cfg["db_name"], cfg["db_user"], cfg["db_pass"]
    _push(job_id, f"Creating database `{db_name}`…")
    ok, err = _create_db(db_name, db_user, db_pass)
    if not ok:
        raise RuntimeError(f"Database creation failed: {err}")

    _set_permissions(tgt)
    _push(job_id, "Drupal extracted ✓ — complete installation via the web installer")
    return {"url": f"https://{DOMAIN}", "admin_url": f"https://{DOMAIN}/core/install.php"}


def _install_grav(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["grav"]
    archive = _download_cached("grav", url, filename, job_id)
    tgt = _target_dir(cfg.get("install_path", "/"))

    _push(job_id, "Extracting Grav…")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["unzip", "-q", str(archive), "-d", tmp], check=True, timeout=60)
        src = Path(tmp) / "grav"
        for item in src.iterdir():
            dst = tgt / item.name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            (shutil.copytree if item.is_dir() else shutil.copy2)(str(item), str(dst))

    _set_permissions(tgt)
    _push(job_id, "Grav extracted ✓ — no database required, site is ready")
    return {"url": f"https://{DOMAIN}"}


def _install_roundcube(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["roundcube"]
    archive = _download_cached("roundcube", url, filename, job_id)
    ipath = cfg.get("install_path", "webmail").strip("/") or "webmail"
    tgt = _target_dir(ipath)

    _push(job_id, "Extracting Roundcube…")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["tar", "-xzf", str(archive), "-C", tmp], check=True, timeout=60)
        src = sorted(Path(tmp).iterdir())[0]
        for item in src.iterdir():
            dst = tgt / item.name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            (shutil.copytree if item.is_dir() else shutil.copy2)(str(item), str(dst))

    db_name, db_user, db_pass = cfg["db_name"], cfg["db_user"], cfg["db_pass"]
    _push(job_id, f"Creating database `{db_name}`…")
    ok, err = _create_db(db_name, db_user, db_pass)
    if not ok:
        raise RuntimeError(f"DB creation failed: {err}")

    _push(job_id, "Writing Roundcube config…")
    config_dir = tgt / "config"
    config_dir.mkdir(exist_ok=True)
    sample = tgt / "config" / "config.inc.php.sample"
    cfg_text = sample.read_text() if sample.exists() else "<?php\n"
    des_key = _rand_str(24)
    rc_config = (
        f"<?php\n"
        f"$config['db_dsnw'] = 'mysql://{db_user}:{db_pass}@localhost/{db_name}';\n"
        f"$config['des_key'] = '{des_key}';\n"
        f"$config['default_host'] = 'localhost';\n"
        f"$config['smtp_server'] = 'localhost';\n"
        f"$config['smtp_port'] = 587;\n"
        f"$config['product_name'] = 'Webmail';\n"
        f"$config['plugins'] = ['archive', 'zipdownload'];\n"
    )
    (tgt / "config" / "config.inc.php").write_text(rc_config)

    # Init DB
    sql_file = tgt / "SQL" / "mysql.initial.sql"
    if sql_file.exists():
        _push(job_id, "Initialising Roundcube database schema…")
        cmd = ["mysql", "-uroot", db_name]
        if MYSQL_ROOT_PASS:
            cmd.insert(2, f"-p{MYSQL_ROOT_PASS}")
        with open(str(sql_file)) as f:
            subprocess.run(cmd, stdin=f, check=False, timeout=30)

    _set_permissions(tgt)
    _push(job_id, "Roundcube installed ✓")
    return {"url": f"https://{DOMAIN}/{ipath}/"}


def _install_snappymail(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["snappymail"]
    archive = _download_cached("snappymail", url, filename, job_id)
    ipath = cfg.get("install_path", "snappymail").strip("/") or "snappymail"
    tgt = _target_dir(ipath)

    _push(job_id, "Extracting SnappyMail…")
    subprocess.run(["tar", "-xzf", str(archive), "-C", str(tgt)], check=True, timeout=60)
    _set_permissions(tgt)
    _push(job_id, "SnappyMail installed ✓ — no database required")
    return {"url": f"https://{DOMAIN}/{ipath}/"}


def _install_phpmyadmin(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["phpmyadmin"]
    archive = _download_cached("phpmyadmin", url, filename, job_id)
    ipath = cfg.get("install_path", "phpmyadmin").strip("/") or "phpmyadmin"
    tgt = _target_dir(ipath)

    _push(job_id, "Extracting phpMyAdmin…")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["tar", "-xzf", str(archive), "-C", tmp], check=True, timeout=60)
        src = sorted(Path(tmp).iterdir())[0]
        for item in src.iterdir():
            dst = tgt / item.name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            (shutil.copytree if item.is_dir() else shutil.copy2)(str(item), str(dst))

    _push(job_id, "Writing phpMyAdmin config…")
    blowfish = _rand_str(32)
    pma_cfg = (
        "<?php\n"
        f"$cfg['blowfish_secret'] = '{blowfish}';\n"
        "$cfg['Servers'][1]['auth_type'] = 'cookie';\n"
        "$cfg['Servers'][1]['host'] = 'localhost';\n"
        "$cfg['Servers'][1]['compress'] = false;\n"
        "$cfg['Servers'][1]['AllowNoPassword'] = false;\n"
    )
    (tgt / "config.inc.php").write_text(pma_cfg)
    _set_permissions(tgt)
    _push(job_id, "phpMyAdmin installed ✓")
    return {"url": f"https://{DOMAIN}/{ipath}/"}


def _install_adminer(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["adminer"]
    _download_cached("adminer", url, filename, job_id)
    ipath = cfg.get("install_path", "adminer").strip("/") or "adminer"
    tgt = _target_dir(ipath)

    _push(job_id, "Installing Adminer (single PHP file)…")
    shutil.copy2(str(APP_CACHE_DIR / filename), str(tgt / "index.php"))
    _set_permissions(tgt)
    _push(job_id, "Adminer installed ✓")
    return {"url": f"https://{DOMAIN}/{ipath}/"}


def _install_ghost(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["ghost"]
    archive = _download_cached("ghost", url, filename, job_id)
    tgt = _target_dir(cfg.get("install_path", "/"))

    _push(job_id, "Extracting Ghost…")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["unzip", "-q", str(archive), "-d", tmp], check=True, timeout=120)
        src = Path(tmp)
        extracted = sorted(src.iterdir())
        if extracted and extracted[0].is_dir():
            src = extracted[0]
        for item in src.iterdir():
            dst = tgt / item.name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            (shutil.copytree if item.is_dir() else shutil.copy2)(str(item), str(dst))

    _push(job_id, "Running npm install --production for Ghost…")
    subprocess.run(["npm", "install", "--production"], cwd=str(tgt),
                   capture_output=True, timeout=300, check=False)

    _push(job_id, "Writing Ghost config…")
    ghost_config = {
        "url": f"https://{DOMAIN}",
        "server": {"port": 2368, "host": "0.0.0.0"},
        "database": {
            "client": "sqlite3",
            "connection": {"filename": "/var/customer/private/ghost.db"},
        },
        "mail": {"transport": "Direct"},
        "logging": {"transports": ["stdout"]},
        "process": "local",
        "paths": {"contentPath": str(tgt / "content")},
    }
    (tgt / "config.production.json").write_text(json.dumps(ghost_config, indent=2))

    _set_permissions(tgt)
    _push(job_id, "Ghost installed ✓ — start with: NODE_ENV=production node index.js (port 2368)")
    return {"url": f"https://{DOMAIN}", "note": "Runs on port 2368 — configure reverse proxy"}


def _install_october(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["october"]
    archive = _download_cached("october", url, filename, job_id)
    tgt = _target_dir(cfg.get("install_path", "/"))

    _push(job_id, "Extracting October CMS…")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["tar", "-xzf", str(archive), "-C", tmp], check=True, timeout=120)
        extracted = sorted(Path(tmp).iterdir())[0]
        for item in extracted.iterdir():
            dst = tgt / item.name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            (shutil.copytree if item.is_dir() else shutil.copy2)(str(item), str(dst))

    db_name, db_user, db_pass = cfg["db_name"], cfg["db_user"], cfg["db_pass"]
    _push(job_id, f"Creating database `{db_name}`…")
    ok, err = _create_db(db_name, db_user, db_pass)
    if not ok:
        raise RuntimeError(f"Database creation failed: {err}")

    import base64
    app_key = "base64:" + base64.b64encode(_rand_str(32).encode()).decode()
    env_content = (
        f"APP_NAME=OctoberCMS\n"
        f"APP_ENV=production\n"
        f"APP_KEY={app_key}\n"
        f"APP_DEBUG=false\n"
        f"APP_URL=https://{DOMAIN}\n"
        f"DB_CONNECTION=mysql\n"
        f"DB_HOST=127.0.0.1\n"
        f"DB_PORT=3306\n"
        f"DB_DATABASE={db_name}\n"
        f"DB_USERNAME={db_user}\n"
        f"DB_PASSWORD={db_pass}\n"
    )
    (tgt / ".env").write_text(env_content)

    _push(job_id, "Running October CMS install…")
    artisan = tgt / "artisan"
    if artisan.exists():
        subprocess.run(["php", str(artisan), "october:install", "--no-interaction"],
                       cwd=str(tgt), capture_output=True, timeout=120, check=False)

    _set_permissions(tgt)
    _push(job_id, "October CMS extracted ✓ — complete setup via browser wizard if needed")
    return {"url": f"https://{DOMAIN}", "admin_url": f"https://{DOMAIN}/backend/"}


def _install_concrete(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["concrete"]
    archive = _download_cached("concrete", url, filename, job_id)
    tgt = _target_dir(cfg.get("install_path", "/"))

    _push(job_id, "Extracting Concrete CMS…")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["unzip", "-q", str(archive), "-d", tmp], check=True, timeout=120)
        extracted = sorted(Path(tmp).iterdir())
        src = extracted[0] if extracted and extracted[0].is_dir() else Path(tmp)
        for item in src.iterdir():
            dst = tgt / item.name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            (shutil.copytree if item.is_dir() else shutil.copy2)(str(item), str(dst))

    db_name, db_user, db_pass = cfg["db_name"], cfg["db_user"], cfg["db_pass"]
    _push(job_id, f"Creating database `{db_name}`…")
    ok, err = _create_db(db_name, db_user, db_pass)
    if not ok:
        raise RuntimeError(f"Database creation failed: {err}")

    _set_permissions(tgt)
    _push(job_id, "Concrete CMS extracted ✓ — complete setup via browser install wizard")
    return {"url": f"https://{DOMAIN}/index.php/install"}


def _install_typo3(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["typo3"]
    archive = _download_cached("typo3", url, filename, job_id)
    tgt = _target_dir(cfg.get("install_path", "/"))

    _push(job_id, "Extracting TYPO3…")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["tar", "-xzf", str(archive), "-C", tmp], check=True, timeout=120)
        extracted = sorted(Path(tmp).iterdir())[0]
        for item in extracted.iterdir():
            dst = tgt / item.name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            (shutil.copytree if item.is_dir() else shutil.copy2)(str(item), str(dst))

    db_name, db_user, db_pass = cfg["db_name"], cfg["db_user"], cfg["db_pass"]
    _push(job_id, f"Creating database `{db_name}`…")
    ok, err = _create_db(db_name, db_user, db_pass)
    if not ok:
        raise RuntimeError(f"Database creation failed: {err}")

    # Create FIRST_INSTALL marker to trigger web-based setup wizard
    (tgt / "FIRST_INSTALL").touch()

    _set_permissions(tgt)
    _push(job_id, "TYPO3 extracted ✓ — visit the site URL to complete installation wizard")
    return {"url": f"https://{DOMAIN}", "admin_url": f"https://{DOMAIN}/typo3/"}


def _install_strapi(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["strapi"]
    archive = _download_cached("strapi", url, filename, job_id)
    tgt = _target_dir(cfg.get("install_path", "/"))

    _push(job_id, "Extracting Strapi package…")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["tar", "-xzf", str(archive), "-C", tmp], check=True, timeout=120)
        # npm tarballs extract to a `package/` subdirectory
        src = Path(tmp) / "package"
        if not src.exists():
            extracted = sorted(Path(tmp).iterdir())
            src = extracted[0] if extracted else Path(tmp)
        for item in src.iterdir():
            dst = tgt / item.name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            (shutil.copytree if item.is_dir() else shutil.copy2)(str(item), str(dst))

    db_name, db_user, db_pass = cfg["db_name"], cfg["db_user"], cfg["db_pass"]
    _push(job_id, f"Creating database `{db_name}`…")
    ok, err = _create_db(db_name, db_user, db_pass)
    if not ok:
        raise RuntimeError(f"Database creation failed: {err}")

    import base64
    keys = ",".join(base64.b64encode(_rand_str(16).encode()).decode() for _ in range(4))
    env_content = (
        f"HOST=0.0.0.0\n"
        f"PORT=1337\n"
        f"APP_KEYS={keys}\n"
        f"API_TOKEN_SALT={_rand_str(32)}\n"
        f"ADMIN_JWT_SECRET={_rand_str(32)}\n"
        f"JWT_SECRET={_rand_str(32)}\n"
        f"DATABASE_CLIENT=mysql\n"
        f"DATABASE_HOST=127.0.0.1\n"
        f"DATABASE_PORT=3306\n"
        f"DATABASE_NAME={db_name}\n"
        f"DATABASE_USERNAME={db_user}\n"
        f"DATABASE_PASSWORD={db_pass}\n"
        f"NODE_ENV=production\n"
    )
    (tgt / ".env").write_text(env_content)

    _push(job_id, "Running npm install for Strapi…")
    subprocess.run(["npm", "install"], cwd=str(tgt),
                   capture_output=True, timeout=300, check=False)

    _set_permissions(tgt)
    _push(job_id, "Strapi installed ✓ — start with: npm run start (port 1337)")
    return {"url": f"https://{DOMAIN}", "admin_url": f"https://{DOMAIN}/admin/",
            "note": "Runs on port 1337 — configure reverse proxy"}


def _install_matomo(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["matomo"]
    archive = _download_cached("matomo", url, filename, job_id)
    ipath = cfg.get("install_path", "matomo").strip("/") or "matomo"
    tgt = _target_dir(ipath)

    _push(job_id, "Extracting Matomo…")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["unzip", "-q", str(archive), "-d", tmp], check=True, timeout=120)
        src = Path(tmp) / "matomo"
        if not src.exists():
            extracted = sorted(Path(tmp).iterdir())
            src = extracted[0] if extracted and extracted[0].is_dir() else Path(tmp)
        for item in src.iterdir():
            dst = tgt / item.name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            (shutil.copytree if item.is_dir() else shutil.copy2)(str(item), str(dst))

    db_name, db_user, db_pass = cfg["db_name"], cfg["db_user"], cfg["db_pass"]
    _push(job_id, f"Creating database `{db_name}`…")
    ok, err = _create_db(db_name, db_user, db_pass)
    if not ok:
        raise RuntimeError(f"Database creation failed: {err}")

    _set_permissions(tgt)
    _push(job_id, "Matomo extracted ✓ — complete setup via browser install wizard")
    return {"url": f"https://{DOMAIN}/{ipath}/index.php"}


def _install_umami(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["umami"]
    archive = _download_cached("umami", url, filename, job_id)
    tgt = _target_dir(cfg.get("install_path", "/"))

    _push(job_id, "Extracting Umami…")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["tar", "-xzf", str(archive), "-C", tmp], check=True, timeout=120)
        extracted = sorted(Path(tmp).iterdir())[0]
        for item in extracted.iterdir():
            dst = tgt / item.name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            (shutil.copytree if item.is_dir() else shutil.copy2)(str(item), str(dst))

    db_name, db_user, db_pass = cfg["db_name"], cfg["db_user"], cfg["db_pass"]
    _push(job_id, f"Creating database `{db_name}`…")
    ok, err = _create_db(db_name, db_user, db_pass)
    if not ok:
        raise RuntimeError(f"Database creation failed: {err}")

    env_content = (
        f"DATABASE_URL=mysql://{db_user}:{db_pass}@localhost:3306/{db_name}\n"
        f"APP_SECRET={_rand_str(32)}\n"
    )
    (tgt / ".env").write_text(env_content)

    _push(job_id, "Running npm install && npm run build for Umami…")
    subprocess.run(["npm", "install"], cwd=str(tgt), capture_output=True, timeout=300, check=False)
    subprocess.run(["npm", "run", "build"], cwd=str(tgt), capture_output=True, timeout=300, check=False)

    _set_permissions(tgt)
    _push(job_id, "Umami installed ✓ — start with: npm run start (port 3000)")
    return {"url": f"https://{DOMAIN}", "note": "Runs on port 3000 — configure reverse proxy"}


def _install_freshrss(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["freshrss"]
    archive = _download_cached("freshrss", url, filename, job_id)
    ipath = cfg.get("install_path", "freshrss").strip("/") or "freshrss"
    tgt = _target_dir(ipath)

    _push(job_id, "Extracting FreshRSS…")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["tar", "-xzf", str(archive), "-C", tmp], check=True, timeout=120)
        extracted = sorted(Path(tmp).iterdir())[0]
        for item in extracted.iterdir():
            dst = tgt / item.name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            (shutil.copytree if item.is_dir() else shutil.copy2)(str(item), str(dst))

    db_name, db_user, db_pass = cfg["db_name"], cfg["db_user"], cfg["db_pass"]
    _push(job_id, f"Creating database `{db_name}`…")
    ok, err = _create_db(db_name, db_user, db_pass)
    if not ok:
        raise RuntimeError(f"Database creation failed: {err}")

    data_dir = tgt / "data"
    data_dir.mkdir(exist_ok=True)
    _set_permissions(tgt)
    subprocess.run(["chmod", "-R", "777", str(data_dir)], check=False, timeout=30)
    _push(job_id, "FreshRSS extracted ✓ — complete setup via browser installer")
    return {"url": f"https://{DOMAIN}/{ipath}/"}


def _install_nextcloud(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["nextcloud"]
    archive = _download_cached("nextcloud", url, filename, job_id)
    tgt = _target_dir(cfg.get("install_path", "/"))

    _push(job_id, "Extracting Nextcloud (this may take a while)…")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["tar", "-xjf", str(archive), "-C", tmp], check=True, timeout=300)
        src = Path(tmp) / "nextcloud"
        if not src.exists():
            src = sorted(Path(tmp).iterdir())[0]
        for item in src.iterdir():
            dst = tgt / item.name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            (shutil.copytree if item.is_dir() else shutil.copy2)(str(item), str(dst))

    db_name, db_user, db_pass = cfg["db_name"], cfg["db_user"], cfg["db_pass"]
    _push(job_id, f"Creating database `{db_name}`…")
    ok, err = _create_db(db_name, db_user, db_pass)
    if not ok:
        raise RuntimeError(f"Database creation failed: {err}")

    _set_permissions(tgt)
    _push(job_id, "Nextcloud extracted ✓ — complete setup via browser install wizard")
    return {"url": f"https://{DOMAIN}", "admin_url": f"https://{DOMAIN}/index.php/login"}


def _install_bookstack(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["bookstack"]
    archive = _download_cached("bookstack", url, filename, job_id)
    tgt = _target_dir(cfg.get("install_path", "/"))

    _push(job_id, "Extracting BookStack…")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["tar", "-xzf", str(archive), "-C", tmp], check=True, timeout=120)
        extracted = sorted(Path(tmp).iterdir())[0]
        for item in extracted.iterdir():
            dst = tgt / item.name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            (shutil.copytree if item.is_dir() else shutil.copy2)(str(item), str(dst))

    db_name, db_user, db_pass = cfg["db_name"], cfg["db_user"], cfg["db_pass"]
    _push(job_id, f"Creating database `{db_name}`…")
    ok, err = _create_db(db_name, db_user, db_pass)
    if not ok:
        raise RuntimeError(f"Database creation failed: {err}")

    import base64
    app_key = "base64:" + base64.b64encode(_rand_str(32).encode()).decode()
    env_content = (
        f"APP_KEY={app_key}\n"
        f"APP_URL=https://{DOMAIN}\n"
        f"APP_LANG=en\n"
        f"DB_HOST=localhost\n"
        f"DB_DATABASE={db_name}\n"
        f"DB_USERNAME={db_user}\n"
        f"DB_PASSWORD={db_pass}\n"
        f"MAIL_DRIVER=smtp\n"
        f"MAIL_FROM=bookstack@{DOMAIN}\n"
    )
    (tgt / ".env").write_text(env_content)

    _push(job_id, "Running composer install for BookStack…")
    if shutil.which("composer"):
        subprocess.run(["composer", "install", "--no-dev", "--no-interaction"],
                       cwd=str(tgt), capture_output=True, timeout=300, check=False)

    _push(job_id, "Running database migrations…")
    artisan = tgt / "artisan"
    if artisan.exists():
        subprocess.run(["php", str(artisan), "migrate", "--force"],
                       cwd=str(tgt), capture_output=True, timeout=120, check=False)

    _set_permissions(tgt)
    _push(job_id, "BookStack installed ✓ — default login: admin@admin.com / password")
    return {"url": f"https://{DOMAIN}"}


def _install_wikijs(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["wikijs"]
    archive = _download_cached("wikijs", url, filename, job_id)
    tgt = _target_dir(cfg.get("install_path", "/"))

    _push(job_id, "Extracting Wiki.js…")
    subprocess.run(["tar", "-xzf", str(archive), "-C", str(tgt)], check=True, timeout=120)

    db_name, db_user, db_pass = cfg["db_name"], cfg["db_user"], cfg["db_pass"]
    _push(job_id, f"Creating database `{db_name}`…")
    ok, err = _create_db(db_name, db_user, db_pass)
    if not ok:
        raise RuntimeError(f"Database creation failed: {err}")

    config_yaml = (
        f"bindIP: 0.0.0.0\n"
        f"port: 3000\n"
        f"db:\n"
        f"  type: mysql\n"
        f"  host: localhost\n"
        f"  port: 3306\n"
        f"  user: {db_user}\n"
        f"  pass: {db_pass}\n"
        f"  db: {db_name}\n"
        f"ssl: false\n"
    )
    (tgt / "config.yml").write_text(config_yaml)

    _set_permissions(tgt)
    _push(job_id, "Wiki.js installed ✓ — start with: node server (port 3000)")
    return {"url": f"https://{DOMAIN}", "note": "Runs on port 3000 — configure reverse proxy"}


def _install_gitea(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["gitea"]
    archive = _download_cached("gitea", url, filename, job_id)
    tgt = _target_dir(cfg.get("install_path", "/"))

    _push(job_id, "Installing Gitea binary…")
    gitea_bin = tgt / "gitea"
    shutil.copy2(str(archive), str(gitea_bin))
    gitea_bin.chmod(0o755)

    data_dir = Path("/var/customer/private/gitea")
    data_dir.mkdir(parents=True, exist_ok=True)
    conf_dir = data_dir / "conf"
    conf_dir.mkdir(exist_ok=True)

    app_ini = (
        f"[DEFAULT]\n"
        f"RUN_USER = www-data\n\n"
        f"[server]\n"
        f"HTTP_ADDR = 0.0.0.0\n"
        f"HTTP_PORT = 3000\n"
        f"ROOT_URL  = https://{DOMAIN}/\n\n"
        f"[database]\n"
        f"DB_TYPE  = sqlite3\n"
        f"PATH     = {data_dir}/gitea.db\n\n"
        f"[repository]\n"
        f"ROOT = {data_dir}/repositories\n\n"
        f"[security]\n"
        f"SECRET_KEY     = {_rand_str(40)}\n"
        f"INTERNAL_TOKEN = {_rand_str(40)}\n"
    )
    (conf_dir / "app.ini").write_text(app_ini)

    _set_permissions(tgt)
    subprocess.run(["chown", "-R", "www-data:www-data", str(data_dir)], check=False, timeout=30)
    _push(job_id, "Gitea installed ✓ — start with: ./gitea web --config /var/customer/private/gitea/conf/app.ini (port 3000)")
    return {"url": f"https://{DOMAIN}", "note": "Runs on port 3000 — configure reverse proxy"}


def _install_codeserver(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["codeserver"]
    archive = _download_cached("codeserver", url, filename, job_id)

    _push(job_id, "Extracting code-server…")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["tar", "-xzf", str(archive), "-C", tmp], check=True, timeout=300)
        extracted = sorted(Path(tmp).iterdir())[0]  # code-server-4.x.y-linux-amd64/
        bin_src = extracted / "bin" / "code-server"
        if bin_src.exists():
            dest_bin = Path("/usr/local/bin/code-server")
            shutil.copy2(str(bin_src), str(dest_bin))
            dest_bin.chmod(0o755)
            _push(job_id, "code-server binary installed to /usr/local/bin/code-server")
        else:
            raise RuntimeError("code-server binary not found in archive")

    admin_pass = cfg.get("admin_pass", _rand_str(16))
    start_script = (
        f"#!/usr/bin/env bash\n"
        f"export PASSWORD='{admin_pass}'\n"
        f"exec /usr/local/bin/code-server --bind-addr 0.0.0.0:8080 --auth password /var/www/html\n"
    )
    script_path = Path("/var/customer/private/code-server.sh")
    script_path.write_text(start_script)
    script_path.chmod(0o700)

    _push(job_id, "code-server installed ✓ — run /var/customer/private/code-server.sh to start (port 8080)")
    return {"url": f"https://{DOMAIN}",
            "note": "Runs on port 8080 — configure reverse proxy. Start: /var/customer/private/code-server.sh"}


def _install_n8n(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["n8n"]
    archive = _download_cached("n8n", url, filename, job_id)
    tgt = _target_dir(cfg.get("install_path", "/"))

    _push(job_id, "Extracting n8n…")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["tar", "-xzf", str(archive), "-C", tmp], check=True, timeout=120)
        src = Path(tmp) / "package"
        if not src.exists():
            extracted = sorted(Path(tmp).iterdir())
            src = extracted[0] if extracted else Path(tmp)
        for item in src.iterdir():
            dst = tgt / item.name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            (shutil.copytree if item.is_dir() else shutil.copy2)(str(item), str(dst))

    admin_user = cfg.get("admin_user", "admin")
    admin_pass = cfg.get("admin_pass", _rand_str(16))
    env_content = (
        f"N8N_BASIC_AUTH_ACTIVE=true\n"
        f"N8N_BASIC_AUTH_USER={admin_user}\n"
        f"N8N_BASIC_AUTH_PASSWORD={admin_pass}\n"
        f"DB_TYPE=sqlite\n"
        f"DB_SQLITE_VACUUM_ON_STARTUP=true\n"
        f"N8N_PORT=5678\n"
        f"N8N_PROTOCOL=https\n"
        f"N8N_HOST={DOMAIN}\n"
        f"WEBHOOK_URL=https://{DOMAIN}/\n"
    )
    (tgt / ".env").write_text(env_content)

    if shutil.which("node"):
        _push(job_id, "Running npm install for n8n…")
        subprocess.run(["npm", "install"], cwd=str(tgt),
                       capture_output=True, timeout=300, check=False)

    _set_permissions(tgt)
    _push(job_id, "n8n installed ✓ — start with: node node_modules/n8n/bin/n8n start (port 5678)")
    return {"url": f"https://{DOMAIN}", "note": "Runs on port 5678 — configure reverse proxy"}


def _install_nodered(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["nodered"]
    archive = _download_cached("nodered", url, filename, job_id)
    tgt = _target_dir(cfg.get("install_path", "/"))

    _push(job_id, "Extracting Node-RED…")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["tar", "-xzf", str(archive), "-C", tmp], check=True, timeout=120)
        src = Path(tmp) / "package"
        if not src.exists():
            extracted = sorted(Path(tmp).iterdir())
            src = extracted[0] if extracted else Path(tmp)
        for item in src.iterdir():
            dst = tgt / item.name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            (shutil.copytree if item.is_dir() else shutil.copy2)(str(item), str(dst))

    _push(job_id, "Running npm install for Node-RED…")
    subprocess.run(["npm", "install"], cwd=str(tgt),
                   capture_output=True, timeout=300, check=False)

    admin_user = cfg.get("admin_user", "admin")
    admin_pass = cfg.get("admin_pass", _rand_str(16))
    # Use a sha256 hash for the Node-RED credentials (bcrypt preferred but may not be available)
    import hashlib
    pass_hash = hashlib.sha256(admin_pass.encode()).hexdigest()
    settings_js = (
        f"module.exports = {{\n"
        f"    uiPort: 1880,\n"
        f"    httpAdminRoot: '/admin',\n"
        f"    httpNodeRoot: '/',\n"
        f"    userDir: '/var/customer/private/nodered/',\n"
        f"    adminAuth: {{\n"
        f"        type: 'credentials',\n"
        f"        users: [{{\n"
        f"            username: '{admin_user}',\n"
        f"            password: '{pass_hash}',\n"
        f"            permissions: '*'\n"
        f"        }}]\n"
        f"    }},\n"
        f"    logging: {{ console: {{ level: 'info', metrics: false, audit: false }} }}\n"
        f"}};\n"
    )
    Path("/var/customer/private/nodered").mkdir(parents=True, exist_ok=True)
    (tgt / "settings.js").write_text(settings_js)

    _set_permissions(tgt)
    _push(job_id, "Node-RED installed ✓ — start with: node red.js (port 1880)")
    return {"url": f"https://{DOMAIN}", "note": "Runs on port 1880 — configure reverse proxy"}


def _install_filebrowser(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["filebrowser"]
    archive = _download_cached("filebrowser", url, filename, job_id)

    _push(job_id, "Extracting File Browser binary…")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["tar", "-xzf", str(archive), "-C", tmp], check=True, timeout=60)
        bin_candidates = list(Path(tmp).glob("**/filebrowser"))
        if not bin_candidates:
            # Some releases use different name
            bin_candidates = [p for p in Path(tmp).iterdir() if p.is_file() and p.stat().st_mode & 0o111]
        if bin_candidates:
            dest_bin = Path("/usr/local/bin/filebrowser")
            shutil.copy2(str(bin_candidates[0]), str(dest_bin))
            dest_bin.chmod(0o755)
            _push(job_id, "filebrowser binary installed to /usr/local/bin/filebrowser")
        else:
            raise RuntimeError("filebrowser binary not found in archive")

    admin_user = cfg.get("admin_user", "admin")
    admin_pass = cfg.get("admin_pass", _rand_str(16))
    fb_config = {
        "port": 8080,
        "baseURL": "",
        "address": "0.0.0.0",
        "log": "stdout",
        "database": "/var/customer/private/filebrowser.db",
        "root": str(PUBLIC_ROOT),
    }
    config_path = Path("/var/customer/private/.filebrowser.json")
    config_path.write_text(json.dumps(fb_config, indent=2))

    _push(job_id, "File Browser installed ✓ — start: filebrowser -c /var/customer/private/.filebrowser.json (port 8080)")
    return {"url": f"https://{DOMAIN}",
            "note": f"Runs on port 8080. First run: filebrowser users add {admin_user} {admin_pass} --perm.admin"}


def _install_uptime(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["uptime"]
    archive = _download_cached("uptime", url, filename, job_id)
    tgt = _target_dir(cfg.get("install_path", "/"))

    _push(job_id, "Extracting Uptime Kuma…")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["tar", "-xzf", str(archive), "-C", tmp], check=True, timeout=120)
        extracted = sorted(Path(tmp).iterdir())[0]  # uptime-kuma-1.x.y/
        for item in extracted.iterdir():
            dst = tgt / item.name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            (shutil.copytree if item.is_dir() else shutil.copy2)(str(item), str(dst))

    _push(job_id, "Running npm install --production for Uptime Kuma…")
    subprocess.run(["npm", "install", "--production"], cwd=str(tgt),
                   capture_output=True, timeout=300, check=False)

    _set_permissions(tgt)
    _push(job_id, "Uptime Kuma installed ✓ — start with: node server/server.js (port 3001)")
    return {"url": f"https://{DOMAIN}", "note": "Runs on port 3001 — configure reverse proxy"}


def _install_vaultwarden(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["vaultwarden"]
    archive = _download_cached("vaultwarden", url, filename, job_id)

    _push(job_id, "Extracting Vaultwarden binary…")
    data_dir = Path("/var/customer/private/vaultwarden")
    data_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["tar", "-xzf", str(archive), "-C", tmp], check=True, timeout=60)
        bin_candidates = list(Path(tmp).glob("**/vaultwarden"))
        if not bin_candidates:
            bin_candidates = [p for p in Path(tmp).iterdir() if p.is_file() and p.stat().st_mode & 0o111]
        if bin_candidates:
            dest_bin = Path("/usr/local/bin/vaultwarden")
            shutil.copy2(str(bin_candidates[0]), str(dest_bin))
            dest_bin.chmod(0o755)
            _push(job_id, "vaultwarden binary installed to /usr/local/bin/vaultwarden")
        else:
            raise RuntimeError("vaultwarden binary not found in archive")

    admin_token = _rand_str(40)
    env_content = (
        f"DATA_FOLDER={data_dir}\n"
        f"DATABASE_URL={data_dir}/db.sqlite3\n"
        f"ROCKET_ADDRESS=0.0.0.0\n"
        f"ROCKET_PORT=8000\n"
        f"DOMAIN=https://{DOMAIN}\n"
        f"ADMIN_TOKEN={admin_token}\n"
        f"SIGNUPS_ALLOWED=true\n"
        f"INVITATIONS_ALLOWED=true\n"
    )
    env_file = data_dir / ".env"
    env_file.write_text(env_content)

    subprocess.run(["chown", "-R", "www-data:www-data", str(data_dir)], check=False, timeout=30)
    _push(job_id, f"Vaultwarden installed ✓ — start: vaultwarden (port 8000). Admin token: {admin_token}")
    return {"url": f"https://{DOMAIN}", "admin_url": f"https://{DOMAIN}/admin/",
            "admin_token": admin_token,
            "note": f"Runs on port 8000 — configure reverse proxy. SAVE admin token: {admin_token}"}


def _install_invoiceninja(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["invoiceninja"]
    archive = _download_cached("invoiceninja", url, filename, job_id)
    tgt = _target_dir(cfg.get("install_path", "/"))

    _push(job_id, "Extracting Invoice Ninja…")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["unzip", "-q", str(archive), "-d", tmp], check=True, timeout=120)
        extracted = sorted(Path(tmp).iterdir())
        src = extracted[0] if extracted and extracted[0].is_dir() else Path(tmp)
        for item in src.iterdir():
            dst = tgt / item.name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            (shutil.copytree if item.is_dir() else shutil.copy2)(str(item), str(dst))

    db_name, db_user, db_pass = cfg["db_name"], cfg["db_user"], cfg["db_pass"]
    _push(job_id, f"Creating database `{db_name}`…")
    ok, err = _create_db(db_name, db_user, db_pass)
    if not ok:
        raise RuntimeError(f"Database creation failed: {err}")

    import base64
    app_key = "base64:" + base64.b64encode(_rand_str(32).encode()).decode()
    env_content = (
        f"APP_NAME='Invoice Ninja'\n"
        f"APP_ENV=production\n"
        f"APP_KEY={app_key}\n"
        f"APP_DEBUG=false\n"
        f"APP_URL=https://{DOMAIN}\n"
        f"DB_HOST=localhost\n"
        f"DB_DATABASE={db_name}\n"
        f"DB_USERNAME={db_user}\n"
        f"DB_PASSWORD={db_pass}\n"
        f"REQUIRE_HTTPS=true\n"
    )
    (tgt / ".env").write_text(env_content)

    _push(job_id, "Running artisan key:generate & migrations…")
    artisan = tgt / "artisan"
    if artisan.exists():
        subprocess.run(["php", str(artisan), "key:generate", "--force"],
                       cwd=str(tgt), capture_output=True, timeout=60, check=False)
        subprocess.run(["php", str(artisan), "migrate", "--force"],
                       cwd=str(tgt), capture_output=True, timeout=120, check=False)
        subprocess.run(["php", str(artisan), "storage:link"],
                       cwd=str(tgt), capture_output=True, timeout=30, check=False)

    _set_permissions(tgt)
    _push(job_id, "Invoice Ninja installed ✓ — visit the site URL to complete setup")
    return {"url": f"https://{DOMAIN}", "admin_url": f"https://{DOMAIN}/setup"}


def _install_prestashop(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["prestashop"]
    archive = _download_cached("prestashop", url, filename, job_id)
    tgt = _target_dir(cfg.get("install_path", "/"))
    _push(job_id, "Extracting PrestaShop…")
    subprocess.run(["unzip", "-q", str(archive), "-d", str(tgt)], check=True, timeout=120)
    db_name, db_user, db_pass = cfg["db_name"], cfg["db_user"], cfg["db_pass"]
    _push(job_id, f"Creating database `{db_name}`…")
    ok, err = _create_db(db_name, db_user, db_pass)
    if not ok:
        raise RuntimeError(f"DB creation failed: {err}")
    _set_permissions(tgt)
    _push(job_id, "PrestaShop extracted ✓ — complete the web installer to finish setup")
    return {"url": f"https://{DOMAIN}", "admin_url": f"https://{DOMAIN}/admin/", "note": "Delete the /install directory after setup is complete."}


def _install_opencart(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["opencart"]
    archive = _download_cached("opencart", url, filename, job_id)
    tgt = _target_dir(cfg.get("install_path", "/"))
    _push(job_id, "Extracting OpenCart…")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["tar", "-xzf", str(archive), "-C", tmp], check=True, timeout=60)
        upload_dir = Path(tmp) / "upload"
        src = upload_dir if upload_dir.exists() else Path(tmp) / sorted(Path(tmp).iterdir())[0]
        for item in src.iterdir():
            dst = tgt / item.name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            (shutil.copytree if item.is_dir() else shutil.copy2)(str(item), str(dst))
    db_name, db_user, db_pass = cfg["db_name"], cfg["db_user"], cfg["db_pass"]
    _push(job_id, f"Creating database `{db_name}`…")
    ok, err = _create_db(db_name, db_user, db_pass)
    if not ok:
        raise RuntimeError(f"DB creation failed: {err}")
    _set_permissions(tgt)
    _push(job_id, "OpenCart extracted ✓ — visit install/ directory to complete setup")
    return {"url": f"https://{DOMAIN}", "admin_url": f"https://{DOMAIN}/admin/"}


def _install_woocommerce(cfg: dict, job_id: str) -> dict:
    """Install WordPress + WooCommerce plugin."""
    # First install WordPress
    _push(job_id, "Installing WordPress as WooCommerce base…")
    result = _install_wordpress(cfg, job_id)
    tgt = _target_dir(cfg.get("install_path", "/"))
    # Download and install WooCommerce plugin
    _push(job_id, "Downloading WooCommerce plugin…")
    woo_url = "https://downloads.wordpress.org/plugin/woocommerce.8.7.0.zip"
    woo_archive = _download_cached("woocommerce-plugin", woo_url, "woocommerce-plugin.zip", job_id)
    plugins_dir = tgt / "wp-content" / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["unzip", "-q", str(woo_archive), "-d", str(plugins_dir)], check=True, timeout=60)
    _push(job_id, "WooCommerce plugin installed ✓ — activate it in WordPress admin")
    result["note"] = "Go to Plugins in WordPress admin and activate WooCommerce to complete setup."
    return result


def _install_piwigo(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["piwigo"]
    archive = _download_cached("piwigo", url, filename, job_id)
    tgt = _target_dir(cfg.get("install_path", "/"))
    _push(job_id, "Extracting Piwigo…")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["unzip", "-q", str(archive), "-d", tmp], check=True, timeout=60)
        src_candidates = [d for d in Path(tmp).iterdir() if d.is_dir()]
        src = src_candidates[0] if src_candidates else Path(tmp)
        for item in src.iterdir():
            dst = tgt / item.name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            (shutil.copytree if item.is_dir() else shutil.copy2)(str(item), str(dst))
    db_name, db_user, db_pass = cfg["db_name"], cfg["db_user"], cfg["db_pass"]
    _push(job_id, f"Creating database `{db_name}`…")
    ok, err = _create_db(db_name, db_user, db_pass)
    if not ok:
        raise RuntimeError(f"DB creation failed: {err}")
    _set_permissions(tgt)
    _push(job_id, "Piwigo extracted ✓ — complete setup via web installer")
    return {"url": f"https://{DOMAIN}", "admin_url": f"https://{DOMAIN}/admin/"}


def _install_lychee(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["lychee"]
    archive = _download_cached("lychee", url, filename, job_id)
    tgt = _target_dir(cfg.get("install_path", "/"))
    _push(job_id, "Extracting Lychee…")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["unzip", "-q", str(archive), "-d", tmp], check=True, timeout=60)
        src_candidates = [d for d in Path(tmp).iterdir() if d.is_dir()]
        src = src_candidates[0] if src_candidates else Path(tmp)
        for item in src.iterdir():
            dst = tgt / item.name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            (shutil.copytree if item.is_dir() else shutil.copy2)(str(item), str(dst))
    db_name, db_user, db_pass = cfg["db_name"], cfg["db_user"], cfg["db_pass"]
    _push(job_id, f"Creating database `{db_name}`…")
    ok, err = _create_db(db_name, db_user, db_pass)
    if not ok:
        raise RuntimeError(f"DB creation failed: {err}")
    _push(job_id, "Writing .env…")
    env_content = (
        f"APP_ENV=production\nAPP_KEY=base64:{_rand_str(32)}\nAPP_DEBUG=false\n"
        f"APP_URL=https://{DOMAIN}\nDB_CONNECTION=mysql\nDB_HOST=127.0.0.1\n"
        f"DB_PORT=3306\nDB_DATABASE={db_name}\nDB_USERNAME={db_user}\nDB_PASSWORD={db_pass}\n"
    )
    (tgt / ".env").write_text(env_content)
    _set_permissions(tgt)
    _push(job_id, "Lychee installed ✓")
    return {"url": f"https://{DOMAIN}"}


def _install_jellyfin(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["jellyfin"]
    archive = _download_cached("jellyfin", url, filename, job_id)
    _push(job_id, "Extracting Jellyfin binary…")
    data_dir = Path("/var/customer/private/jellyfin")
    data_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["tar", "-xzf", str(archive), "-C", tmp], check=True, timeout=60)
        extracted = sorted(Path(tmp).iterdir())[0]
        for item in extracted.iterdir():
            dst = data_dir / item.name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            (shutil.copytree if item.is_dir() else shutil.copy2)(str(item), str(dst))
    jellyfin_bin = data_dir / "jellyfin"
    if jellyfin_bin.exists():
        jellyfin_bin.chmod(0o755)
    _push(job_id, "Jellyfin installed ✓ — runs on port 8096")
    return {"url": f"https://{DOMAIN}:8096", "note": "Start with: /var/customer/private/jellyfin/jellyfin"}


def _install_moodle(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["moodle"]
    archive = _download_cached("moodle", url, filename, job_id)
    tgt = _target_dir(cfg.get("install_path", "/"))
    _push(job_id, "Extracting Moodle…")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["tar", "-xzf", str(archive), "-C", tmp], check=True, timeout=120)
        src_candidates = [d for d in Path(tmp).iterdir() if d.is_dir()]
        src = src_candidates[0] if src_candidates else Path(tmp)
        for item in src.iterdir():
            dst = tgt / item.name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            (shutil.copytree if item.is_dir() else shutil.copy2)(str(item), str(dst))
    db_name, db_user, db_pass = cfg["db_name"], cfg["db_user"], cfg["db_pass"]
    _push(job_id, f"Creating database `{db_name}`…")
    ok, err = _create_db(db_name, db_user, db_pass)
    if not ok:
        raise RuntimeError(f"DB creation failed: {err}")
    moodle_data = Path("/var/customer/private/moodledata")
    moodle_data.mkdir(parents=True, exist_ok=True)
    _set_permissions(tgt)
    subprocess.run(["chown", "-R", "www-data:www-data", str(moodle_data)], timeout=10, check=False)
    _push(job_id, "Moodle extracted ✓ — visit the site to complete the installer")
    return {"url": f"https://{DOMAIN}"}


def _install_monica(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["monica"]
    archive = _download_cached("monica", url, filename, job_id)
    tgt = _target_dir(cfg.get("install_path", "/"))
    _push(job_id, "Extracting Monica…")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["tar", "-xzf", str(archive), "-C", tmp], check=True, timeout=60)
        src = sorted(Path(tmp).iterdir())[0]
        for item in src.iterdir():
            dst = tgt / item.name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            (shutil.copytree if item.is_dir() else shutil.copy2)(str(item), str(dst))
    db_name, db_user, db_pass = cfg["db_name"], cfg["db_user"], cfg["db_pass"]
    _push(job_id, f"Creating database `{db_name}`…")
    ok, err = _create_db(db_name, db_user, db_pass)
    if not ok:
        raise RuntimeError(f"DB creation failed: {err}")
    _push(job_id, "Writing .env…")
    env_content = (
        f"APP_ENV=production\nAPP_KEY=base64:{_rand_str(32)}\nAPP_DEBUG=false\n"
        f"APP_URL=https://{DOMAIN}\nDB_CONNECTION=mysql\nDB_HOST=127.0.0.1\n"
        f"DB_PORT=3306\nDB_DATABASE={db_name}\nDB_USERNAME={db_user}\nDB_PASSWORD={db_pass}\n"
        f"MAIL_MAILER=smtp\nMAIL_HOST=localhost\nMAIL_PORT=587\n"
        f"HASH_ROUNDS=14\n"
    )
    (tgt / ".env").write_text(env_content)
    _set_permissions(tgt)
    _push(job_id, "Running Monica migrations…")
    php = shutil.which("php")
    if php:
        subprocess.run([php, str(tgt / "artisan"), "migrate", "--force"], cwd=str(tgt), timeout=120, check=False)
        subprocess.run([php, str(tgt / "artisan"), "storage:link"], cwd=str(tgt), timeout=30, check=False)
    return {"url": f"https://{DOMAIN}"}


def _install_yourls(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["yourls"]
    archive = _download_cached("yourls", url, filename, job_id)
    tgt = _target_dir(cfg.get("install_path", "/"))
    _push(job_id, "Extracting YOURLS…")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["unzip", "-q", str(archive), "-d", tmp], check=True, timeout=60)
        src = sorted(Path(tmp).iterdir())[0]
        for item in src.iterdir():
            dst = tgt / item.name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            (shutil.copytree if item.is_dir() else shutil.copy2)(str(item), str(dst))
    db_name, db_user, db_pass = cfg["db_name"], cfg["db_user"], cfg["db_pass"]
    _push(job_id, f"Creating database `{db_name}`…")
    ok, err = _create_db(db_name, db_user, db_pass)
    if not ok:
        raise RuntimeError(f"DB creation failed: {err}")
    cfg_sample = tgt / "user" / "config-sample.php"
    cfg_dest   = tgt / "user" / "config.php"
    if cfg_sample.exists():
        content = cfg_sample.read_text()
        for old, new in [
            ("'YOURLS_DB_USER', 'your db user name'", f"'YOURLS_DB_USER', '{db_user}'"),
            ("'YOURLS_DB_PASS', 'your db password'",  f"'YOURLS_DB_PASS', '{db_pass}'"),
            ("'YOURLS_DB_NAME', 'yourls'",             f"'YOURLS_DB_NAME', '{db_name}'"),
            ("'YOURLS_SITE', 'http://your-own-domain-here.com'", f"'YOURLS_SITE', 'https://{DOMAIN}'"),
            ("'YOURLS_USER', 'username'",              f"'YOURLS_USER', '{cfg.get('admin_user','admin')}'"),
            ("'YOURLS_PASS', 'password'",              f"'YOURLS_PASS', '{cfg.get('admin_pass',_rand_str(16))}'"),
        ]:
            content = content.replace(old, new)
        cfg_dest.write_text(content)
    _set_permissions(tgt)
    _push(job_id, "YOURLS configured ✓ — visit /admin/ to complete install")
    return {"url": f"https://{DOMAIN}", "admin_url": f"https://{DOMAIN}/admin/"}


def _install_grafana(cfg: dict, job_id: str) -> dict:
    url, filename = APP_DOWNLOADS["grafana"]
    archive = _download_cached("grafana", url, filename, job_id)
    data_dir = Path("/var/customer/private/grafana")
    data_dir.mkdir(parents=True, exist_ok=True)
    _push(job_id, "Extracting Grafana…")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["tar", "-xzf", str(archive), "-C", tmp], check=True, timeout=60)
        src = sorted(Path(tmp).iterdir())[0]
        for item in src.iterdir():
            dst = data_dir / item.name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            (shutil.copytree if item.is_dir() else shutil.copy2)(str(item), str(dst))
    grafana_bin = data_dir / "bin" / "grafana"
    if grafana_bin.exists():
        grafana_bin.chmod(0o755)
    _push(job_id, "Grafana installed ✓ — runs on port 3000")
    return {"url": f"http://{DOMAIN}:3000", "note": "Start with: /var/customer/private/grafana/bin/grafana server --homepath /var/customer/private/grafana"}


def _install_netdata(cfg: dict, job_id: str) -> dict:
    _push(job_id, "Installing Netdata via kickstart script…")
    r = subprocess.run(
        ["bash", "-c", "curl -Ss https://get.netdata.cloud/kickstart.sh | bash /dev/stdin --non-interactive --dont-start-it --disable-cloud"],
        capture_output=True, text=True, timeout=300, check=False,
    )
    if r.returncode != 0:
        raise RuntimeError(f"Netdata install failed: {r.stderr[:500]}")
    _push(job_id, "Netdata installed ✓ — runs on port 19999")
    return {"url": f"http://{DOMAIN}:19999", "note": "Start with: systemctl start netdata"}


def _install_zabbix(cfg: dict, job_id: str) -> dict:
    db_name, db_user, db_pass = cfg["db_name"], cfg["db_user"], cfg["db_pass"]
    _push(job_id, f"Creating Zabbix database `{db_name}`…")
    ok, err = _create_db(db_name, db_user, db_pass)
    if not ok:
        raise RuntimeError(f"DB creation failed: {err}")
    _push(job_id, "Installing Zabbix via apt…")
    subprocess.run(["bash", "-c",
        "wget -q https://repo.zabbix.com/zabbix/6.4/debian/pool/main/z/zabbix-release/zabbix-release_6.4-1+debian12_all.deb -O /tmp/zabbix.deb && dpkg -i /tmp/zabbix.deb && apt-get update -q && apt-get install -y -q zabbix-server-mysql zabbix-frontend-php zabbix-apache-conf zabbix-sql-scripts"
    ], capture_output=True, timeout=300, check=False)
    _push(job_id, "Zabbix installed ✓ — configure /etc/zabbix/zabbix_server.conf and start services")
    return {"url": f"https://{DOMAIN}/zabbix", "note": f"DB: {db_name}, user: {db_user}"}


def _install_paperless(cfg: dict, job_id: str) -> dict:
    _push(job_id, "Installing Paperless-ngx via pip…")
    install_dir = Path("/var/customer/private/paperless")
    install_dir.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["pip3", "install", "--quiet", "paperless-ngx"],
        capture_output=True, text=True, timeout=300, check=False,
    )
    if r.returncode != 0:
        _push(job_id, f"pip install failed, trying alternative…")
    db_name, db_user, db_pass = cfg["db_name"], cfg["db_user"], cfg["db_pass"]
    ok, err = _create_db(db_name, db_user, db_pass)
    if not ok:
        raise RuntimeError(f"DB creation failed: {err}")
    env_content = (
        f"PAPERLESS_SECRET_KEY={_rand_str(50)}\n"
        f"PAPERLESS_URL=https://{DOMAIN}\n"
        f"PAPERLESS_DBENGINE=mariadb\n"
        f"PAPERLESS_DBHOST=127.0.0.1\n"
        f"PAPERLESS_DBNAME={db_name}\n"
        f"PAPERLESS_DBUSER={db_user}\n"
        f"PAPERLESS_DBPASS={db_pass}\n"
        f"PAPERLESS_MEDIA_ROOT=/var/customer/private/paperless/media\n"
        f"PAPERLESS_DATA_DIR=/var/customer/private/paperless/data\n"
    )
    (install_dir / ".env").write_text(env_content)
    _push(job_id, "Paperless-ngx configured ✓")
    return {"url": f"https://{DOMAIN}", "note": "Run: python manage.py migrate && python manage.py createsuperuser"}


_INSTALLERS = {
    "wordpress":  _install_wordpress,
    "joomla":     _install_joomla,
    "drupal":     _install_drupal,
    "grav":       _install_grav,
    "roundcube":  _install_roundcube,
    "snappymail": _install_snappymail,
    "phpmyadmin": _install_phpmyadmin,
    "adminer":    _install_adminer,
    "ghost":        _install_ghost,
    "october":      _install_october,
    "concrete":     _install_concrete,
    "typo3":        _install_typo3,
    "strapi":       _install_strapi,
    "matomo":       _install_matomo,
    "umami":        _install_umami,
    "freshrss":     _install_freshrss,
    "nextcloud":    _install_nextcloud,
    "bookstack":    _install_bookstack,
    "wikijs":       _install_wikijs,
    "gitea":        _install_gitea,
    "codeserver":   _install_codeserver,
    "n8n":          _install_n8n,
    "nodered":      _install_nodered,
    "filebrowser":  _install_filebrowser,
    "uptime":       _install_uptime,
    "vaultwarden":  _install_vaultwarden,
    "invoiceninja": _install_invoiceninja,
}


def _run_install(job_id: str, app_id: str, cfg: dict):
    try:
        fn = _INSTALLERS[app_id]
        result = fn(cfg, job_id)
        _install_jobs[job_id]["status"] = "done"
        _install_jobs[job_id]["result"] = result
        _record_installed(app_id, result)
    except Exception as exc:
        log.exception("Install failed for %s", app_id)
        _install_jobs[job_id]["status"] = "error"
        _install_jobs[job_id]["error"] = str(exc)


# ── Install API ───────────────────────────────────────────────────────────────

@app.get("/install/apps")
def install_list_apps():
    _verify_token()
    return jsonify({k: {"name": k} for k in _INSTALLERS})


@app.get("/install/list")
def install_list_installed():
    _verify_token()
    if not INSTALLED_APPS_FILE.exists():
        return jsonify({"apps": []})
    try:
        return jsonify(json.loads(INSTALLED_APPS_FILE.read_text()))
    except Exception:
        return jsonify({"apps": []})


@app.post("/install")
def install_app():
    _verify_token()
    body   = request.json or {}
    app_id = body.get("app_id", "")
    cfg    = body.get("config", {})

    if app_id not in _INSTALLERS:
        abort(400)

    job_id = secrets.token_hex(8)
    _install_jobs[job_id] = {
        "status": "running",
        "messages": [f"Starting installation of {app_id}…"],
        "error": None,
        "result": None,
    }
    threading.Thread(target=_run_install, args=(job_id, app_id, cfg), daemon=True).start()
    return jsonify({"job_id": job_id})


@app.get("/install/status/<job_id>")
def install_job_status(job_id):
    _verify_token()
    job = _install_jobs.get(job_id)
    if not job:
        abort(404)
    return jsonify(job)


# ══════════════════════════════════════════════════════════════════════════════
# ── SFTP (SSH-based, key-pair, chrooted to webroot) ───────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
#
# Creates an OS user `sftp_<domain>` locked to SFTP-only (no shell),
# chrooted to /var/www/html.  Uses Ed25519 key pair; private key is returned
# once and stored nowhere accessible to the customer (only root can read it
# until they download it).

SFTP_USER       = f"sftp_{re.sub(r'[^a-z0-9]', '_', DOMAIN.lower())[:24]}"
SFTP_KEY_DIR    = DB_DIR / "sftp"
SFTP_INFO_FILE  = SFTP_KEY_DIR / "info.json"


def _sftp_user_exists() -> bool:
    r = subprocess.run(["id", SFTP_USER], capture_output=True)
    return r.returncode == 0


@app.post("/sftp/create")
def sftp_create():
    """
    Create (or rotate) SFTP credentials for this container's domain.
    Returns the Ed25519 private key (PEM) — only time it is readable.
    """
    _verify_token()
    SFTP_KEY_DIR.mkdir(parents=True, exist_ok=True)

    priv_key = SFTP_KEY_DIR / "id_ed25519"
    pub_key  = SFTP_KEY_DIR / "id_ed25519.pub"

    # Remove old keys if rotating
    priv_key.unlink(missing_ok=True)
    pub_key.unlink(missing_ok=True)

    # Generate Ed25519 key pair (no passphrase — panel manages access)
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-N", "", "-C", f"sftp@{DOMAIN}", "-f", str(priv_key)],
        check=True, timeout=15,
    )
    priv_key.chmod(0o600)
    pub_key.chmod(0o644)

    # Create OS user if absent, locked, no shell
    if not _sftp_user_exists():
        subprocess.run(
            ["useradd", "-M", "-s", "/usr/lib/openssh/sftp-server",
             "-d", str(PUBLIC_ROOT), SFTP_USER],
            check=True, timeout=10,
        )
        subprocess.run(["passwd", "-l", SFTP_USER], check=True, timeout=5)

    # Install authorised key
    auth_keys_dir = Path(f"/home/{SFTP_USER}/.ssh")
    auth_keys_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(pub_key), str(auth_keys_dir / "authorized_keys"))
    subprocess.run(["chown", "-R", f"{SFTP_USER}:{SFTP_USER}", str(auth_keys_dir)], check=True)
    subprocess.run(["chmod", "700", str(auth_keys_dir)], check=True)
    subprocess.run(["chmod", "600", str(auth_keys_dir / "authorized_keys")], check=True)

    # Chroot requires root-owned target dir
    subprocess.run(["chown", "root:root", str(PUBLIC_ROOT)], check=True)
    subprocess.run(["chmod", "755", str(PUBLIC_ROOT)], check=True)

    # Determine the SSH port exposed to the outside world
    ssh_port_file = DB_DIR / "ssh_port.txt"
    ext_port = ssh_port_file.read_text().strip() if ssh_port_file.exists() else "22"

    info = {
        "user":     SFTP_USER,
        "host":     DOMAIN,
        "port":     ext_port,
        "key_type": "ed25519",
        "webroot":  str(PUBLIC_ROOT),
        "created":  int(time.time()),
    }
    SFTP_INFO_FILE.write_text(json.dumps(info))

    return jsonify({
        "ok":          True,
        "private_key": priv_key.read_text(),  # returned once — customer must save it
        "info":        info,
    })


@app.get("/sftp/info")
def sftp_info():
    """Return current SFTP connection info (no private key)."""
    _verify_token()
    if not SFTP_INFO_FILE.exists():
        return jsonify({"configured": False})
    data = json.loads(SFTP_INFO_FILE.read_text())
    return jsonify({"configured": True, **data})


@app.delete("/sftp/revoke")
def sftp_revoke():
    """Remove SFTP access — deletes OS user and keys."""
    _verify_token()
    if _sftp_user_exists():
        subprocess.run(["userdel", "-r", SFTP_USER], check=False, timeout=10)
    for f in [SFTP_KEY_DIR / "id_ed25519", SFTP_KEY_DIR / "id_ed25519.pub", SFTP_INFO_FILE]:
        f.unlink(missing_ok=True)
    return jsonify({"ok": True})


# ── SSH key helpers (shared by webuser and admin endpoints) ───────────────────

_VALID_KEY_TYPES = {
    "ssh-rsa", "ssh-ed25519", "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521",
    "sk-ssh-ed25519@openssh.com", "sk-ecdsa-sha2-nistp256@openssh.com",
}


def _validate_ssh_pubkey(key: str) -> bool:
    """Basic structural validation: must start with a known key type."""
    parts = key.strip().split()
    return len(parts) >= 2 and parts[0] in _VALID_KEY_TYPES


# ── Domain customer (webuser) SSH key management ─────────────────────────────

WEBUSER_SSH_DIR   = Path("/home/webuser/.ssh")
WEBUSER_AUTH_KEYS = WEBUSER_SSH_DIR / "authorized_keys"


@app.post("/webuser/ssh-key")
def webuser_ssh_key():
    """
    Set the SSH public key for the domain customer (webuser).
    webuser gets a real bash shell with access to /var/www/html and PHP tools.
    Replaces any existing key (idempotent — call again to rotate).
    """
    _verify_token()
    body = request.json or {}
    key = (body.get("public_key") or "").strip()
    if not key:
        abort(400)
    if not _validate_ssh_pubkey(key):
        abort(400)

    WEBUSER_SSH_DIR.mkdir(parents=True, exist_ok=True)
    WEBUSER_SSH_DIR.chmod(0o700)
    shutil.chown(str(WEBUSER_SSH_DIR), "webuser", "webuser")

    WEBUSER_AUTH_KEYS.write_text(key + "\n")
    WEBUSER_AUTH_KEYS.chmod(0o600)
    shutil.chown(str(WEBUSER_AUTH_KEYS), "webuser", "webuser")

    log.info("webuser SSH key set for domain %s", DOMAIN)
    return jsonify({"ok": True, "domain": DOMAIN, "user": "webuser"})


@app.delete("/webuser/ssh-key")
def webuser_ssh_key_revoke():
    """Remove the webuser SSH key."""
    _verify_token()
    if WEBUSER_AUTH_KEYS.exists():
        WEBUSER_AUTH_KEYS.write_text("")
    log.info("webuser SSH key revoked for domain %s", DOMAIN)
    return jsonify({"ok": True})


# ── Superadmin SSH key injection ──────────────────────────────────────────────

ADMIN_SSH_DIR   = Path("/home/gnukontrolr-admin/.ssh")
ADMIN_AUTH_KEYS = ADMIN_SSH_DIR / "authorized_keys"


@app.post("/admin/ssh-key")
def admin_ssh_key():
    """
    Inject a superadmin SSH public key into gnukontrolr-admin's authorized_keys.
    Replaces all existing keys (idempotent — call again to rotate).
    Only callable with a valid CONTAINER_API_TOKEN.
    """
    _verify_token()
    body = request.json or {}
    key = (body.get("public_key") or "").strip()
    if not key:
        abort(400)
    if not _validate_ssh_pubkey(key):
        abort(400)

    ADMIN_SSH_DIR.mkdir(parents=True, exist_ok=True)
    ADMIN_SSH_DIR.chmod(0o700)
    shutil.chown(str(ADMIN_SSH_DIR), "gnukontrolr-admin", "gnukontrolr")

    ADMIN_AUTH_KEYS.write_text(key + "\n")
    ADMIN_AUTH_KEYS.chmod(0o600)
    shutil.chown(str(ADMIN_AUTH_KEYS), "gnukontrolr-admin", "gnukontrolr")

    log.info("Superadmin SSH key injected for domain %s", DOMAIN)
    return jsonify({"ok": True, "domain": DOMAIN, "user": "gnukontrolr-admin"})


@app.delete("/admin/ssh-key")
def admin_ssh_key_revoke():
    """Remove the superadmin SSH key — closes the admin SSH backdoor."""
    _verify_token()
    if ADMIN_AUTH_KEYS.exists():
        ADMIN_AUTH_KEYS.write_text("")
    log.info("Superadmin SSH key revoked for domain %s", DOMAIN)
    return jsonify({"ok": True})


# ── Site backup ───────────────────────────────────────────────────────────────
#
# Backup types:
#   website — /var/www/html (web files) + MariaDB dump
#   files   — /var/www/html only
#   db      — MariaDB dump only
#   full    — website + /var/config (nginx, php, env, ssl configs)
#
# Backups are stored in /var/customer/backups/ as .tar.gz archives.
# A maximum of 10 backups are kept; oldest are pruned automatically.

SITE_BACKUP_MAX = 10


def _db_credentials() -> tuple[str, str, str]:
    """Return (db_name, user, password) from the container's env file."""
    env_file = ENV_DIR / "site.env"
    db_name  = DOMAIN.replace(".", "_").replace("-", "_")
    user     = "site_" + db_name
    password = ""
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("DB_PASSWORD="):
                password = line.split("=", 1)[1].strip()
            elif line.startswith("DB_USER="):
                user = line.split("=", 1)[1].strip()
            elif line.startswith("DB_NAME="):
                db_name = line.split("=", 1)[1].strip()
    return db_name, user, password


@app.get("/site-backup/list")
def site_backup_list():
    _verify_token()
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    backups = []
    for f in sorted(BACKUPS_DIR.glob("site-backup-*.tar.gz"), reverse=True):
        stat = f.stat()
        backups.append({
            "filename": f.name,
            "size":     stat.st_size,
            "created":  int(stat.st_mtime),
        })
    return jsonify({"backups": backups})


@app.post("/site-backup/create")
def site_backup_create():
    """Create a site backup.  body.type = website (default) | files | db | full."""
    _verify_token()
    backup_type = (request.json or {}).get("type", "website")
    if backup_type not in ("website", "files", "db", "full"):
        backup_type = "website"

    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

    ts       = int(time.time())
    filename = f"site-backup-{backup_type}-{ts}.tar.gz"
    dest     = BACKUPS_DIR / filename

    include_files  = backup_type in ("website", "files", "full")
    include_db     = backup_type in ("website", "db", "full")
    include_config = backup_type == "full"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        parts    = []

        if include_files and PUBLIC_ROOT.exists():
            parts.append(("files", str(PUBLIC_ROOT)))

        if include_config and SECURE_ROOT.exists():
            parts.append(("config", str(SECURE_ROOT)))

        if include_db:
            db_name, db_user, db_pass = _db_credentials()
            dump_file = tmp_path / "database.sql"
            env = os.environ.copy()
            env["MYSQL_PWD"] = db_pass
            result = subprocess.run(
                ["mysqldump", "-u", db_user, db_name],
                capture_output=True, env=env, timeout=120,
            )
            if result.returncode == 0:
                dump_file.write_bytes(result.stdout)
                parts.append(("database.sql", str(dump_file)))
            else:
                log.warning("mysqldump failed: %s", result.stderr.decode()[:200])

        # Build tar.gz
        cmd = ["tar", "-czf", str(dest)]
        for label, path_str in parts:
            cmd += ["-C", str(Path(path_str).parent), Path(path_str).name]
        subprocess.run(cmd, check=True, timeout=300)

    # Prune old backups
    all_backups = sorted(BACKUPS_DIR.glob("site-backup-*.tar.gz"), key=lambda f: f.stat().st_mtime)
    while len(all_backups) > SITE_BACKUP_MAX:
        all_backups.pop(0).unlink(missing_ok=True)

    stat = dest.stat()
    return jsonify({"ok": True, "filename": filename, "size": stat.st_size})


@app.delete("/site-backup/<filename>")
def site_backup_delete(filename: str):
    _verify_token()
    # Sanitise — only allow safe filenames
    if not re.match(r'^site-backup-[\w\-]+\.tar\.gz$', filename):
        abort(400)
    f = BACKUPS_DIR / filename
    if f.exists():
        f.unlink()
    return jsonify({"ok": True})


@app.get("/site-backup/download/<filename>")
def site_backup_download(filename: str):
    _verify_token()
    if not re.match(r'^site-backup-[\w\-]+\.tar\.gz$', filename):
        abort(400)
    f = BACKUPS_DIR / filename
    if not f.exists():
        abort(404)
    from flask import send_file
    return send_file(str(f), as_attachment=True, download_name=filename,
                     mimetype="application/gzip")


# ── Security Scanner ──────────────────────────────────────────────────────────
#
# Called by the panel's /api/scanner/scan endpoint (admin-only).
# Runs clamscan on the requested area and returns per-file results.
# Also provides quarantine support for confirmed malware.

QUARANTINE_DIR = Path("/var/customer/quarantine")
QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)

_AREA_PATHS_MAP = {
    "public":  Path("/var/www/html"),
    "uploads": Path("/var/customer/uploads"),
    "private": Path("/var/customer/private"),
}


@app.route("/scanner/scan", methods=["POST"])
def scanner_scan():
    """Run ClamAV on an area and return per-file results."""
    _verify_token()
    body = request.get_json(force=True) or {}
    area = body.get("area", "public")
    if area not in _AREA_PATHS_MAP:
        return jsonify({"error": "Invalid area"}), 400

    scan_path = _AREA_PATHS_MAP[area]
    if not scan_path.exists():
        return jsonify({"results": [], "summary": "Directory not found"}), 200

    try:
        result = subprocess.run(
            ["clamscan", "--recursive", "--infected", "--no-summary",
             "--stdout", str(scan_path)],
            capture_output=True, text=True, timeout=180,
        )
    except FileNotFoundError:
        return jsonify({"error": "ClamAV (clamscan) not installed in container"}), 503
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Scan timed out (180s)"}), 504

    # Parse clamscan output: "FOUND" lines = infected
    results = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("---"):
            continue
        if "FOUND" in line:
            # Format: /path/to/file: Virus.Name FOUND
            parts = line.rsplit(":", 1)
            filepath = parts[0].strip()
            threat = parts[1].replace("FOUND", "").strip() if len(parts) > 1 else "Unknown"
            results.append({
                "file": filepath,
                "threat": threat,
                "area": area,
            })
        elif ": OK" in line:
            filepath = line.split(":")[0].strip()
            results.append({"file": filepath, "threat": None, "area": area})

    return jsonify({"results": results, "return_code": result.returncode})


@app.route("/scanner/quarantine", methods=["POST"])
def scanner_quarantine():
    """Move a file to quarantine directory."""
    _verify_token()
    body = request.get_json(force=True) or {}
    area = body.get("area", "public")
    rel_path = body.get("path", "")

    if area not in _AREA_PATHS_MAP or not rel_path:
        return jsonify({"error": "Invalid area or path"}), 400

    try:
        src = _safe_path(_AREA_PATHS_MAP[area], rel_path)
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403

    if not src.exists():
        return jsonify({"error": "File not found"}), 404

    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    dest = QUARANTINE_DIR / f"{area}__{rel_path.replace('/', '__')}_{int(time.time())}"
    shutil.move(str(src), str(dest))
    log.warning("QUARANTINE: moved %s → %s", src, dest)
    return jsonify({"ok": True, "quarantined_to": str(dest)})


if __name__ == "__main__":
    if not API_TOKEN:
        log.error("FATAL: CONTAINER_API_TOKEN must be set in production. Refusing to start without token.")
        # Still start in dev — but print loud warning
    log.info("Container API starting for domain: %s", DOMAIN)

    # Load TLS cert if available — encrypts all panel ↔ container-API traffic
    cert = Path("/var/db/api_cert.pem")
    key  = Path("/var/db/api_key.pem")
    if cert.exists() and key.exists():
        log.info("TLS enabled: using %s", cert)
        ssl_ctx = (str(cert), str(key))
    else:
        log.warning("TLS cert not found — running unencrypted (dev mode only)")
        ssl_ctx = None

    app.run(host=LISTEN_HOST, port=9000, debug=False, threaded=True,
            ssl_context=ssl_ctx)
