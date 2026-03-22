"""
Customer services marketplace.
Allows customers to install / enable / disable additional services
inside their domain container: Nginx, Apache, Lighttpd, Node.js,
Laravel, WordPress, Django, etc.
"""
import json
import subprocess
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import get_current_user, require_admin
from app.models.user import User, Role

router = APIRouter(prefix="/api/services", tags=["services"])

# ────────────────────────────────────────────────────────────────────────────
# Service catalogue — what customers can install
# ────────────────────────────────────────────────────────────────────────────
CATALOGUE: dict[str, dict] = {
    # ── Web Servers ──────────────────────────────────────────────────────────
    "nginx": {
        "name": "Nginx",
        "category": "web_server",
        "description": "High-performance HTTP server and reverse proxy.",
        "icon": "🌐",
        "supervisor_program": "nginx",
        "web_server_value": "nginx",
        "incompatible": ["apache", "lighttpd"],
    },
    "apache": {
        "name": "Apache 2",
        "category": "web_server",
        "description": "The world's most widely used web server, with .htaccess support.",
        "icon": "🪶",
        "supervisor_program": "apache2",
        "web_server_value": "apache",
        "incompatible": ["nginx", "lighttpd"],
    },
    "lighttpd": {
        "name": "Lighttpd",
        "category": "web_server",
        "description": "Lightweight, high-speed web server ideal for low-memory environments.",
        "icon": "⚡",
        "supervisor_program": "lighttpd",
        "web_server_value": "lighttpd",
        "incompatible": ["nginx", "apache"],
    },
    # ── Runtime ──────────────────────────────────────────────────────────────
    "nodejs": {
        "name": "Node.js 20",
        "category": "runtime",
        "description": "JavaScript runtime powered by Chrome V8 engine, with PM2 process manager.",
        "icon": "🟢",
        "supervisor_program": "node",
        "env_key": "NODE_ENABLED",
        "env_value": "true",
        "incompatible": [],
    },
    # ── PHP Frameworks ────────────────────────────────────────────────────────
    "laravel": {
        "name": "Laravel",
        "category": "php_framework",
        "description": "The PHP framework for web artisans. Installs via Composer.",
        "icon": "🔴",
        "install_cmd": ["composer", "create-project", "laravel/laravel", "/var/www/html", "--prefer-dist"],
        "requires": ["nginx"],
        "incompatible": ["wordpress"],
    },
    "wordpress": {
        "name": "WordPress",
        "category": "php_framework",
        "description": "World's most popular CMS. Installed via WP-CLI.",
        "icon": "🔵",
        "install_cmd": [
            "bash", "-c",
            "wp core download --path=/var/www/html --allow-root && "
            "wp config create --path=/var/www/html --dbhost=$DB_HOST "
            "--dbname=$DB_NAME --dbuser=$DB_USER --dbpass=$DB_PASS --allow-root"
        ],
        "requires": ["nginx"],
        "incompatible": ["laravel", "django"],
    },
    "codeigniter": {
        "name": "CodeIgniter 4",
        "category": "php_framework",
        "description": "Lightweight PHP framework with a small footprint.",
        "icon": "🔥",
        "install_cmd": ["composer", "create-project", "codeigniter4/appstarter", "/var/www/html"],
        "requires": ["nginx"],
        "incompatible": ["laravel", "wordpress"],
    },
    # ── Python ────────────────────────────────────────────────────────────────
    "django": {
        "name": "Django",
        "category": "python_framework",
        "description": "High-level Python web framework. Served via Gunicorn + Nginx.",
        "icon": "🐍",
        "install_cmd": [
            "bash", "-c",
            "pip3 install django gunicorn && "
            "django-admin startproject mysite /var/www/app"
        ],
        "requires": ["nginx"],
        "incompatible": ["laravel", "wordpress"],
    },
    "flask": {
        "name": "Flask",
        "category": "python_framework",
        "description": "Lightweight WSGI Python microframework.",
        "icon": "🫙",
        "install_cmd": ["bash", "-c", "pip3 install flask gunicorn"],
        "requires": ["nginx"],
        "incompatible": [],
    },
    # ── Databases ─────────────────────────────────────────────────────────────
    "sqlite": {
        "name": "SQLite",
        "category": "database",
        "description": "Serverless embedded SQL database. Stored at /var/db/site.db.",
        "icon": "📦",
        "incompatible": [],
    },
    # ── Other ─────────────────────────────────────────────────────────────────
    "composer": {
        "name": "Composer",
        "category": "tool",
        "description": "PHP dependency manager. Pre-installed — always available.",
        "icon": "📦",
        "always_installed": True,
        "incompatible": [],
    },
    "wpcli": {
        "name": "WP-CLI",
        "category": "tool",
        "description": "Command-line tool for managing WordPress installations.",
        "icon": "🔧",
        "always_installed": True,
        "incompatible": [],
    },
    "pm2": {
        "name": "PM2",
        "category": "tool",
        "description": "Production Node.js process manager. Available when Node.js is enabled.",
        "icon": "🔄",
        "always_installed": True,
        "incompatible": [],
    },
}

# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def _container_name(domain: str) -> str:
    return "site_" + domain.replace(".", "_").replace("-", "_")


def _run_in_container(domain: str, cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
    container = _container_name(domain)
    r = subprocess.run(
        ["docker", "exec", container] + cmd,
        capture_output=True, text=True, timeout=timeout
    )
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def _get_container_env(domain: str, key: str) -> str:
    """Read an environment variable from the running container."""
    code, out, _ = _run_in_container(domain, ["printenv", key])
    return out if code == 0 else ""


def _supervisor_ctl(domain: str, action: str, program: str) -> tuple[int, str]:
    code, out, err = _run_in_container(domain, ["supervisorctl", action, program])
    return code, out or err


def _detect_installed(domain: str) -> dict[str, bool]:
    """Detect which services are running inside the container."""
    installed: dict[str, bool] = {}
    for key, info in CATALOGUE.items():
        if info.get("always_installed"):
            installed[key] = True
            continue
        if "supervisor_program" in info:
            code, out, _ = _run_in_container(domain, [
                "supervisorctl", "status", info["supervisor_program"]
            ])
            installed[key] = "RUNNING" in out
        elif "env_key" in info:
            val = _get_container_env(domain, info["env_key"])
            installed[key] = val.lower() == "true"
        else:
            installed[key] = False
    return installed


# ────────────────────────────────────────────────────────────────────────────
# Routes
# ────────────────────────────────────────────────────────────────────────────

@router.get("/catalogue")
async def get_catalogue():
    """Return the full services catalogue."""
    return CATALOGUE


@router.get("/{domain}")
async def list_domain_services(domain: str, user: User = Depends(get_current_user)):
    """List installed / running services for a domain container."""
    try:
        installed = _detect_installed(domain)
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Container not responding")
    except Exception as exc:
        raise HTTPException(500, str(exc))
    return {
        "domain": domain,
        "services": installed,
        "catalogue": CATALOGUE,
    }


class ServiceAction(BaseModel):
    action: str   # enable | disable | install | uninstall


@router.post("/{domain}/{service_id}")
async def service_action(
    domain: str,
    service_id: str,
    body: ServiceAction,
    user: User = Depends(get_current_user),
):
    """Enable, disable, install, or uninstall a service on a domain container."""
    info = CATALOGUE.get(service_id)
    if not info:
        raise HTTPException(404, f"Unknown service: {service_id}")

    if info.get("always_installed"):
        return {"ok": True, "message": f"{info['name']} is always available."}

    action = body.action.lower()

    if action in ("enable", "start"):
        # ── Web server: switch active server ──────────────────────────────
        if "web_server_value" in info:
            # Stop incompatible web servers first
            for inc in info.get("incompatible", []):
                inc_info = CATALOGUE.get(inc, {})
                if "supervisor_program" in inc_info:
                    _supervisor_ctl(domain, "stop", inc_info["supervisor_program"])
            # Update env in container (write to /etc/environment)
            ws_val = info["web_server_value"]
            _run_in_container(domain, [
                "bash", "-c",
                "echo 'WEB_SERVER=" + ws_val + "' >> /etc/environment"
            ])
            code, msg = _supervisor_ctl(domain, "start", info["supervisor_program"])
        elif "env_key" in info:
            env_key = info["env_key"]
            env_val = info["env_value"]
            _run_in_container(domain, [
                "bash", "-c",
                "echo '" + env_key + "=" + env_val + "' >> /etc/environment"
            ])
            code, msg = _supervisor_ctl(domain, "start", info["supervisor_program"])
        else:
            raise HTTPException(400, f"Service {service_id} cannot be enabled this way.")
        return {"ok": code == 0, "output": msg}

    elif action in ("disable", "stop"):
        if "supervisor_program" in info:
            code, msg = _supervisor_ctl(domain, "stop", info["supervisor_program"])
        else:
            raise HTTPException(400, f"Service {service_id} cannot be disabled this way.")
        return {"ok": code == 0, "output": msg}

    elif action == "install":
        install_cmd = info.get("install_cmd")
        if not install_cmd:
            return {"ok": True, "message": f"{info['name']} is pre-installed. Use 'enable' to activate."}
        code, out, err = _run_in_container(domain, install_cmd, timeout=300)
        if code != 0:
            raise HTTPException(500, f"Install failed: {err}")
        return {"ok": True, "output": out}

    elif action == "uninstall":
        # For safety, only stop the service — don't delete customer files
        if "supervisor_program" in info:
            _supervisor_ctl(domain, "stop", info["supervisor_program"])
        return {"ok": True, "message": f"{info['name']} stopped. Files preserved."}

    else:
        raise HTTPException(400, f"Unknown action: {action}")


@router.get("/{domain}/{service_id}/status")
async def service_status(domain: str, service_id: str, _=Depends(get_current_user)):
    """Check status of a specific service in a domain container."""
    info = CATALOGUE.get(service_id)
    if not info:
        raise HTTPException(404, f"Unknown service: {service_id}")

    if "supervisor_program" in info:
        code, out, _ = _run_in_container(domain, [
            "supervisorctl", "status", info["supervisor_program"]
        ])
        running = "RUNNING" in out
        return {"service": service_id, "running": running, "detail": out}

    return {"service": service_id, "running": info.get("always_installed", False)}
