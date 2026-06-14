#!/bin/bash
# ── GnuKontrolR Panel Entrypoint ──────────────────────────────────────────────
# Starts cron daemon, then drops to the panelapi user and execs the CMD.
set -e

echo "[entrypoint] Starting cron daemon..."
cron -f &

echo "[entrypoint] Dropping to panelapi, executing: $*"
exec su -s /bin/bash -p panelapi -c "exec $*"
