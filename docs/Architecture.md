# Architecture

## Container Overview

GnuKontrolR runs as a stack of Docker containers managed by Docker Compose.

```
                    Internet
                        │
                  ┌─────▼─────┐
                  │  Traefik   │  Reverse proxy (ports 80, 443, 8443)
                  │            │  Automatic Let's Encrypt TLS
                  └─────┬─────┘
                        │
          ┌─────────────┼─────────────┐
          │             │             │
    ┌─────▼─────┐ ┌────▼────┐ ┌─────▼─────┐
    │  WebPanel  │ │ PowerDNS│ │  Postfix  │
    │  API       │ │  (DNS)  │ │  (SMTP)   │
    │  + Frontend│ │         │ │           │
    └─────┬─────┘ └─────────┘ └─────┬─────┘
          │                         │
    ┌─────▼─────┐             ┌─────▼─────┐
    │  MySQL    │             │  Dovecot   │
    │  (sites)  │             │  (IMAP)    │
    └───────────┘             └───────────┘
```

## Service Descriptions

### Traefik (`traefik:v3.3`)
- **Role**: Reverse proxy, TLS termination, Let's Encrypt automation
- **Ports**: 80 (HTTP), 443 (HTTPS), 8443 (Panel HTTPS)
- **Config**: Dynamic config in `docker/traefik/dynamic/`
- **Features**: automatic SSL, middleware (rate limiting, IP blocking), dashboard on panel domain

### WebPanel API (`gnukontrolr-webpanel`)
- **Role**: Main application — FastAPI backend + React frontend
- **Ports**: 8000 (internal, exposed via Traefik)
- **Stack**: Python FastAPI, SQLAlchemy, JWT auth, Redis sessions
- **Terminal**: WebSocket-based browser shell (panelapi user, docker group)

### MySQL (`mysql:8.4`)
- **Role**: Primary database for customer site data
- **Storage**: `mysql_data` volume
- **Access**: Used by the panel and customer site containers

### PostgreSQL (`postgres:17-alpine`)
- **Role**: Panel metadata, audit logs, scheduled tasks
- **Storage**: `postgres_data` volume
- **Access**: Panel API only

### Redis (`redis:8-alpine`)
- **Role**: Caching, session storage, real-time updates
- **Storage**: `redis_data` volume
- **Features**: Pub/sub for SSE events

### PowerDNS (`powerdns/pdns-auth-49`)
- **Role**: Authoritative DNS server
- **Ports**: 53 (UDP/TCP), 8081 (API)
- **Storage**: `pdns_data` volume
- **Backend**: MySQL for zone/record storage

### Postfix (`boky/postfix`)
- **Role**: SMTP email delivery
- **Features**: DKIM signing, SPF, DMARC support
- **Integration**: Receives outgoing mail from customer sites

### Dovecot (`dovecot/dovecot`)
- **Role**: IMAP/POP3 email retrieval
- **Ports**: 143 (IMAP), 993 (IMAPS)

### Prometheus + Grafana
- **Role**: Monitoring and metrics
- **Prometheus**: collects container metrics, panel API metrics
- **Grafana**: dashboards for system visualisation
- **Storage**: `prometheus_data`, `grafana_data` volumes

### Docker API Proxy (`nginx:alpine`)
- **Role**: Proxies Docker API for the panel with access control
- **Access**: Internal only, used by panel to manage containers

### OpenDKIM
- **Role**: DKIM key generation and email signing
- **Integration**: Generates per-domain DKIM keys, configured via panel

### LocalDNS (`gnukontrolr-localdns`)
- **Role**: Internal DNS for service discovery and customer site resolution

## Container Networks

```
┌──────────────────────────────────────────────────┐
│                 gnukontrolr_net                   │
│  (all panel services communicate here)            │
│                                                    │
│  webpanel → mysql, postgres, redis, powerdns,      │
│             postfix, dovecot, traefik              │
│                                                    │
│  Customer containers also join this net            │
│  for inter-service routing                         │
└──────────────────────────────────────────────────┘
```

## Security Boundaries

- **Panel API container**: has Docker socket access (`docker` group) to manage customer containers
- **Customer containers**: isolated, no host access, resource-limited
- **Database containers**: internal network only, no external ports
- **Traefik**: only service exposed to the public internet
