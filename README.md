# GnuKontrolR

A multi-domain, multi-user web hosting control panel built with FastAPI + React.

![License](https://img.shields.io/badge/license-MIT-blue) ![Docker](https://img.shields.io/badge/docker-required-blue) ![Python](https://img.shields.io/badge/python-3.11+-green) ![React](https://img.shields.io/badge/react-18-blue)

---

## Features

| Area | Details |
|---|---|
| **Domains** | Add/remove domains, Nginx vhost management |
| **DNS** | PowerDNS authoritative server, A/CNAME/MX/TXT records |
| **SSL** | Let's Encrypt via Traefik, auto-renew |
| **Docker** | Per-domain site containers, start/stop/rebuild |
| **Marketplace** | One-click installers — WordPress, Ghost, Nextcloud, n8n, Gitea, and 25+ more |
| **SFTP** | Ed25519 key-pair generation per domain, per-client instructions |
| **Email** | Postfix + Dovecot, SMTP/IMAP/POP3 |
| **Databases** | MySQL per-domain isolated schemas |
| **Files** | In-browser file manager per domain |
| **Terminal** | Browser-based SSH terminal |
| **Backups** | Rolling config snapshots (Nginx/PHP/SSL/env) with one-click restore |
| **Security** | Firewall rules, fail2ban, SSL audit, login hardening advisor |
| **Activity Log** | Per-user request history with IP hashing and event IDs |
| **Monitoring** | Prometheus + Grafana dashboards (CPU, memory, disk, containers) |
| **Users** | Multi-user with admin/user roles |

---

## Quick Install

```bash
curl -sSL https://raw.githubusercontent.com/timehub-uk/GnuKontrolR/master/install.sh | sudo bash
```

Requires a fresh Ubuntu 22.04+ or Debian 12+ server with ports 80, 443, 53 open.

---

## Manual Install

```bash
# 1. Clone
git clone https://github.com/timehub-uk/GnuKontrolR.git /opt/gnukontrolr
cd /opt/gnukontrolr

# 2. Configure
cp .env.example .env
nano .env          # fill in your domain, secrets, email

# 3. Build frontend
cd frontend && npm ci && npm run build && cd ..

# 4. Start
docker compose up -d --build

# 5. Create admin user
bash setup.sh add-user
```

---

## Stack

```
Traefik          — reverse proxy + Let's Encrypt SSL
PowerDNS         — authoritative DNS
MySQL 8          — databases
Redis 7          — cache / sessions
Postfix          — outbound SMTP
Dovecot          — IMAP / POP3
FastAPI          — control panel API (Python 3.11)
React 18         — frontend (Vite + Tailwind CSS)
Prometheus       — metrics
Grafana          — dashboards
```

---

## Management

```bash
bash setup.sh start        # start all services
bash setup.sh stop         # stop all services
bash setup.sh status       # container status
bash setup.sh logs         # tail all logs
bash setup.sh logs webpanel  # tail one service
bash setup.sh update       # pull latest + rebuild
bash setup.sh backup       # dump databases to backups/
bash setup.sh reset-pass   # reset a user password
bash setup.sh add-user     # add a panel user
bash setup.sh uninstall    # remove containers (data kept)
```

---

## Ports

| Port | Service |
|---|---|
| 80 / 443 | HTTP / HTTPS (Traefik) |
| 53 | DNS (PowerDNS) |
| 25 / 587 | SMTP (Postfix) |
| 143 / 993 | IMAP / IMAPS (Dovecot) |
| 110 / 995 | POP3 / POP3S (Dovecot) |
| 8000 | Panel API (internal) |
| 3000 | Grafana (internal) |

---

## Directory Structure

```
GnuKontrolR/
├── backend/             FastAPI application
│   ├── app/
│   │   ├── routers/     API route handlers
│   │   ├── models/      SQLAlchemy models
│   │   ├── auth.py      JWT authentication
│   │   └── main.py      App entry point
│   └── Dockerfile
├── frontend/            React + Vite + Tailwind
│   └── src/
│       ├── pages/       One component per page
│       ├── components/  Shared UI components
│       ├── hooks/       Custom React hooks
│       └── utils/       API client, cache, websocket
├── docker/              Service configs
│   ├── traefik/
│   ├── site-template/   Per-domain container image
│   ├── mysql/
│   ├── powerdns/
│   ├── prometheus/
│   └── grafana/
├── docker-compose.yml
├── install.sh           One-command installer
├── setup.sh             Management helper
└── .env.example         Environment template
```

---

## License

MIT
