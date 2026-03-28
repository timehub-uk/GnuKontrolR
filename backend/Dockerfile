# ── GnuKontrolR Panel API ────────────────────────────────────────────────────
# Multi-stage build:
#   frontend-builder  — Node 20, builds React SPA → /frontend/dist
#   py-builder        — compiles Python wheels
#   runtime           — slim image with both outputs baked in

# ── Stage 1: React frontend build ────────────────────────────────────────────
FROM node:20-slim AS frontend-builder

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
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS runtime

LABEL maintainer="GnuKontrolR"
LABEL description="GnuKontrolR panel API — FastAPI + uvicorn"

# Docker CLI (to manage customer containers from within the panel)
RUN apt-get update && apt-get install -y --no-install-recommends \
        docker.io curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── Non-root panel user ───────────────────────────────────────────────────────
# panelapi runs the FastAPI process. It is added to the 'docker' group so it
# can talk to the Docker socket without running as root.
RUN groupadd -r panelapi \
    && useradd -r -g panelapi -s /sbin/nologin -d /app -M panelapi \
    && usermod -aG docker panelapi

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy application source
COPY backend/app/ ./app/

# Copy built React frontend (from frontend-builder stage)
COPY --from=frontend-builder /frontend/dist ./frontend/dist/

# Persistent data directory (SQLite DB lives here — mount a volume at /app/data)
RUN mkdir -p /app/data && chown panelapi:panelapi /app/data

# Customer site files root (mount the same volume as the customer containers)
RUN mkdir -p /var/webpanel/sites && chown panelapi:panelapi /var/webpanel/sites

USER panelapi

EXPOSE 8000

# Health check — hits the OpenAPI docs endpoint
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:8000/docs > /dev/null || exit 1

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--log-level", "info", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
