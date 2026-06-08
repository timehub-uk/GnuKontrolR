# GnuKontrolR — Web Hosting Panel

GnuKontrolR is an open-source web hosting control panel built on Docker. It provides a complete hosting environment with a modern web UI, DNS management, email services, SSL certificate management, and container-based isolation for customer sites.

## Features

- **Containerised Sites** — each customer site runs in its own Docker container with isolated PHP, nginx, and filesystem
- **DNS Management** — integrated PowerDNS with full zone and record management
- **Email Services** — Postfix (SMTP) + Dovecot (IMAP/POP3) with DKIM signing
- **SSL/TLS** — automated Let's Encrypt via Traefik, custom certificate upload
- **Fail2ban** — integrated intrusion prevention with geo-blocking
- **CVE Feed** — built-in vulnerability feed from NVD and CVE.org
- **Monitoring** — Prometheus + Grafana stack, container-level metrics
- **CLI Tool** — full administration via `panel` command inside the WebPanel Terminal
- **PHP** — multiple PHP version support with configurable `php.ini`
- **WebPanel Terminal** — browser-based SSH-like terminal into the admin container
- **Database Management** — MySQL/MariaDB for customer sites, PostgreSQL for panel data, Redis for caching

## Quick Start

```bash
git clone https://github.com/timehub-uk/GnuKontrolR.git
cd GnuKontrolR
sudo bash setup.sh install
```

Follow the prompts to configure your domain, IP, and create the admin account. Access the panel at `https://your-domain:8443`.

## Architecture Overview

```
┌──────────────┐  ┌──────────┐  ┌───────────┐
│   Traefik    │  │ PowerDNS │  │  Postfix  │
│  (Reverse    │  │  (DNS)   │  │  (SMTP)   │
│   Proxy)     │  │          │  │           │
└──────┬───────┘  └──────────┘  └─────┬─────┘
       │                              │
┌──────▼──────────────────────────────▼──────┐
│              WebPanel API                   │
│    FastAPI + SQLAlchemy + JWT Auth          │
├─────────────────────────────────────────────┤
│  MySQL  │  PostgreSQL  │  Redis  │  Prometheus │
└─────────────────────────────────────────────┘
```

See [Architecture](Architecture) for detailed service descriptions.
