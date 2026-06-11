#!/usr/bin/env bash
# ── GnuKontrolR Security Matrix — write-secrets-manifest.sh ───────────────────
# Generates / updates secrets.json inside the vault.
# This manifest maps every secret file to its purpose, owner service, and
# canonical path — so the panel API and setup wizard know the correct UUID
# and can resolve secret paths without hardcoding.
#
# Usage:
#   bash write-secrets-manifest.sh
#   bash write-secrets-manifest.sh --verify   # validate existing manifest
#
# Called automatically by secrets-init.sh and setup.sh.
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/secrets-lib.sh"

VAULT=$(get_vault_path 2>/dev/null) || { warn "Vault not initialised — run secrets-init.sh first"; exit 1; }
UUID=$(get_install_uuid)

# ── Build manifest ───────────────────────────────────────────────────────────
build_manifest() {
    local manifest
    manifest=$(cat <<JSON
{
  "version": "${SECRETS_SCHEMA_VERSION}",
  "updated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "install_uuid": "${UUID}",
  "vault_root": "${VAULT}",
  "services": {
    "webpanel": {
      "purpose": "FastAPI panel backend — reads all env vars + TLS + SSH keys",
      "mount": "/run/secrets",
      "secrets": [
        {"path": "env/main.env", "purpose": "Master environment variables (DB, Redis, API keys, JWT secret)", "perm": "600"},
        {"path": "tls/container-api-key.pem", "purpose": "TLS private key for customer container API", "perm": "600"},
        {"path": "tls/container-api-cert.pem", "purpose": "TLS certificate for customer container API", "perm": "644"},
        {"path": "ssh/id_ecdsa", "purpose": "ECDSA SSH private key for panel→container access", "perm": "600"},
        {"path": "ssh/id_ecdsa.pub", "purpose": "ECDSA SSH public key for panel→container access", "perm": "644"},
        {"path": "config/pdns.conf", "purpose": "PowerDNS configuration (contains API key for DNS management)", "perm": "600"},
        {"path": "config/docker-compose.yml", "purpose": "Backup of the docker-compose configuration", "perm": "600"}
      ]
    },
    "powerdns": {
      "purpose": "Authoritative DNS server",
      "mount": "/etc/powerdns/pdns.conf",
      "secrets": [
        {"path": "config/pdns.conf", "purpose": "PowerDNS config with api-key for zone management", "perm": "600"}
      ]
    },
    "mysql": {
      "purpose": "MySQL 8.4 database — stores panel data",
      "mount": "/var/lib/mysql",
      "secrets": [
        {"path": "tls/mysql/ca-key.pem", "purpose": "MySQL CA private key", "perm": "600"},
        {"path": "tls/mysql/ca.pem", "purpose": "MySQL CA certificate", "perm": "644"},
        {"path": "tls/mysql/server-key.pem", "purpose": "MySQL server TLS private key", "perm": "600"},
        {"path": "tls/mysql/server-cert.pem", "purpose": "MySQL server TLS certificate", "perm": "644"},
        {"path": "tls/mysql/client-key.pem", "purpose": "MySQL client TLS private key", "perm": "600"},
        {"path": "tls/mysql/client-cert.pem", "purpose": "MySQL client TLS certificate", "perm": "644"}
      ]
    },
    "opendkim": {
      "purpose": "DKIM email signing",
      "mount": "/etc/opendkim/keys",
      "secrets": [
        {"path": "dkim/", "purpose": "Per-domain DKIM private keys (mail.private) and public records (mail.txt)", "perm": "600/644"}
      ]
    },
    "postfix": {
      "purpose": "Outbound SMTP mail relay",
      "mount": "/etc/postfix",
      "secrets": [
        {"path": "env/main.env", "purpose": "MAIL_HOSTNAME, ALLOWED_SENDER_DOMAINS for postfix configuration"}
      ]
    },
    "traefik": {
      "purpose": "Reverse proxy / TLS termination",
      "mount": "/etc/traefik",
      "secrets": [
        {"path": "env/main.env", "purpose": "ACME_EMAIL for Let's Encrypt certificate registration"}
      ]
    },
    "grafana": {
      "purpose": "Monitoring dashboard",
      "mount": "/etc/grafana",
      "secrets": [
        {"path": "env/main.env", "purpose": "GRAFANA_USER, GRAFANA_PASSWORD for admin login"}
      ]
    }
  },
  "files": [
    {"path": "env/main.env", "type": "env", "size": $(stat -c%s "${VAULT}/env/main.env" 2>/dev/null || echo 0), "sha256": "$(sha256sum "${VAULT}/env/main.env" 2>/dev/null | cut -d' ' -f1 || echo 'unknown')"},
    {"path": "env/test.resemble.media/public_html/.env.webpanel", "type": "env", "size": $(stat -c%s "${VAULT}/env/test.resemble.media/public_html/.env.webpanel" 2>/dev/null || echo 0), "sha256": "$(sha256sum "${VAULT}/env/test.resemble.media/public_html/.env.webpanel" 2>/dev/null | cut -d' ' -f1 || echo 'unknown')"},
    {"path": "config/pdns.conf", "type": "config", "size": $(stat -c%s "${VAULT}/config/pdns.conf" 2>/dev/null || echo 0), "sha256": "$(sha256sum "${VAULT}/config/pdns.conf" 2>/dev/null | cut -d' ' -f1 || echo 'unknown')"},
    {"path": "config/docker-compose.yml", "type": "config", "size": $(stat -c%s "${VAULT}/config/docker-compose.yml" 2>/dev/null || echo 0), "sha256": "$(sha256sum "${VAULT}/config/docker-compose.yml" 2>/dev/null | cut -d' ' -f1 || echo 'unknown')"},
    {"path": "ssh/id_ecdsa", "type": "ssh-key", "size": $(stat -c%s "${VAULT}/ssh/id_ecdsa" 2>/dev/null || echo 0), "sha256": "$(sha256sum "${VAULT}/ssh/id_ecdsa" 2>/dev/null | cut -d' ' -f1 || echo 'unknown')"},
    {"path": "ssh/id_ecdsa.pub", "type": "ssh-key", "size": $(stat -c%s "${VAULT}/ssh/id_ecdsa.pub" 2>/dev/null || echo 0), "sha256": "$(sha256sum "${VAULT}/ssh/id_ecdsa.pub" 2>/dev/null | cut -d' ' -f1 || echo 'unknown')"},
    {"path": "tls/container-api-key.pem", "type": "tls-key", "size": $(stat -c%s "${VAULT}/tls/container-api-key.pem" 2>/dev/null || echo 0), "sha256": "$(sha256sum "${VAULT}/tls/container-api-key.pem" 2>/dev/null | cut -d' ' -f1 || echo 'unknown')"},
    {"path": "tls/container-api-cert.pem", "type": "tls-cert", "size": $(stat -c%s "${VAULT}/tls/container-api-cert.pem" 2>/dev/null || echo 0), "sha256": "$(sha256sum "${VAULT}/tls/container-api-cert.pem" 2>/dev/null | cut -d' ' -f1 || echo 'unknown')"},
    {"path": "tls/mysql/ca-key.pem", "type": "tls-key", "size": $(stat -c%s "${VAULT}/tls/mysql/ca-key.pem" 2>/dev/null || echo 0), "sha256": "$(sha256sum "${VAULT}/tls/mysql/ca-key.pem" 2>/dev/null | cut -d' ' -f1 || echo 'unknown')"},
    {"path": "tls/mysql/ca.pem", "type": "tls-cert", "size": $(stat -c%s "${VAULT}/tls/mysql/ca.pem" 2>/dev/null || echo 0), "sha256": "$(sha256sum "${VAULT}/tls/mysql/ca.pem" 2>/dev/null | cut -d' ' -f1 || echo 'unknown')"},
    {"path": "tls/mysql/server-key.pem", "type": "tls-key", "size": $(stat -c%s "${VAULT}/tls/mysql/server-key.pem" 2>/dev/null || echo 0), "sha256": "$(sha256sum "${VAULT}/tls/mysql/server-key.pem" 2>/dev/null | cut -d' ' -f1 || echo 'unknown')"},
    {"path": "tls/mysql/server-cert.pem", "type": "tls-cert", "size": $(stat -c%s "${VAULT}/tls/mysql/server-cert.pem" 2>/dev/null || echo 0), "sha256": "$(sha256sum "${VAULT}/tls/mysql/server-cert.pem" 2>/dev/null | cut -d' ' -f1 || echo 'unknown')"},
    {"path": "tls/mysql/client-key.pem", "type": "tls-key", "size": $(stat -c%s "${VAULT}/tls/mysql/client-key.pem" 2>/dev/null || echo 0), "sha256": "$(sha256sum "${VAULT}/tls/mysql/client-key.pem" 2>/dev/null | cut -d' ' -f1 || echo 'unknown')"},
    {"path": "tls/mysql/client-cert.pem", "type": "tls-cert", "size": $(stat -c%s "${VAULT}/tls/mysql/client-cert.pem" 2>/dev/null || echo 0), "sha256": "$(sha256sum "${VAULT}/tls/mysql/client-cert.pem" 2>/dev/null | cut -d' ' -f1 || echo 'unknown')"},
    {"path": "dkim/key.table", "type": "dkim", "size": $(stat -c%s "${VAULT}/dkim/key.table" 2>/dev/null || echo 0), "sha256": "$(sha256sum "${VAULT}/dkim/key.table" 2>/dev/null | cut -d' ' -f1 || echo 'unknown')"},
    {"path": "dkim/signing.table", "type": "dkim", "size": $(stat -c%s "${VAULT}/dkim/signing.table" 2>/dev/null || echo 0), "sha256": "$(sha256sum "${VAULT}/dkim/signing.table" 2>/dev/null | cut -d' ' -f1 || echo 'unknown')"},
    {"path": "dkim/test.resemble.media/mail.private", "type": "dkim-key", "size": $(stat -c%s "${VAULT}/dkim/test.resemble.media/mail.private" 2>/dev/null || echo 0), "sha256": "$(sha256sum "${VAULT}/dkim/test.resemble.media/mail.private" 2>/dev/null | cut -d' ' -f1 || echo 'unknown')"},
    {"path": "dkim/test.resemble.media/mail.public", "type": "dkim-key", "size": $(stat -c%s "${VAULT}/dkim/test.resemble.media/mail.public" 2>/dev/null || echo 0), "sha256": "$(sha256sum "${VAULT}/dkim/test.resemble.media/mail.public" 2>/dev/null | cut -d' ' -f1 || echo 'unknown')"}
  ]
}
JSON
)
    echo "$manifest" > "${VAULT}/secrets.json"
    chown root:"${DOCKER_GID}" "${VAULT}/secrets.json"
    chmod 0640 "${VAULT}/secrets.json"
    ok "Security matrix written: ${VAULT}/secrets.json"
}

# ── Verify manifest ──────────────────────────────────────────────────────────
verify_manifest() {
    if [[ ! -f "${VAULT}/secrets.json" ]]; then
        die "No secrets.json found — run without --verify first"
    fi
    # Validate JSON
    if command -v python3 &>/dev/null; then
        python3 -m json.tool "${VAULT}/secrets.json" > /dev/null 2>&1 || die "Invalid JSON in secrets.json"
        ok "secrets.json is valid JSON"
    fi
    # Check required fields
    local uuid_from_manifest
    uuid_from_manifest=$(grep -o '"install_uuid"[[:space:]]*:[[:space:]]*"[^"]*"' "${VAULT}/secrets.json" | cut -d'"' -f4)
    if [[ "$uuid_from_manifest" == "$UUID" ]]; then
        ok "install_uuid matches: ${uuid_from_manifest}"
    else
        warn "install_uuid mismatch — manifest: ${uuid_from_manifest}, actual: ${UUID}"
    fi
    echo ""
    echo -e "${BOLD}Security Matrix Summary:${NC}"
    echo "  Install UUID: ${UUID}"
    echo "  Services mapped: $(grep -o '"[a-z]*"[[:space:]]*:[[:space:]]*{' "${VAULT}/secrets.json" | grep -v "files\|version\|updated_at\|install_uuid\|vault_root" | wc -l)"
    echo "  Secret files tracked: $(grep -c '"path"' "${VAULT}/secrets.json")"
    echo ""
    python3 -c "
import json
with open('${VAULT}/secrets.json') as f:
    m = json.load(f)
print('  Service → Secret count:')
for svc, info in m.get('services', {}).items():
    print(f'    {svc}: {len(info.get(\"secrets\", []))} secrets — {info.get(\"purpose\", \"\")}')
" 2>/dev/null || true
}

# ── Main ─────────────────────────────────────────────────────────────────────
case "${1:-}" in
    --verify|-v)
        verify_manifest
        ;;
    --help|-h)
        echo "Usage: bash write-secrets-manifest.sh [--verify]"
        echo ""
        echo "  (no args)  Generate/update secrets.json manifest"
        echo "  --verify   Validate existing manifest"
        ;;
    *)
        build_manifest
        verify_manifest
        ;;
esac
