#!/usr/bin/env bash
# ── GnuKontrolR Secrets Vault Library ─────────────────────────────────────────
# Shared functions for secrets-init, secrets-migrate, and setup.sh integration.
# Source this file:  source "$(dirname "$0")/secrets-lib.sh"
#
# Vault layout:
#   /opt/gnukontrolr/secrets/
#   ├── install.id              # Single installation UUID
#   ├── VERSION                 # Schema version (currently 1)
#   └── <INSTALL_UUID>/
#       ├── env/main.env        # Master environment file
#       ├── tls/                # TLS certs + private keys
#       ├── dkim/<domain>/      # DKIM keypairs
#       ├── ssh/                # Panel SSH keypair
#       └── config/             # Sensitive config files (pdns.conf, etc.)
#
# Permissions:
#   /opt/gnukontrolr/secrets/          0700 root:root
#   *.private, *-key.pem, *.key        0600 root:root
#   *.pem, *.pub, *.crt, *.cert         644 root:root
#   main.env                            600 root:root
#   install.id                          600 root:root
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Paths ────────────────────────────────────────────────────────────────────
SECRETS_ROOT="/opt/gnukontrolr/secrets"
SECRETS_INSTALL_ID="${SECRETS_ROOT}/install.id"
SECRETS_VERSION_FILE="${SECRETS_ROOT}/VERSION"
SECRETS_SCHEMA_VERSION="1"

# ── Colours (passthrough from setup.sh if present) ───────────────────────────
NC='\033[0m'; RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; DIM='\033[2m'

info()  { echo -e "  ${BOLD}•${NC} $*"; }
ok()    { echo -e "  ${GREEN}✓${NC} $*"; }
warn()  { echo -e "  ${YELLOW}⚠${NC} $*"; }
die()   { echo -e "  ${RED}✘${NC} $*" >&2; exit 1; }

# ── UUID generation (no dependency on uuidgen) ───────────────────────────────
generate_uuid() {
    # UUID v4 — try uuidgen first, fall back to /proc, then pure-bash
    if command -v uuidgen &>/dev/null; then
        uuidgen | tr '[:upper:]' '[:lower:]'
        return
    fi
    if [[ -f /proc/sys/kernel/random/uuid ]]; then
        cat /proc/sys/kernel/random/uuid
        return
    fi
    # Pure-bash fallback: 8-4-4-4-12 hex digits with version 4 / variant 1
    local hex=""
    local i b
    for ((i=0; i<32; i++)); do
        b=$((RANDOM % 16))
        case $i in
            12) printf '4%x' $((b % 16)) ;;     # time_hi_and_version (version 4)
            16) printf '%x%x' $((b % 4 + 8)) $((RANDOM % 16)) ;;  # clock_seq_hi_and_reserved (variant 1)
            *)  printf '%x' $b ;;
        esac
    done | sed 's/^\(........\)\(....\)\(....\)\(....\)\(............\)$/\1-\2-\3-\4-\5/'
}

# ── Ensure secrets root exists with correct permissions ──────────────────────
ensure_secrets_root() {
    if [[ ! -d "$SECRETS_ROOT" ]]; then
        mkdir -p "$SECRETS_ROOT"
        chown root:root "$SECRETS_ROOT"
        chmod 0700 "$SECRETS_ROOT"
        info "Created secrets root: ${SECRETS_ROOT} (0700 root:root)"
    fi
}

# ── Get or create the installation UUID ──────────────────────────────────────
get_install_uuid() {
    ensure_secrets_root
    if [[ -f "$SECRETS_INSTALL_ID" ]]; then
        cat "$SECRETS_INSTALL_ID"
    else
        local uuid
        uuid=$(generate_uuid)
        echo "$uuid" > "$SECRETS_INSTALL_ID"
        chown root:root "$SECRETS_INSTALL_ID"
        chmod 0600 "$SECRETS_INSTALL_ID"
        echo "$uuid"
    fi
}

# ── Get the vault path for the current installation ──────────────────────────
get_vault_path() {
    local uuid
    uuid=$(get_install_uuid)
    echo "${SECRETS_ROOT}/${uuid}"
}

# ── Ensure a subdirectory exists inside the vault with 0700 permissions ──────
ensure_vault_dir() {
    local vault subdir path
    vault=$(get_vault_path)
    subdir="$1"
    path="${vault}/${subdir}"
    if [[ ! -d "$path" ]]; then
        mkdir -p "$path"
        chown root:root "$path"
        chmod 0700 "$path"
    fi
    echo "$path"
}

# ── Write a secret file with correct permissions ─────────────────────────────
# Usage: write_secret <relative_path> <content> [mode]
#   relative_path: e.g. "env/main.env" or "tls/server-key.pem"
#   content:       the file content (string)
#   mode:          permissions (default: 600)
write_secret() {
    local rel_path="$1" content="$2" mode="${3:-600}"
    local vault dir abs_path
    vault=$(get_vault_path)
    dir=$(dirname "${vault}/${rel_path}")
    mkdir -p "$dir" && chmod 0700 "$dir" && chown root:root "$dir"
    abs_path="${vault}/${rel_path}"
    echo "$content" > "$abs_path"
    chown root:root "$abs_path"
    chmod "$mode" "$abs_path"
    ok "Wrote ${abs_path} (${mode})"
}

# ── Copy a file into the vault with correct permissions ──────────────────────
# Usage: copy_to_vault <source_path> <relative_dest> [mode]
copy_to_vault() {
    local src="$1" rel_dest="$2" mode="${3:-600}"
    local vault dir abs_path
    vault=$(get_vault_path)
    dir=$(dirname "${vault}/${rel_dest}")
    mkdir -p "$dir" && chmod 0700 "$dir" && chown root:root "$dir"
    abs_path="${vault}/${rel_dest}"
    cp -f "$src" "$abs_path"
    chown root:root "$abs_path"
    chmod "$mode" "$abs_path"
    ok "Copied ${src} → ${abs_path} (${mode})"
}

# ── Read a secret file from the vault ────────────────────────────────────────
read_secret() {
    local rel_path="$1"
    local vault abs_path
    vault=$(get_vault_path)
    abs_path="${vault}/${rel_path}"
    if [[ -f "$abs_path" ]]; then
        cat "$abs_path"
    else
        return 1
    fi
}

# ── Check if vault is fully initialized ──────────────────────────────────────
is_vault_initialized() {
    local vault
    vault=$(get_vault_path 2>/dev/null) || return 1
    [[ -d "$vault" ]] && [[ -f "${vault}/env/main.env" ]]
}

# ── Ensure secrets schema version is current ─────────────────────────────────
ensure_version() {
    if [[ -f "$SECRETS_VERSION_FILE" ]]; then
        local ver
        ver=$(cat "$SECRETS_VERSION_FILE")
        if [[ "$ver" != "$SECRETS_SCHEMA_VERSION" ]]; then
            warn "Secrets vault schema v${ver} != expected v${SECRETS_SCHEMA_VERSION}"
            warn "Run migrate script to upgrade."
        fi
    else
        echo "$SECRETS_SCHEMA_VERSION" > "$SECRETS_VERSION_FILE"
        chown root:root "$SECRETS_VERSION_FILE"
        chmod 0600 "$SECRETS_VERSION_FILE"
    fi
}

# ── Docker group GID (used so container user can read vault) ──────────────────
DOCKER_GID="${DOCKER_GID:-129}"

# ── Lock down the entire secrets tree ────────────────────────────────────────
# The vault root stays 0700 root:root — only root can list it.
# The UUID subdirectory gets group-read (0750) so the container's panelapi user
# (which is a member of the docker group / GID ${DOCKER_GID}) can traverse it.
lockdown_secrets() {
    local vault
    ensure_secrets_root
    vault=$(get_vault_path 2>/dev/null) || true

    # Root directory: 0700 root:root — only root can list
    chmod 0700 "$SECRETS_ROOT"
    chown root:root "$SECRETS_ROOT" 2>/dev/null || true

    # UUID subdirectory: 0750 root:${DOCKER_GID} — container can traverse
    if [[ -n "$vault" && -d "$vault" ]]; then
        chmod 0750 "$vault"
        chown root:"$DOCKER_GID" "$vault" 2>/dev/null || true

        # All subdirectories: 0750 root:${DOCKER_GID}
        find "$vault" -type d 2>/dev/null | while read -r d; do
            chmod 0750 "$d"
            chown root:"$DOCKER_GID" "$d" 2>/dev/null || true
        done

        # All private keys, env files, configs: 0640 root:${DOCKER_GID} (group-read)
        find "$vault" -type f \( \
            -name "*.key" -o -name "*-key.pem" -o -name "*.private" \
            -o -name "main.env" -o -name "install.id" -o -name "VERSION" \
            -o -name "*.cnf" -o -name "pdns.conf" -o -name "id_ecdsa" \
            -o -name "id_ed25519" -o -name "id_rsa" \
        \) 2>/dev/null | while read -r f; do
            chmod 0640 "$f"
            chown root:"$DOCKER_GID" "$f" 2>/dev/null || true
        done

        # Public certs/documents: 0644 root:${DOCKER_GID}
        find "$vault" -type f \( \
            -name "*.pem" -o -name "*.crt" -o -name "*.cert" \
            -o -name "*.pub" -o -name "mail.txt" \
        \) 2>/dev/null | while read -r f; do
            # Skip private keys (already handled above)
            case "$f" in
                *-key.pem|*key.pem) ;;
                *) chmod 0644 "$f"; chown root:"$DOCKER_GID" "$f" 2>/dev/null || true ;;
            esac
        done
    fi

    ok "Secrets vault locked down (dirs 0750, files 0640/0644, group ${DOCKER_GID})"
}

# ── Generate a 2-pair API key (xxxxxxxx-xxxxxxxx) ────────────────────────────
# Uses /dev/urandom for cryptographic randomness; no external dependencies.
# Output: 32 random hex chars formatted as two 16-char segments separated by a
#         single dash — 128 bits of entropy, suitable for PDNS API keys.
generate_api_key() {
    local raw
    if [[ -f /proc/sys/kernel/random/uuid ]]; then
        # Generate 4 UUIDs, strip dashes, take first 32 hex chars, split 16+16
        raw=$(cat /proc/sys/kernel/random/uuid /proc/sys/kernel/random/uuid 2>/dev/null | tr -d '\n-')
        if [[ ${#raw} -ge 32 ]]; then
            echo "${raw:0:16}-${raw:16:16}"
            return
        fi
    fi
    # Pure-bash fallback via /dev/urandom
    raw=$(dd if=/dev/urandom bs=1 count=32 2>/dev/null | od -A n -t x1 | tr -d ' \n')
    echo "${raw:0:16}-${raw:16:16}"
}

# ── Write pdns.conf with a generated API key ─────────────────────────────────
# Usage: write_pdns_config <target_path> [api_key]
# If no api_key is provided, one is generated.
# Returns the API key via stdout (so the caller can record it in env files too).
write_pdns_config() {
    local target="${1:-}"
    local api_key="${2:-}"
    [[ -z "$target" ]] && { die "write_pdns_config: missing target path"; return 1; }
    [[ -z "$api_key" ]] && api_key=$(generate_api_key)

    cat > "$target" <<PDNSEOF
launch=gsqlite3
gsqlite3-database=/var/lib/powerdns/pdns.sqlite3
gsqlite3-dnssec=yes
gsqlite3-pragma-journal-mode=WAL
gsqlite3-pragma-synchronous=NORMAL

webserver=yes
webserver-address=0.0.0.0
webserver-port=8081
# Restrict API to Docker internal bridge only — not reachable from outside webpanel_net
webserver-allow-from=127.0.0.1,172.30.0.0/16

api=yes
# This key is auto-generated by the secrets vault installer.
# The same value must be set as PDNS_API_KEY in the panel .env so the panel
# can authenticate, and as PDNS_AUTH_API_KEY in docker-compose for PDNS itself.
api-key=${api_key}

local-address=0.0.0.0
local-port=53

dnsupdate=yes
log-dns-queries=no
log-dns-details=yes
PDNSEOF

    # Return the key so callers can capture it without re-reading the file
    echo "$api_key"
}
