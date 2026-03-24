# GnuKontrolR

A self-hosted, multi-domain web hosting control panel — faster and lighter than Plesk.
Built with FastAPI + React + Docker. Every site runs in its own isolated container.

![License](https://img.shields.io/badge/license-MIT-blue) ![Docker](https://img.shields.io/badge/docker-required-blue) ![Python](https://img.shields.io/badge/python-3.12+-green) ![React](https://img.shields.io/badge/react-18-blue)

---

## Features

| Area | Details |
|---|---|
| **Domains** | Add/remove domains, subdomains, redirects, addon domains |
| **DNS** | PowerDNS authoritative server, A/CNAME/MX/TXT/SRV records |
| **SSL** | Let's Encrypt via Traefik, auto-renew, HSTS |
| **Docker** | Per-domain isolated site containers (PHP-FPM, Nginx/Apache/Lighttpd) |
| **Marketplace** | One-click installers — WordPress, Laravel, Django, Ghost, Nextcloud, n8n, Gitea, and 25+ more |
| **SFTP** | Ed25519 key-pair per domain, SSH-only chroot access |
| **Email** | Postfix outbound SMTP + Dovecot IMAP/POP3 |
| **Databases** | MySQL per-domain isolated schemas, SQLite inside containers |
| **Files** | In-browser file manager + syntax-highlighted viewer |
| **Terminal** | Browser-based SSH terminal (WebSocket) |
| **Backups** | Rolling config snapshots (Nginx/PHP/SSL/env) with one-click restore |
| **Security** | Live security advisor, auto-fix headers, SSL audit, open-port scanner |
| **Activity Log** | Per-user request history, IP hashing, UUID event IDs for tracing |
| **Monitoring** | Prometheus + Grafana dashboards (CPU, memory, disk, per-container stats) |
| **Users** | Multi-tier roles: superadmin / admin / reseller / user |
| **Admin Content** | Superadmin file browser with PIN-protected access |

---

## Quick Install

```bash
curl -sSL https://raw.githubusercontent.com/timehub-uk/GnuKontrolR/master/get.sh | sudo bash
```

> Requires a fresh **Ubuntu 22.04+** or **Debian 12+** VPS/server with ports 80, 443, 53 open.

The installer will:
1. Install Docker + Docker Compose (if missing)
2. Clone the repo to `/opt/gnukontrolr`
3. Prompt for your panel domain, mail hostname, Let's Encrypt email, and timezone
4. Generate a secure `.env` with random secrets
5. Build the React frontend
6. Start all Docker services
7. Prompt to create the superadmin account

---

## Manual Install

```bash
# 1. Clone
git clone https://github.com/timehub-uk/GnuKontrolR.git /opt/gnukontrolr
cd /opt/gnukontrolr

# 2. Configure
cp .env.example .env
nano .env          # fill in your domain, secrets, and email

# 3. Build frontend (requires Node.js 18+)
cd frontend && npm ci && npm run build && cd ..

# 4. Start all services
docker compose up -d --build

# 5. Create the superadmin account
bash setup.sh add-user
```

---

## Stack

```
Traefik          — reverse proxy + automatic Let's Encrypt SSL
PowerDNS         — authoritative DNS server (SQLite backend)
MySQL 8          — customer databases (per-domain isolated schemas)
Redis 7          — shared cache, session store
Postfix          — outbound SMTP relay
Dovecot          — IMAP / POP3 mail delivery
FastAPI          — control panel REST API (Python 3.12)
React 18         — frontend SPA (Vite + Tailwind CSS)
Prometheus       — metrics scraper (host + containers)
Grafana          — live dashboards
Node Exporter    — host-level metrics
cAdvisor         — per-container metrics
```

Each customer site runs in a dedicated container (`webpanel/php-site:8.2`) with:
- PHP-FPM 8.2 + choice of Nginx / Apache / Lighttpd
- Node.js 20 + PM2 (optional)
- Composer, WP-CLI pre-installed
- SSH/SFTP chroot (unique port per domain, loopback-only)
- Internal container API (port 9000, TLS, token-auth) for config management

---

## Management

```bash
bash setup.sh start           # start all services
bash setup.sh stop            # stop all services
bash setup.sh restart         # restart all services
bash setup.sh status          # show container status
bash setup.sh logs            # tail all logs
bash setup.sh logs webpanel   # tail one service's logs
bash setup.sh update          # pull latest code + rebuild
bash setup.sh backup          # dump MySQL + .env to backups/
bash setup.sh restore         # restore from a backup
bash setup.sh reset-pass      # reset a user's password
bash setup.sh add-user        # add a panel user (prompts for role)
bash setup.sh uninstall       # remove containers (data volumes kept)
```

---

## Ports

| Port | Service | Notes |
|---|---|---|
| 80 | HTTP | Traefik — redirects to HTTPS |
| 443 | HTTPS | Traefik — all customer domains + panel |
| 53 | DNS | PowerDNS |
| 25 | SMTP | Postfix (outbound relay) |
| 587 | Submission | Postfix (authenticated mail) |
| 143 | IMAP | Dovecot |
| 993 | IMAPS | Dovecot (TLS) |
| 110 | POP3 | Dovecot |
| 995 | POP3S | Dovecot (TLS) |
| 8000 | Panel API | Internal only (Traefik proxy) |
| 3000 | Grafana | Internal only (Traefik proxy) |
| 10200–14999 | SSH/SFTP | Per-domain, loopback-bound |

---

## Directory Structure

```
GnuKontrolR/
├── get.sh                   One-command installer (curl | sudo bash)
├── setup.sh                 Management helper (start/stop/update/backup…)
├── docker-compose.yml       Full service stack definition
├── .env.example             Environment variable template
│
├── backend/                 FastAPI application (Python 3.12)
│   ├── Dockerfile           Multi-stage build → slim runtime image
│   ├── requirements.txt     Python dependencies (pinned versions)
│   └── app/
│       ├── main.py          App entry point, middleware, Prometheus metrics
│       ├── auth.py          JWT tokens, password hashing, role guards
│       ├── database.py      SQLAlchemy async engine + session factory
│       ├── cache.py         Redis cache layer with graceful fallback
│       ├── models/          SQLAlchemy ORM models
│       │   ├── user.py      User + Role enum
│       │   ├── domain.py    Domain + DomainType/Status enums
│       │   ├── container_port.py  Persistent port allocations
│       │   └── request_log.py     Per-user activity log entries
│       └── routers/         API route handlers (one file per feature)
│           ├── auth.py      /api/auth — login, register, /me
│           ├── users.py     /api/users — CRUD (admin+)
│           ├── domains.py   /api/domains — domain management
│           ├── docker_mgr.py /api/docker — container lifecycle
│           ├── services.py  /api/services — marketplace / per-container services
│           ├── server.py    /api/server — stats, service control, WS live feed
│           ├── security.py  /api/security — advisor, auto-fix, WS stream
│           ├── activity_log.py /api/log — per-user request history
│           ├── container_proxy.py /api/container — proxy to container API
│           ├── admin_content.py /api/admin/content — PIN-protected file viewer
│           └── marketplace.py /api/marketplace — one-click app catalogue
│
├── frontend/                React 18 SPA (Vite + Tailwind CSS)
│   ├── src/
│   │   ├── pages/           Full-page views (one per panel section)
│   │   ├── components/      Shared UI components
│   │   ├── hooks/           Custom React hooks (live validation, debounce…)
│   │   ├── utils/
│   │   │   ├── api.js       Axios instance with UUID event ID tracing
│   │   │   ├── ws.js        WebSocket helper
│   │   │   └── pageCache.js Client-side page cache
│   │   └── context/         AuthContext — token storage + user state
│   ├── vite.config.js       Dev proxy → localhost:8000
│   └── tailwind.config.js
│
└── docker/                  Per-service configuration
    ├── traefik/             traefik.yml — routing, ACME, entrypoints
    ├── site-template/       Per-domain customer container
    │   ├── Dockerfile       PHP 8.2 + Nginx/Apache/Lighttpd + Node.js + SSH
    │   ├── entrypoint.sh    Container bootstrap (SSH keys, TLS cert, env setup)
    │   ├── container_api.py Flask API on port 9000 (TLS, token-auth)
    │   └── conf/            Service config templates
    ├── mysql/               init.sql — schema bootstrap
    ├── powerdns/            pdns.conf
    ├── postfix/             Configured via environment variables
    ├── dovecot/             Configured via environment variables
    ├── prometheus/          prometheus.yml — scrape targets
    └── grafana/             Dashboard + datasource provisioning
```

---

## Security Model

- **TLS everywhere**: Traefik terminates HTTPS for all public traffic. Container-to-container API traffic uses per-container self-signed certs (TLS + shared Bearer token).
- **Isolation**: Each domain runs in its own Docker container. Containers share no filesystem, process space, or secrets.
- **Non-root**: Both the panel API (`panelapi` user) and container API (`gnukontrolr-admin`) run as unprivileged users.
- **SFTP chroot**: SSH/SFTP access is locked to the domain's `public_html` and `uploads` directories only — `/var/config` (secrets area) is never visible.
- **Admin content PIN**: Superadmin file browsing requires a separate 6-digit PIN and issues a 15-minute scoped JWT.
- **Rate limiting**: Container API enforces 60 req/min per IP. Panel API login is protected by FastAPI's standard auth flow.

---

## License

MIT
