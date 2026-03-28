"""
Marketplace router — proxies one-click app install requests to the per-domain
container API and returns live install-job status.

Endpoints
---------
GET  /api/marketplace/apps                     — full app catalogue
GET  /api/marketplace/installed/{domain}       — apps already installed on domain
POST /api/marketplace/install                  — start an install job
GET  /api/marketplace/install/status/{domain}/{job_id}  — poll job progress
GET  /api/marketplace/cache                    — list panel-side cached archives
POST /api/marketplace/cache/refresh            — download/update cache for all apps
POST /api/marketplace/cache/refresh/{app_id}  — refresh one app
DELETE /api/marketplace/cache/{app_id}         — purge an app's cached archives
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List
import secrets
import string
import os
import json
import time
import shutil
import threading
import urllib.request
from pathlib import Path

from datetime import datetime
from sqlalchemy import select, delete
from app.auth import get_current_user, require_admin
from app.database import get_db as get_db_dep, AsyncSession
from app.models.installed_app import InstalledApp
from app.routers.container_proxy import _container_api_url, _TLS_VERIFY
from app.dns_helper import register_vdns
import httpx
from app.http_client import panel_client
from app.notify import push as notify_push

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])

TIMEOUT = httpx.Timeout(connect=5, read=300, write=30, pool=5)  # long read for downloads

# ── App catalogue (source of truth on the panel side) ─────────────────────────

APP_CATALOG = {
    # ── CMS ───────────────────────────────────────────────────────────────────
    "wordpress": {
        "id": "wordpress", "category": "cms",
        "name": "WordPress",  "version": "6.x (latest)",
        "description": "World's most popular CMS. Powers over 43 % of all websites. Ideal for blogs, business sites, WooCommerce stores, and more.",
        "disk": "~55 MB", "language": "PHP",
        "requires_db": True, "color": "from-blue-600/25 to-blue-900/10 border-blue-700/40",
    },
    "joomla": {
        "id": "joomla", "category": "cms",
        "name": "Joomla", "version": "5.x (latest)",
        "description": "Flexible, award-winning CMS with a strong extension ecosystem. Great for community portals, e-commerce, and complex structured-content sites.",
        "disk": "~35 MB", "language": "PHP",
        "requires_db": True, "color": "from-orange-600/25 to-orange-900/10 border-orange-700/40",
    },
    "drupal": {
        "id": "drupal", "category": "cms",
        "name": "Drupal", "version": "10.x (latest)",
        "description": "Enterprise-grade CMS trusted by governments and Fortune 500s. Unmatched flexibility for complex, high-traffic content architectures.",
        "disk": "~30 MB", "language": "PHP",
        "requires_db": True, "color": "from-cyan-600/25 to-cyan-900/10 border-cyan-700/40",
    },
    "grav": {
        "id": "grav", "category": "cms",
        "name": "Grav", "version": "1.x (latest)",
        "description": "Modern flat-file CMS — no database needed. Blazing fast, uses Markdown, Twig templates and a powerful plugin system.",
        "disk": "~28 MB", "language": "PHP",
        "requires_db": False, "color": "from-emerald-600/25 to-emerald-900/10 border-emerald-700/40",
    },
    # ── Webmail ───────────────────────────────────────────────────────────────
    "roundcube": {
        "id": "roundcube", "category": "webmail",
        "name": "Roundcube", "version": "1.6.x (latest)",
        "description": "Classic, full-featured browser-based IMAP client. Rich text composition, address book, folder management, and plugin support.",
        "disk": "~22 MB", "language": "PHP",
        "requires_db": True, "color": "from-green-600/25 to-green-900/10 border-green-700/40",
    },
    "snappymail": {
        "id": "snappymail", "category": "webmail",
        "name": "SnappyMail", "version": "2.x (latest)",
        "description": "Modern, lightweight webmail. Faster and more secure successor to RainLoop. Clean UI, dark mode, PGP support, and multi-account handling.",
        "disk": "~8 MB", "language": "PHP",
        "requires_db": False, "color": "from-sky-600/25 to-sky-900/10 border-sky-700/40",
    },
    # ── Tools ─────────────────────────────────────────────────────────────────
    "phpmyadmin": {
        "id": "phpmyadmin", "category": "tools",
        "name": "phpMyAdmin", "version": "5.2.x (latest)",
        "description": "The most widely used MySQL/MariaDB web interface. Browse tables, run SQL, import/export dumps, manage users and permissions.",
        "disk": "~16 MB", "language": "PHP",
        "requires_db": False, "color": "from-yellow-600/25 to-yellow-900/10 border-yellow-700/40",
    },
    "adminer": {
        "id": "adminer", "category": "tools",
        "name": "Adminer", "version": "4.x (latest)",
        "description": "Full-featured database manager in a single PHP file. Supports MySQL, PostgreSQL, SQLite, MongoDB. Tiny footprint, zero dependencies.",
        "disk": "< 1 MB", "language": "PHP",
        "requires_db": False, "color": "from-purple-600/25 to-purple-900/10 border-purple-700/40",
    },
    # ── CMS (additional) ──────────────────────────────────────────────────────
    "ghost": {
        "id": "ghost", "category": "cms",
        "name": "Ghost", "version": "5.x (latest)",
        "description": "Modern Node.js blog and publication platform. Beautiful editor, native SEO, newsletter and membership features built in.",
        "disk": "~120 MB", "language": "Node.js",
        "requires_db": False, "color": "from-gray-600/25 to-gray-900/10 border-gray-700/40",
    },
    "october": {
        "id": "october", "category": "cms",
        "name": "October CMS", "version": "3.x (latest)",
        "description": "Elegant PHP CMS with a rich plugin ecosystem. Combines the simplicity of a flat-file structure with the power of a full database backend.",
        "disk": "~45 MB", "language": "PHP",
        "requires_db": True, "color": "from-teal-600/25 to-teal-900/10 border-teal-700/40",
    },
    "concrete": {
        "id": "concrete", "category": "cms",
        "name": "Concrete CMS", "version": "9.x (latest)",
        "description": "PHP CMS with in-context editing — click anything on the page to edit it. Ideal for institutional sites, schools, and government portals.",
        "disk": "~48 MB", "language": "PHP",
        "requires_db": True, "color": "from-blue-700/25 to-blue-900/10 border-blue-800/40",
    },
    "typo3": {
        "id": "typo3", "category": "cms",
        "name": "TYPO3", "version": "v12 (latest)",
        "description": "PHP enterprise CMS used by large organisations and governments worldwide. Multi-site, multi-language, granular access control.",
        "disk": "~65 MB", "language": "PHP",
        "requires_db": True, "color": "from-orange-600/25 to-orange-900/10 border-orange-700/40",
    },
    "strapi": {
        "id": "strapi", "category": "cms",
        "name": "Strapi", "version": "4.x (latest)",
        "description": "Node.js headless CMS with REST and GraphQL APIs out of the box. Customisable content types, roles, and a clean admin UI.",
        "disk": "~180 MB", "language": "Node.js",
        "requires_db": True, "color": "from-indigo-600/25 to-indigo-900/10 border-indigo-700/40",
    },
    # ── Analytics ─────────────────────────────────────────────────────────────
    "matomo": {
        "id": "matomo", "category": "analytics",
        "name": "Matomo", "version": "5.x (latest)",
        "description": "Self-hosted web analytics platform. GDPR-friendly Google Analytics alternative with full data ownership and 100 % accurate stats.",
        "disk": "~35 MB", "language": "PHP",
        "requires_db": True, "color": "from-purple-600/25 to-purple-900/10 border-purple-700/40",
    },
    "umami": {
        "id": "umami", "category": "analytics",
        "name": "Umami", "version": "2.x (latest)",
        "description": "Simple, fast, privacy-focused analytics dashboard. No cookies, no personal data collected. Lightweight single-page app.",
        "disk": "~50 MB", "language": "Node.js",
        "requires_db": True, "color": "from-slate-600/25 to-slate-900/10 border-slate-700/40",
    },
    "freshrss": {
        "id": "freshrss", "category": "analytics",
        "name": "FreshRSS", "version": "1.24.x (latest)",
        "description": "Self-hosted RSS and Atom feed aggregator. Keyboard shortcuts, multi-user, mobile-friendly, and supports many third-party clients.",
        "disk": "~14 MB", "language": "PHP",
        "requires_db": True, "color": "from-orange-500/25 to-orange-900/10 border-orange-600/40",
    },
    # ── Collaboration ─────────────────────────────────────────────────────────
    "nextcloud": {
        "id": "nextcloud", "category": "collaboration",
        "name": "Nextcloud", "version": "28.x (latest)",
        "description": "Self-hosted file sync, sharing, calendar, and contacts. The all-in-one collaboration platform — your private Google Workspace.",
        "disk": "~115 MB", "language": "PHP",
        "requires_db": True, "color": "from-blue-500/25 to-blue-900/10 border-blue-600/40",
    },
    "bookstack": {
        "id": "bookstack", "category": "collaboration",
        "name": "BookStack", "version": "23.x (latest)",
        "description": "Simple, self-hosted documentation and wiki platform. Organise content as Books, Chapters, and Pages with a familiar editor.",
        "disk": "~30 MB", "language": "PHP",
        "requires_db": True, "color": "from-amber-600/25 to-amber-900/10 border-amber-700/40",
    },
    "wikijs": {
        "id": "wikijs", "category": "collaboration",
        "name": "Wiki.js", "version": "2.x (latest)",
        "description": "Powerful Node.js wiki with full-text search, many auth methods (LDAP, OAuth, SAML), and a sleek markdown editor.",
        "disk": "~90 MB", "language": "Node.js",
        "requires_db": True, "color": "from-green-600/25 to-green-900/10 border-green-700/40",
    },
    "gitea": {
        "id": "gitea", "category": "collaboration",
        "name": "Gitea", "version": "1.21 (latest)",
        "description": "Lightweight self-hosted Git service with issues, pull requests, and CI pipelines. Single binary, minimal resource use.",
        "disk": "~80 MB", "language": "Go",
        "requires_db": False, "color": "from-green-700/25 to-green-900/10 border-green-800/40",
    },
    # ── Developer ─────────────────────────────────────────────────────────────
    "codeserver": {
        "id": "codeserver", "category": "developer",
        "name": "code-server", "version": "4.x (latest)",
        "description": "VS Code running in the browser — a full IDE accessible from any device. Persistent workspace, extensions, integrated terminal.",
        "disk": "~350 MB", "language": "Node.js",
        "requires_db": False, "color": "from-blue-600/25 to-blue-900/10 border-blue-700/40",
    },
    "n8n": {
        "id": "n8n", "category": "developer",
        "name": "n8n", "version": "1.x (latest)",
        "description": "Visual workflow automation with 400 + integrations. Self-hostable alternative to Zapier with fair-code licence.",
        "disk": "~200 MB", "language": "Node.js",
        "requires_db": False, "color": "from-orange-500/25 to-orange-900/10 border-orange-600/40",
    },
    "nodered": {
        "id": "nodered", "category": "developer",
        "name": "Node-RED", "version": "3.x (latest)",
        "description": "Flow-based visual programming tool for IoT and automation. Hundreds of community nodes for hardware, APIs, and online services.",
        "disk": "~120 MB", "language": "Node.js",
        "requires_db": False, "color": "from-red-600/25 to-red-900/10 border-red-700/40",
    },
    # ── Utilities ─────────────────────────────────────────────────────────────
    "filebrowser": {
        "id": "filebrowser", "category": "utilities",
        "name": "File Browser", "version": "2.x (latest)",
        "description": "Sleek web-based file manager with upload, download, rename, move, and user management. Single binary, zero dependencies.",
        "disk": "~10 MB", "language": "Go",
        "requires_db": False, "color": "from-sky-600/25 to-sky-900/10 border-sky-700/40",
    },
    "uptime": {
        "id": "uptime", "category": "utilities",
        "name": "Uptime Kuma", "version": "1.x (latest)",
        "description": "Self-hosted uptime monitoring with alert notifications via Telegram, Slack, email, and more. Beautiful status-page included.",
        "disk": "~60 MB", "language": "Node.js",
        "requires_db": False, "color": "from-green-500/25 to-green-900/10 border-green-600/40",
    },
    "vaultwarden": {
        "id": "vaultwarden", "category": "utilities",
        "name": "Vaultwarden", "version": "1.30.x (latest)",
        "description": "Lightweight Bitwarden-compatible server written in Rust. Self-hosted password manager with browser extension and mobile app support.",
        "disk": "~20 MB", "language": "Rust",
        "requires_db": False, "color": "from-blue-700/25 to-blue-900/10 border-blue-800/40",
    },
    "invoiceninja": {
        "id": "invoiceninja", "category": "utilities",
        "name": "Invoice Ninja", "version": "5.x (latest)",
        "description": "Professional invoicing, quotes, expenses, and client portal. Full billing suite with payment gateway integrations.",
        "disk": "~90 MB", "language": "PHP",
        "requires_db": True, "color": "from-green-600/25 to-green-900/10 border-green-700/40",
    },
    # ── E-commerce ────────────────────────────────────────────────────────────────
    "prestashop": {
        "id": "prestashop", "category": "ecommerce",
        "name": "PrestaShop", "version": "8.x (latest)",
        "description": "Full-featured open-source e-commerce platform. Product catalogue, cart, checkout, promotions, multi-currency and multi-language out of the box.",
        "disk": "~75 MB", "language": "PHP",
        "requires_db": True, "color": "from-pink-600/25 to-pink-900/10 border-pink-700/40",
    },
    "opencart": {
        "id": "opencart", "category": "ecommerce",
        "name": "OpenCart", "version": "4.x (latest)",
        "description": "Lightweight PHP shopping cart. Easy product and category management, multi-store support, and hundreds of free extensions.",
        "disk": "~25 MB", "language": "PHP",
        "requires_db": True, "color": "from-blue-500/25 to-blue-900/10 border-blue-600/40",
    },
    "woocommerce": {
        "id": "woocommerce", "category": "ecommerce",
        "name": "WooCommerce", "version": "8.x + WordPress",
        "description": "WordPress-based e-commerce. Installs WordPress plus WooCommerce with sensible defaults — the world's most popular online store platform.",
        "disk": "~80 MB", "language": "PHP",
        "requires_db": True, "color": "from-purple-600/25 to-purple-900/10 border-purple-700/40",
    },
    # ── Media / Gallery ────────────────────────────────────────────────────────────
    "piwigo": {
        "id": "piwigo", "category": "media",
        "name": "Piwigo", "version": "14.x (latest)",
        "description": "Self-hosted photo gallery application. Organise albums, add tags, share with visitors. Handles tens of thousands of photos efficiently.",
        "disk": "~15 MB", "language": "PHP",
        "requires_db": True, "color": "from-teal-600/25 to-teal-900/10 border-teal-700/40",
    },
    "lychee": {
        "id": "lychee", "category": "media",
        "name": "Lychee", "version": "5.x (latest)",
        "description": "Beautiful self-hosted photo management tool. Drag-and-drop uploads, smart albums, sharing links, and a clean modern UI.",
        "disk": "~30 MB", "language": "PHP",
        "requires_db": True, "color": "from-rose-600/25 to-rose-900/10 border-rose-700/40",
    },
    "jellyfin": {
        "id": "jellyfin", "category": "media",
        "name": "Jellyfin", "version": "10.x (latest)",
        "description": "Free media system to manage and stream your movies, TV, music, and photos. Open-source Plex/Emby alternative with no fees or tracking.",
        "disk": "~150 MB", "language": "C# / .NET",
        "requires_db": False, "color": "from-indigo-600/25 to-indigo-900/10 border-indigo-700/40",
    },
    "immich": {
        "id": "immich", "category": "media",
        "name": "Immich", "version": "1.x (latest)",
        "description": "High-performance self-hosted photo and video management. Mobile backup, facial recognition, map view, and an intuitive timeline — your private Google Photos.",
        "disk": "~200 MB", "language": "Node.js / Go",
        "requires_db": True, "color": "from-amber-500/25 to-amber-900/10 border-amber-600/40",
    },
    # ── Productivity ───────────────────────────────────────────────────────────────
    "moodle": {
        "id": "moodle", "category": "productivity",
        "name": "Moodle", "version": "4.x (latest)",
        "description": "World's leading open-source Learning Management System (LMS). Courses, quizzes, assignments, forums, and SCORM support.",
        "disk": "~65 MB", "language": "PHP",
        "requires_db": True, "color": "from-orange-600/25 to-orange-900/10 border-orange-700/40",
    },
    "monica": {
        "id": "monica", "category": "productivity",
        "name": "Monica", "version": "4.x (latest)",
        "description": "Personal CRM to organise your relationships. Track contacts, interactions, birthdays, notes, and relationship graphs.",
        "disk": "~40 MB", "language": "PHP",
        "requires_db": True, "color": "from-pink-500/25 to-pink-900/10 border-pink-600/40",
    },
    "yourls": {
        "id": "yourls", "category": "productivity",
        "name": "YOURLS", "version": "1.x (latest)",
        "description": "Your Own URL Shortener — a self-hosted link shortening service with stats, bookmarklets, and a clean admin interface.",
        "disk": "~2 MB", "language": "PHP",
        "requires_db": True, "color": "from-cyan-600/25 to-cyan-900/10 border-cyan-700/40",
    },
    "paperless": {
        "id": "paperless", "category": "productivity",
        "name": "Paperless-ngx", "version": "2.x (latest)",
        "description": "Document management system — scan, index, and archive all your paper documents. OCR, tags, correspondents, and full-text search.",
        "disk": "~80 MB", "language": "Python",
        "requires_db": True, "color": "from-green-700/25 to-green-900/10 border-green-800/40",
    },
    # ── Monitoring ─────────────────────────────────────────────────────────────────
    "grafana": {
        "id": "grafana", "category": "monitoring",
        "name": "Grafana", "version": "10.x (latest)",
        "description": "Leading open-source observability platform. Beautiful dashboards for metrics, logs, and traces. Connects to 80 + data sources.",
        "disk": "~75 MB", "language": "Go",
        "requires_db": False, "color": "from-orange-500/25 to-orange-900/10 border-orange-600/40",
    },
    "netdata": {
        "id": "netdata", "category": "monitoring",
        "name": "Netdata", "version": "1.x (latest)",
        "description": "Real-time server performance monitoring. CPU, memory, disk, network, application metrics — all in a single drag-and-drop dashboard.",
        "disk": "~40 MB", "language": "C",
        "requires_db": False, "color": "from-green-600/25 to-green-900/10 border-green-700/40",
    },
    "zabbix": {
        "id": "zabbix", "category": "monitoring",
        "name": "Zabbix", "version": "6.x (latest)",
        "description": "Enterprise-grade monitoring solution for networks, servers, cloud and applications. Triggers, escalations, and customisable dashboards.",
        "disk": "~55 MB", "language": "PHP / C",
        "requires_db": True, "color": "from-red-600/25 to-red-900/10 border-red-700/40",
    },
}


def _rand_pass(n: int = 20) -> str:
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(n))


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/apps")
async def list_apps(_user=Depends(get_current_user)):
    return APP_CATALOG


@router.get("/my-installs")
async def list_my_installs(user=Depends(get_current_user), db: AsyncSession = Depends(get_db_dep)):
    """Return all apps installed by the current user across all their domains."""
    from app.models.user import Role
    if user.role in (Role.superadmin, Role.admin):
        result = await db.execute(select(InstalledApp).order_by(InstalledApp.installed_at.desc()))
    else:
        result = await db.execute(
            select(InstalledApp)
            .where(InstalledApp.owner_id == user.id)
            .order_by(InstalledApp.installed_at.desc())
        )
    rows = result.scalars().all()
    return [
        {
            "id": r.id, "owner_id": r.owner_id, "domain_name": r.domain_name,
            "app_id": r.app_id, "app_name": r.app_name, "app_version": r.app_version,
            "install_path": r.install_path, "vdns": r.vdns, "admin_url": r.admin_url,
            "status": r.status, "installed_at": r.installed_at, "updated_at": r.updated_at,
        }
        for r in rows
    ]


@router.get("/installed/{domain}")
async def list_installed(domain: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db_dep)):
    """List installed apps for a domain — DB-backed with container fallback."""
    result = await db.execute(
        select(InstalledApp)
        .where(InstalledApp.domain_name == domain, InstalledApp.status != "removed")
        .order_by(InstalledApp.installed_at.desc())
    )
    db_rows = result.scalars().all()
    if db_rows:
        return {
            "apps": [
                {
                    "app_id": r.app_id, "name": r.app_name, "version": r.app_version,
                    "path": r.install_path, "vdns": r.vdns, "admin_url": r.admin_url,
                    "status": r.status, "installed_at": str(r.installed_at),
                }
                for r in db_rows
            ]
        }
    # Fall back to container API for legacy installs not yet in DB
    url = _container_api_url(domain, "/install/list")
    async with panel_client(verify=_TLS_VERIFY, timeout=TIMEOUT) as c:
        try:
            r = await c.get(url, headers={"Authorization": f"Bearer {_get_token(domain)}"})
            return r.json()
        except Exception:
            return {"apps": []}


class InstallRequest(BaseModel):
    domain:      str
    app_id:      str
    install_path: str = Field(default="/")
    site_title:  str = Field(default="My Site")
    admin_user:  str = Field(default="admin")
    admin_pass:  str = Field(default="")
    admin_email: str = Field(default="")
    db_name:     Optional[str] = None
    db_user:     Optional[str] = None
    db_pass:     Optional[str] = None


@router.post("/install")
async def start_install(req: InstallRequest, user=Depends(get_current_user), db: AsyncSession = Depends(get_db_dep)):
    if req.app_id not in APP_CATALOG:
        raise HTTPException(400, f"Unknown app: {req.app_id}")

    app = APP_CATALOG[req.app_id]

    # Auto-generate credentials if not supplied
    safe_name = req.domain.replace(".", "_").replace("-", "_")[:16]
    db_name = req.db_name or f"{safe_name}_{req.app_id[:4]}"
    db_user = req.db_user or f"{safe_name[:10]}_{req.app_id[:3]}"
    db_pass = req.db_pass or _rand_pass(24)
    admin_pass = req.admin_pass or _rand_pass(16)

    payload = {
        "app_id": req.app_id,
        "config": {
            "site_title":   req.site_title,
            "admin_user":   req.admin_user,
            "admin_pass":   admin_pass,
            "admin_email":  req.admin_email or f"admin@{req.domain}",
            "db_name":      db_name,
            "db_user":      db_user,
            "db_pass":      db_pass,
            "install_path": req.install_path,
        },
    }

    url = _container_api_url(req.domain, "/install")
    async with panel_client(verify=_TLS_VERIFY, timeout=TIMEOUT) as c:
        try:
            r = await c.post(url, json=payload,
                             headers={"Authorization": f"Bearer {_get_token(req.domain)}"})
            r.raise_for_status()
            data = r.json()
            # Register a virtual subdomain in PowerDNS so the service is
            # accessible as {app_id}.{domain} from outside the server.
            vdns_host = await register_vdns(req.domain, req.app_id)
            vdns_url  = f"https://{vdns_host}"

            # Persist installation record to DB (upsert: remove old, insert new)
            try:
                await db.execute(
                    delete(InstalledApp).where(
                        InstalledApp.domain_name == req.domain,
                        InstalledApp.app_id == req.app_id,
                    )
                )
                record = InstalledApp(
                    owner_id     = user.id,
                    domain_name  = req.domain,
                    app_id       = req.app_id,
                    app_name     = app.get("name", req.app_id),
                    app_version  = app.get("version"),
                    install_path = req.install_path,
                    vdns         = vdns_url,
                    admin_url    = data.get("result", {}).get("admin_url") if isinstance(data.get("result"), dict) else None,
                    status       = "installed",
                )
                db.add(record)
                await db.commit()
                import asyncio as _asyncio
                _asyncio.create_task(notify_push(
                    db,
                    type    = "app_installed",
                    title   = f"App installed: {app.get('name', req.app_id)} on {req.domain}",
                    message = f"'{app.get('name', req.app_id)}' was installed on {req.domain} by {user.username}.",
                    details = {
                        "App":     app.get("name", req.app_id),
                        "Domain":  req.domain,
                        "Path":    req.install_path or "/",
                        "URL":     vdns_url,
                        "By":      user.username,
                    },
                ))
            except Exception:
                await db.rollback()

            # Return job_id plus the generated credentials so the frontend can display them
            return {
                **data,
                "vdns":      vdns_url,
                "vdns_host": vdns_host,
                "generated": {
                    "db_name":    db_name,
                    "db_user":    db_user,
                    "db_pass":    db_pass,
                    "admin_pass": admin_pass,
                },
            }
        except httpx.HTTPStatusError as e:
            raise HTTPException(502, f"Container error: {e.response.text}")
        except Exception as e:
            raise HTTPException(502, f"Container unreachable: {e}")


@router.get("/install/status/{domain}/{job_id}")
async def install_status(domain: str, job_id: str, _user=Depends(get_current_user)):
    url = _container_api_url(domain, f"/install/status/{job_id}")
    async with panel_client(verify=_TLS_VERIFY, timeout=TIMEOUT) as c:
        try:
            r = await c.get(url, headers={"Authorization": f"Bearer {_get_token(domain)}"})
            return r.json()
        except Exception as e:
            raise HTTPException(502, str(e))


@router.delete("/installed/{domain}/{app_id}")
async def remove_app(domain: str, app_id: str, _user=Depends(get_current_user), db: AsyncSession = Depends(get_db_dep)):
    """Remove an installed app from the domain container."""
    url = _container_api_url(domain, f"/install/{app_id}")
    async with panel_client(verify=_TLS_VERIFY, timeout=TIMEOUT) as c:
        try:
            r = await c.delete(url, headers={"Authorization": f"Bearer {_get_token(domain)}"})
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, e.response.text)
        except Exception as e:
            raise HTTPException(502, str(e))
    # Mark as removed in DB
    result = await db.execute(
        select(InstalledApp).where(InstalledApp.domain_name == domain, InstalledApp.app_id == app_id)
    )
    row = result.scalar_one_or_none()
    if row:
        row.status = "removed"
        row.updated_at = datetime.utcnow()
        await db.commit()
    return {"ok": True}


@router.post("/installed/{domain}/{app_id}/repair")
async def repair_app(domain: str, app_id: str, _user=Depends(get_current_user)):
    """Repair (re-configure) an installed app without wiping data."""
    url = _container_api_url(domain, f"/install/{app_id}/repair")
    async with panel_client(verify=_TLS_VERIFY, timeout=TIMEOUT) as c:
        try:
            r = await c.post(url, headers={"Authorization": f"Bearer {_get_token(domain)}"})
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, e.response.text)
        except Exception as e:
            raise HTTPException(502, str(e))


@router.post("/installed/{domain}/{app_id}/reset")
async def reset_app(domain: str, app_id: str, _user=Depends(get_current_user)):
    """Reset an installed app — wipes all app data and reinstalls from scratch."""
    url = _container_api_url(domain, f"/install/{app_id}/reset")
    async with panel_client(verify=_TLS_VERIFY, timeout=TIMEOUT) as c:
        try:
            r = await c.post(url, headers={"Authorization": f"Bearer {_get_token(domain)}"})
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, e.response.text)
        except Exception as e:
            raise HTTPException(502, str(e))


# ── Config templates catalog ──────────────────────────────────────────────────

CONFIG_TEMPLATES = {
    "nginx_wordpress": {
        "id": "nginx_wordpress", "category": "nginx", "name": "WordPress",
        "description": "Optimised nginx config for WordPress — pretty permalinks, static asset caching, xmlrpc.php blocked, PHP-FPM integration.",
        "applies_to": "nginx",
        "content": """server {
    listen 80;
    root /var/www/html;
    index index.php index.html;
    client_max_body_size 64M;

    location / {
        try_files $uri $uri/ /index.php?$args;
    }

    location ~ \\.php$ {
        fastcgi_pass unix:/run/php/php-fpm.sock;
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
        include fastcgi_params;
        fastcgi_read_timeout 300;
    }

    location ~* \\.(css|gif|ico|jpeg|jpg|js|png|svg|webp|woff2?)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    location ~ /\\.(ht|git|env) { deny all; }
    location = /xmlrpc.php { deny all; }
    location = /wp-cron.php { deny all; }
}""",
    },
    "nginx_laravel": {
        "id": "nginx_laravel", "category": "nginx", "name": "Laravel / Symfony",
        "description": "nginx config for Laravel or Symfony — routes everything through public/index.php, correct PHP-FPM setup, dot-file protection.",
        "applies_to": "nginx",
        "content": """server {
    listen 80;
    root /var/www/html/public;
    index index.php index.html;
    client_max_body_size 32M;

    location / {
        try_files $uri $uri/ /index.php?$query_string;
    }

    location ~ \\.php$ {
        fastcgi_pass unix:/run/php/php-fpm.sock;
        fastcgi_param SCRIPT_FILENAME $realpath_root$fastcgi_script_name;
        include fastcgi_params;
        fastcgi_hide_header X-Powered-By;
        fastcgi_read_timeout 60;
    }

    location ~ /\\. { deny all; }
}""",
    },
    "nginx_static": {
        "id": "nginx_static", "category": "nginx", "name": "Static Site",
        "description": "Clean nginx config for a static HTML/CSS/JS site — aggressive caching, gzip, proper 404 handling.",
        "applies_to": "nginx",
        "content": """server {
    listen 80;
    root /var/www/html;
    index index.html;

    gzip on;
    gzip_types text/plain text/css text/javascript application/javascript application/json image/svg+xml;
    gzip_min_length 256;

    location / {
        try_files $uri $uri/ $uri.html =404;
    }

    location ~* \\.(css|js|png|jpg|jpeg|gif|ico|svg|woff2?)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    error_page 404 /404.html;
}""",
    },
    "nginx_spa": {
        "id": "nginx_spa", "category": "nginx", "name": "Single Page App (React/Vue/Angular)",
        "description": "SPA routing — all requests fall back to index.html so client-side routing works correctly.",
        "applies_to": "nginx",
        "content": """server {
    listen 80;
    root /var/www/html;
    index index.html;

    gzip on;
    gzip_types text/plain text/css application/javascript application/json;

    location / {
        try_files $uri /index.html;
    }

    location ~* \\.(js|css|png|jpg|jpeg|gif|ico|svg|woff2?)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
    }
}""",
    },
    "nginx_nodejs": {
        "id": "nginx_nodejs", "category": "nginx", "name": "Node.js App (Reverse Proxy)",
        "description": "Proxies requests to a Node.js process running on port 3000. Includes WebSocket support and sensible timeouts.",
        "applies_to": "nginx",
        "content": """upstream nodejs {
    server 127.0.0.1:3000;
    keepalive 32;
}

server {
    listen 80;

    location / {
        proxy_pass http://nodejs;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
        proxy_buffering off;
    }
}""",
    },
    "nginx_python": {
        "id": "nginx_python", "category": "nginx", "name": "Python / Gunicorn (WSGI)",
        "description": "Reverse proxy to a Python WSGI app (Django/Flask) running via Gunicorn on port 8000.",
        "applies_to": "nginx",
        "content": """upstream gunicorn {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    client_max_body_size 20M;

    location / {
        proxy_pass http://gunicorn;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    location /static/ {
        alias /var/www/html/staticfiles/;
        expires 1y;
        access_log off;
    }

    location /media/ {
        alias /var/www/html/media/;
    }
}""",
    },
    "nginx_high_security": {
        "id": "nginx_high_security", "category": "nginx", "name": "High Security",
        "description": "Hardened nginx config — strict CSP, HSTS preload, X-Frame-Options, no server tokens, rate limiting.",
        "applies_to": "nginx",
        "content": """limit_req_zone $binary_remote_addr zone=req_limit:10m rate=30r/m;

server {
    listen 80;
    root /var/www/html;
    index index.php index.html;
    server_tokens off;
    client_max_body_size 16M;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:;" always;
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;

    limit_req zone=req_limit burst=20 nodelay;

    location / {
        try_files $uri $uri/ /index.php?$args;
    }

    location ~ \\.php$ {
        fastcgi_pass unix:/run/php/php-fpm.sock;
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
        include fastcgi_params;
    }

    location ~ /\\. { deny all; }
    location ~* \\.(sh|sql|bak|log|env|ini|cfg)$ { deny all; }
}""",
    },
    # PHP templates
    "php_wordpress": {
        "id": "php_wordpress", "category": "php", "name": "WordPress Optimised",
        "description": "PHP settings tuned for WordPress — generous memory, large uploads, longer execution for WP-Cron and admin operations.",
        "applies_to": "php",
        "content": """; WordPress Optimised PHP settings
memory_limit = 256M
upload_max_filesize = 64M
post_max_size = 64M
max_execution_time = 300
max_input_vars = 10000
max_input_time = 120
date.timezone = UTC
""",
    },
    "php_high_memory": {
        "id": "php_high_memory", "category": "php", "name": "High Memory",
        "description": "512 MB memory limit for PHP-hungry applications like Magento, complex Drupal installs, or data-intensive scripts.",
        "applies_to": "php",
        "content": """; High Memory PHP settings
memory_limit = 512M
upload_max_filesize = 128M
post_max_size = 128M
max_execution_time = 600
max_input_vars = 20000
realpath_cache_size = 4096K
realpath_cache_ttl = 600
opcache.enable = 1
opcache.memory_consumption = 256
opcache.max_accelerated_files = 20000
""",
    },
    "php_debug": {
        "id": "php_debug", "category": "php", "name": "Debug Mode",
        "description": "Full error reporting enabled — shows all warnings and notices. Use only in development, never in production.",
        "applies_to": "php",
        "content": """; Debug / Development PHP settings
error_reporting = E_ALL
display_errors = On
display_startup_errors = On
log_errors = On
error_log = /var/log/php_errors.log
memory_limit = 256M
max_execution_time = 0
""",
    },
    "php_ecommerce": {
        "id": "php_ecommerce", "category": "php", "name": "E-commerce",
        "description": "Long session lifetime, extended execution time, and large upload support — ideal for WooCommerce, PrestaShop, and OpenCart.",
        "applies_to": "php",
        "content": """; E-commerce PHP settings
memory_limit = 512M
upload_max_filesize = 128M
post_max_size = 128M
max_execution_time = 600
max_input_time = 600
session.gc_maxlifetime = 7200
session.cookie_httponly = 1
session.cookie_secure = 1
opcache.enable = 1
opcache.memory_consumption = 256
""",
    },
    "php_secure": {
        "id": "php_secure", "category": "php", "name": "Hardened / Secure",
        "description": "Disables dangerous functions, hides PHP version, enables strict session security. Recommended for production.",
        "applies_to": "php",
        "content": """; Hardened PHP settings
expose_php = Off
disable_functions = exec,passthru,shell_exec,system,proc_open,popen,curl_exec,curl_multi_exec,parse_ini_file,show_source
allow_url_fopen = Off
allow_url_include = Off
session.cookie_httponly = 1
session.cookie_secure = 1
session.cookie_samesite = Strict
session.use_strict_mode = 1
memory_limit = 256M
upload_max_filesize = 32M
post_max_size = 32M
""",
    },
}

@router.get("/templates")
async def list_templates(_user=Depends(get_current_user)):
    return CONFIG_TEMPLATES


class ApplyTemplateRequest(BaseModel):
    domain: str
    template_id: str
    config_name: str = Field(default="template")  # name for nginx fragment


@router.post("/templates/apply")
async def apply_template(req: ApplyTemplateRequest, user=Depends(get_current_user)):
    tmpl = CONFIG_TEMPLATES.get(req.template_id)
    if not tmpl:
        raise HTTPException(400, f"Unknown template: {req.template_id}")

    applies_to = tmpl["applies_to"]

    if applies_to == "nginx":
        endpoint = "/secure/nginx"
        payload = {"name": req.config_name or "template", "content": tmpl["content"]}
    elif applies_to == "php":
        endpoint = "/secure/php"
        payload = {"content": tmpl["content"]}
    else:
        raise HTTPException(400, f"Unknown applies_to: {applies_to}")

    url = _container_api_url(req.domain, endpoint)
    async with panel_client(verify=_TLS_VERIFY, timeout=TIMEOUT) as c:
        try:
            r = await c.post(url, json=payload,
                             headers={"Authorization": f"Bearer {_get_token(req.domain)}"})
            r.raise_for_status()
            return {"ok": True, "applied": req.template_id}
        except httpx.HTTPStatusError as e:
            raise HTTPException(502, f"Container error: {e.response.text}")
        except Exception as e:
            raise HTTPException(502, str(e))


# ── Internal helper ───────────────────────────────────────────────────────────

def _get_token(domain: str) -> str:
    """Retrieve the container API token for a domain."""
    import os, pathlib
    token_file = pathlib.Path(f"/var/tokens/{domain}.token")
    if token_file.exists():
        return token_file.read_text().strip()
    return os.environ.get("CONTAINER_API_TOKEN", "")


# ══════════════════════════════════════════════════════════════════════════════
# ── Panel-side Marketplace App Cache ─────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
#
# Archives are stored at /var/webpanel/app-cache/ on the panel host and
# bind-mounted read-only into every site container at /var/cache/gnukontrolr/apps.
# The container_api.py _download_cached() checks that path first, so containers
# install from the local cache without touching the internet.
#
# Layout:
#   /var/webpanel/app-cache/
#     manifest.json                 — {app_id: [{version, filename, size, cached_at}]}
#     wordpress.tar.gz              — the LATEST version (always present, ready to use)
#     wordpress-6.3.tar.gz          — older version (kept until pruned)
#     wordpress-6.4.tar.gz
#     joomla.tar.gz
#     ...
#
# Up to APP_CACHE_KEEP_VERSIONS older archives are kept per app.
# ─────────────────────────────────────────────────────────────────────────────

APP_CACHE_DIR           = Path("/var/webpanel/app-cache")
APP_CACHE_KEEP_VERSIONS = 3   # keep this many old versions per app

# Maps app_id → (download_url, canonical_filename)
# Mirrors APP_DOWNLOADS in container_api.py — this is the panel-side copy.
_APP_DOWNLOADS = {
    "wordpress":   ("https://wordpress.org/latest.tar.gz",                                                "wordpress.tar.gz"),
    "joomla":      ("https://downloads.joomla.org/cms/joomla5/latest/Joomla_latest-Stable-Full_Package.tar.gz", "joomla.tar.gz"),
    "drupal":      ("https://www.drupal.org/download-latest/tar.gz",                                       "drupal.tar.gz"),
    "grav":        ("https://getgrav.org/download/core/grav/latest",                                       "grav.zip"),
    "roundcube":   ("https://github.com/roundcube/roundcubemail/releases/download/1.6.9/roundcubemail-1.6.9-complete.tar.gz", "roundcube.tar.gz"),
    "snappymail":  ("https://github.com/the-djmaze/snappymail/releases/download/v2.38.2/snappymail-2.38.2.tar.gz", "snappymail.tar.gz"),
    "phpmyadmin":  ("https://files.phpmyadmin.net/phpMyAdmin/5.2.2/phpMyAdmin-5.2.2-all-languages.tar.gz",  "phpmyadmin.tar.gz"),
    "adminer":     ("https://github.com/vrana/adminer/releases/download/v4.8.1/adminer-4.8.1.php",         "adminer.php"),
    "ghost":       ("https://github.com/TryGhost/Ghost/releases/download/v5.82.2/Ghost-5.82.2.zip",        "ghost.zip"),
    "october":     ("https://github.com/octobercms/october/archive/refs/tags/v3.5.30.tar.gz",              "october.tar.gz"),
    "matomo":      ("https://builds.matomo.org/matomo-5.0.3.zip",                                          "matomo.zip"),
    "nextcloud":   ("https://download.nextcloud.com/server/releases/nextcloud-28.0.3.tar.bz2",             "nextcloud.tar.bz2"),
    "bookstack":   ("https://github.com/BookStackApp/BookStack/archive/refs/tags/v23.12.2.tar.gz",         "bookstack.tar.gz"),
    "freshrss":    ("https://github.com/FreshRSS/FreshRSS/archive/refs/tags/1.24.1.tar.gz",               "freshrss.tar.gz"),
    "wikijs":      ("https://github.com/requarks/wiki/releases/download/v2.5.303/wiki-js.tar.gz",          "wikijs.tar.gz"),
    "gitea":       ("https://dl.gitea.com/gitea/1.21.11/gitea-1.21.11-linux-amd64",                       "gitea-bin"),
    "vaultwarden": ("https://github.com/dani-garcia/vaultwarden/releases/download/1.30.5/vaultwarden-1.30.5-linux-amd64.tar.gz", "vaultwarden.tar.gz"),
    "piwigo":      ("https://piwigo.org/download/dlcounter.php?code=latest",                               "piwigo.zip"),
    "moodle":      ("https://download.moodle.org/download.php/direct/stable404/moodle-latest-404.tgz",    "moodle.tgz"),
    "prestashop":  ("https://github.com/PrestaShop/PrestaShop/releases/download/8.1.7/prestashop_8.1.7.zip", "prestashop.zip"),
    "opencart":    ("https://github.com/opencart/opencart/releases/download/4.0.2.3/opencart-4.0.2.3.tar.gz", "opencart.tar.gz"),
}

_cache_lock = threading.Lock()


def _cache_app(app_id: str) -> dict:
    """
    Download the canonical archive for app_id into APP_CACHE_DIR.
    Saves a versioned copy, writes to DB (via sync SQLAlchemy), and
    prunes old files beyond APP_CACHE_KEEP_VERSIONS. Thread-safe.
    Returns a status dict.
    """
    if app_id not in _APP_DOWNLOADS:
        return {"ok": False, "error": f"Unknown app: {app_id}"}

    url, filename = _APP_DOWNLOADS[app_id]
    dest = APP_CACHE_DIR / filename

    with _cache_lock:
        APP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = APP_CACHE_DIR / f".tmp-{filename}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "GnuKontrolR-Cache/1.0"})
            with urllib.request.urlopen(req, timeout=180) as resp, open(str(tmp), "wb") as fh:
                shutil.copyfileobj(resp, fh)
            size = tmp.stat().st_size
            shutil.move(str(tmp), str(dest))
            # Keep a versioned timestamped copy
            ts_str = str(int(time.time()))
            stem   = Path(filename).stem
            ext    = "".join(Path(filename).suffixes)
            versioned_name = f"{stem}-{ts_str}{ext}"
            versioned = APP_CACHE_DIR / versioned_name
            shutil.copy2(str(dest), str(versioned))

            # Write to DB (sync, runs inside a thread already)
            _db_record_cached(app_id, url, filename, versioned_name, size)

            return {"ok": True, "app_id": app_id, "filename": filename, "size_kb": size // 1024}
        except Exception as exc:
            tmp.unlink(missing_ok=True)
            return {"ok": False, "app_id": app_id, "error": str(exc)}


def _db_record_cached(app_id: str, url: str, canonical: str, versioned: str, size: int):
    """Write/update the DB records for a freshly cached app. Runs synchronously."""
    import asyncio
    from sqlalchemy import select as _sel, delete as _del
    from sqlalchemy.orm import Session
    from sqlalchemy import create_engine
    from app.models.app_cache import AppCacheEntry
    from app.database import DB_PATH

    engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
    now = datetime.utcnow()
    with Session(engine) as s:
        # Mark previous canonical as non-canonical
        s.query(AppCacheEntry).filter_by(app_id=app_id, is_canonical=True).update({"is_canonical": False})
        # Insert canonical entry (upsert by filename)
        existing = s.query(AppCacheEntry).filter_by(app_id=app_id, filename=canonical).first()
        if existing:
            existing.size_bytes   = size
            existing.is_canonical = True
            existing.source_url   = url
            existing.cached_at    = now
        else:
            s.add(AppCacheEntry(app_id=app_id, filename=canonical, size_bytes=size,
                                is_canonical=True, source_url=url, cached_at=now))
        # Insert versioned copy entry
        s.add(AppCacheEntry(app_id=app_id, filename=versioned, size_bytes=size,
                            is_canonical=False, source_url=url, cached_at=now))
        s.commit()

        # Prune: keep only the most recent APP_CACHE_KEEP_VERSIONS non-canonical rows per app
        old_rows = (
            s.query(AppCacheEntry)
             .filter_by(app_id=app_id, is_canonical=False)
             .order_by(AppCacheEntry.cached_at.asc())
             .all()
        )
        while len(old_rows) > APP_CACHE_KEEP_VERSIONS:
            row = old_rows.pop(0)
            f = APP_CACHE_DIR / row.filename
            f.unlink(missing_ok=True)
            s.delete(row)
        s.commit()
    engine.dispose()


# ── Cache API endpoints ────────────────────────────────────────────────────────

@router.get("/cache")
async def list_cache(db=Depends(get_db_dep), _=Depends(require_admin)):
    """List all cached marketplace archives with version history from the database."""
    from sqlalchemy import select as _sel
    from app.models.app_cache import AppCacheEntry

    rows = (await db.execute(_sel(AppCacheEntry).order_by(AppCacheEntry.app_id, AppCacheEntry.cached_at.desc()))).scalars().all()

    # Group by app_id
    by_app: dict = {}
    for row in rows:
        by_app.setdefault(row.app_id, {"canonical": None, "versions": []})
        entry = {
            "id":           row.id,
            "filename":     row.filename,
            "size_kb":      row.size_bytes // 1024,
            "cached_at":    row.cached_at.isoformat() if row.cached_at else None,
            "is_canonical": row.is_canonical,
        }
        if row.is_canonical:
            by_app[row.app_id]["canonical"] = entry
        else:
            by_app[row.app_id]["versions"].append(entry)

    result = []
    for app_id, url_filename in _APP_DOWNLOADS.items():
        _, filename = url_filename
        canonical_file = APP_CACHE_DIR / filename
        app_data = by_app.get(app_id, {"canonical": None, "versions": []})
        result.append({
            "app_id":        app_id,
            "filename":      filename,
            "cached":        canonical_file.exists(),
            "size_kb":       canonical_file.stat().st_size // 1024 if canonical_file.exists() else 0,
            "canonical":     app_data["canonical"],
            "versions":      app_data["versions"],
        })

    cached_count = sum(1 for e in result if e["cached"])
    return {"apps": result, "cached": cached_count, "total": len(result), "cache_dir": str(APP_CACHE_DIR)}


@router.post("/cache/refresh")
async def refresh_all_cache(background_tasks: BackgroundTasks, _=Depends(require_admin)):
    """
    Download/refresh the latest version of every app in the background.
    Returns immediately — large downloads may take several minutes.
    Check GET /api/marketplace/cache for progress.
    """
    def _run_all():
        for app_id in _APP_DOWNLOADS:
            _cache_app(app_id)

    background_tasks.add_task(_run_all)
    return {
        "ok":   True,
        "apps": list(_APP_DOWNLOADS.keys()),
        "note": "Downloading in background. Poll GET /api/marketplace/cache to track progress.",
    }


@router.post("/cache/refresh/{app_id}")
async def refresh_one_cache(app_id: str, _=Depends(require_admin)):
    """Download/refresh the cache for a single app (synchronous — waits for download)."""
    if app_id not in _APP_DOWNLOADS:
        raise HTTPException(404, f"Unknown app: {app_id}")
    result = _cache_app(app_id)
    if not result["ok"]:
        raise HTTPException(500, result.get("error", "Download failed"))
    return result


@router.delete("/cache/{app_id}")
async def purge_app_cache(app_id: str, db=Depends(get_db_dep), _=Depends(require_admin)):
    """Remove all cached archives for an app (files + DB rows)."""
    from sqlalchemy import select as _sel, delete as _del
    from app.models.app_cache import AppCacheEntry
    if app_id not in _APP_DOWNLOADS:
        raise HTTPException(404, f"Unknown app: {app_id}")
    _, filename = _APP_DOWNLOADS[app_id]
    removed = []
    stem = Path(filename).stem
    if APP_CACHE_DIR.exists():
        for f in APP_CACHE_DIR.iterdir():
            if f.name == filename or f.name.startswith(f"{stem}-"):
                f.unlink(missing_ok=True)
                removed.append(f.name)
    await db.execute(_del(AppCacheEntry).where(AppCacheEntry.app_id == app_id))
    await db.commit()
    return {"ok": True, "app_id": app_id, "removed": removed}
