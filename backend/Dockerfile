# ── GnuKontrolR Panel API ────────────────────────────────────────────────────
# Multi-stage build:
#   frontend-builder  — Node 20, builds React SPA → /frontend/dist
#   py-builder        — compiles Python wheels
#   runtime           — slim image with both outputs baked in

# ── Stage 1: React frontend build ────────────────────────────────────────────
FROM node:26-slim AS frontend-builder

WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci --silent
COPY frontend/ ./
# Create the postbuild target so the cp doesn't fail inside the Docker build
RUN mkdir -p /opt/gnukontrolr/frontend/dist && npm run build

# ── Stage 2: Python dependency builder ───────────────────────────────────────
FROM python:3.12-slim-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libffi-dev libssl-dev build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS runtime

LABEL maintainer="GnuKontrolR"
LABEL description="GnuKontrolR panel API — FastAPI + uvicorn"

# Docker CLI (to manage customer containers via docker-api-proxy)
# DOCKER_HOST env var points it at the nginx proxy instead of docker.sock
RUN apt-get update && apt-get install -y --no-install-recommends \
        docker.io curl ca-certificates default-mysql-client postgresql-client openssh-client cron sudo \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir psutil

# ── Non-root panel user ───────────────────────────────────────────────────────
# panelapi runs the FastAPI process.
# dkim group (GID 1001) shares the dkim_keys volume with the opendkim container.
RUN groupadd -r panelapi \
    && groupadd -r dkim -g 1001 \
    && useradd -r -g panelapi -s /bin/bash -d /app -M panelapi \
    && usermod -aG dkim panelapi

# Allow panelapi to update /etc/hosts for local vdns resolution via a helper
# script that only supports add/remove operations (no arbitrary commands).
COPY backend/docker/update-hosts.sh /usr/local/bin/update-hosts.sh
RUN chmod 755 /usr/local/bin/update-hosts.sh \
    && echo "panelapi ALL=(root) NOPASSWD: /usr/local/bin/update-hosts.sh" > /etc/sudoers.d/panelapi-hosts \
    && chmod 440 /etc/sudoers.d/panelapi-hosts \
    && echo "Defaults:panelapi !syslog" > /etc/sudoers.d/panelapi-nolog \
    && chmod 440 /etc/sudoers.d/panelapi-nolog

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy application source (creates /app/app/ Python package)
COPY backend/app/ ./app/

# Install CLI tool
RUN chmod +x /app/app/cli.py && ln -sf /app/app/cli.py /usr/local/bin/panel

# Copy built React frontend (from frontend-builder stage)
COPY --from=frontend-builder /frontend/dist ./frontend/dist/

# Persistent data directory (SQLite DB lives here — mount a volume at /app/data)
RUN mkdir -p /app/data && chown panelapi:panelapi /app/data

# Create a proper .bashrc for interactive shells (docker exec)
RUN echo 'export PS1="\u@\h:\w\$ "' > /app/.bashrc && chown panelapi:panelapi /app/.bashrc

# Customer site files root (mount the same volume as the customer containers)
RUN mkdir -p /var/webpanel/sites && chown panelapi:panelapi /var/webpanel/sites

# Secondary services installation directory
RUN mkdir -p /var/webpanel/services && chown panelapi:panelapi /var/webpanel/services

# DKIM keys dir — panelapi generates and writes DKIM keypairs here.
# The dkim_keys volume is bind-mounted at runtime; we create the path so the
# chown is reflected in the image layer used as the volume initialiser.
RUN mkdir -p /etc/opendkim/keys && chown -R panelapi:panelapi /etc/opendkim/keys

# Entrypoint — starts cron as root, then drops to panelapi
COPY backend/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

USER root
WORKDIR /app

ENTRYPOINT ["/docker-entrypoint.sh"]

EXPOSE 8000

# Health check — hits /health
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:8000/health > /dev/null || exit 1

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--log-level", "info", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "172.30.0.0/16"]
