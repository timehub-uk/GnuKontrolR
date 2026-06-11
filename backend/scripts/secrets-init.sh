#!/usr/bin/env bash
# ── GnuKontrolR Secrets Vault — Initialiser ───────────────────────────────────
# Run once at install time (called by setup.sh).
#   Creates:
#     - /opt/gnukontrolr/secrets/            (0700 root:root)
#     - /opt/gnukontrolr/secrets/install.id  (installation UUID)
#     - /opt/gnukontrolr/secrets/<UUID>/env/main.env
#     - /opt/gnukontrolr/secrets/<UUID>/ssh/  (panel SSH keypair)
#     - /opt/gnukontrolr/secrets/<UUID>/tls/  (container API certs)
#     - /opt/gnukontrolr/secrets/<UUID>/config/  (sensitive .cnf / .conf)
#
# Usage:
#   bash secrets-init.sh           # fresh init (interactive if no .env)
#   bash secrets-init.sh --migrate # move existing secrets into vault
#   bash secrets-init.sh --status  # print vault status
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/secrets-lib.sh"

# ── Paths (relative to the project root) ─────────────────────────────────────
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_SOURCE="${PROJECT_ROOT}/.env"              # may be in /opt/gnukontrolr or home
# Also check /opt/gnukontrolr/.env if PROJECT_ROOT isn't /opt/gnukontrolr
[[ -f "$ENV_SOURCE" ]] || ENV_SOURCE="/opt/gnukontrolr/.env"
[[ -f "$ENV_SOURCE" ]] || ENV_SOURCE="${HOME}/GnuKontrolR/.env"
DOCKER_COMPOSE="${PROJECT_ROOT}/docker-compose.yml"

# ── Update UUID in docker-compose files ────────────────────────────────────
_update_compose_uuid() {
    local uuid="$1"
    local compose_files=(
        "${PROJECT_ROOT}/docker-compose.yml"
        "/opt/gnukontrolr/docker-compose.yml"
        "${PROJECT_ROOT}/docker-compose.secrets.yml"
        "/opt/gnukontrolr/docker-compose.secrets.yml"
    )
    for compose_file in "${compose_files[@]}"; do
        if [[ -f "$compose_file" ]]; then
            # Replace old UUID pattern (if any) with the current one
            sed -i "s|/opt/gnukontrolr/secrets/[0-9a-f-]*/|/opt/gnukontrolr/secrets/${uuid}/|g" "$compose_file"
            ok "Updated UUID in ${compose_file}"
        fi
    done
}

# ── Print vault status ───────────────────────────────────────────────────────
status() {
    echo ""
    echo -e "${BOLD}━━━ GnuKontrolR Secrets Vault ────${NC}"
    if is_vault_initialized; then
        local uuid vault
        uuid=$(get_install_uuid)
        vault=$(get_vault_path)
        echo -e "  ${GREEN}✓${NC} Initialized"
        echo -e "  UUID:     ${BOLD}${uuid}${NC}"
        echo -e "  Vault:    ${vault}"
        echo -e "  Size:     $(du -sh "${vault}" 2>/dev/null | cut -f1)"
        echo -e "  Files:    $(find "${vault}" -type f 2>/dev/null | wc -l)"
        echo ""
        echo -e "${DIM}Contents:${NC}"
        find "${vault}" -type f 2>/dev/null | sort | while read -r f; do
            local perms
            perms=$(stat -c "%a" "$f" 2>/dev/null)
            echo -e "    ${perms}  ${f#${vault}/}"
        done
        echo ""
        echo -e "${BOLD}Permissions:${NC}"
        echo -e "  $(stat -c '%a %U:%G' "${SECRETS_ROOT}" 2>/dev/null)  ${SECRETS_ROOT}"
        echo -e "  $(stat -c '%a %U:%G' "${vault}" 2>/dev/null)  ${vault#${SECRETS_ROOT}/}"
    else
        echo -e "  ${YELLOW}⚠${NC} Not initialized"
    fi
}

# ── Helpers ───────────────────────────────────────────────────────────────────

# Set or add a KEY=VALUE line in a .env-style file.
_set_env_var() {
    local file="$1" key="$2" value="$3"
    if grep -qE "^(export )?${key}=" "$file" 2>/dev/null; then
        sed -i "s|^\(export \)\?${key}=.*|${key}=${value}|" "$file"
    else
        echo "${key}=${value}" >> "$file"
    fi
}

# ── Generate PowerDNS API key + configs at install or rotate ────────────────
# Returns the generated key via stdout.
_setup_pdns_key() {
    local vault api_key pdns_vault_path pdns_source_path env_vault_path
    vault=$(get_vault_path)

    # 1. Generate the 2-pair key
    api_key=$(generate_api_key)
    info "PowerDNS API key: ${DIM}${api_key}${NC}"

    # 2. Write vault copy of pdns.conf (backup / audit)
    pdns_vault_path="${vault}/config/pdns.conf"
    write_pdns_config "$pdns_vault_path" "$api_key" > /dev/null
    chown root:root "$pdns_vault_path"
    chmod 0600 "$pdns_vault_path"
    ok "Wrote vault pdns.conf → ${pdns_vault_path}"

    # 3. Update source pdns.conf for live bind-mount
    for pdns_source_path in "${PROJECT_ROOT}/docker/powerdns/pdns.conf" \
                            "/opt/gnukontrolr/docker/powerdns/pdns.conf"; do
        if [[ -f "$pdns_source_path" ]]; then
            write_pdns_config "$pdns_source_path" "$api_key" > /dev/null
            chown root:root "$pdns_source_path" 2>/dev/null || true
            chmod 0644 "$pdns_source_path"
            ok "Updated live pdns.conf → ${pdns_source_path}"
            break
        fi
    done

    # 4. Record PDNS_API_KEY in vault env/main.env
    env_vault_path="${vault}/env/main.env"
    if [[ -f "$env_vault_path" ]]; then
        _set_env_var "$env_vault_path" "PDNS_API_KEY" "$api_key"
        chmod 0600 "$env_vault_path"
        ok "Updated PDNS_API_KEY in vault env/main.env"
    else
        # Write fresh .env in vault
        echo "# Generated by secrets-init.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$env_vault_path"
        echo "" >> "$env_vault_path"
        echo "# ── PowerDNS ─────────────────────────────────────────────────" >> "$env_vault_path"
        echo "PDNS_API_KEY=${api_key}" >> "$env_vault_path"
        chown root:root "$env_vault_path"
        chmod 0600 "$env_vault_path"
        ok "Created vault env/main.env with PDNS_API_KEY"
    fi

    # 5. Also update source .env files so docker-compose picks it up
    for src_env in "${ENV_SOURCE}" "${PROJECT_ROOT}/.env" "/opt/gnukontrolr/.env"; do
        if [[ -f "$src_env" ]]; then
            _set_env_var "$src_env" "PDNS_API_KEY" "$api_key"
            ok "Updated PDNS_API_KEY in ${src_env}"
        fi
    done

    # 6. Update docker-compose — ensure the env var mapping is correct
    for compose_file in "${PROJECT_ROOT}/docker-compose.yml" \
                        "/opt/gnukontrolr/docker-compose.yml"; do
        if [[ -f "$compose_file" ]]; then
            # Ensure PDNS_AUTH_API_KEY references PDNS_API_KEY (not a literal fallback)
            if grep -q "PDNS_AUTH_API_KEY=" "$compose_file"; then
                sed -i 's|PDNS_AUTH_API_KEY=\${PDNS_API_KEY:-.*}|PDNS_AUTH_API_KEY=${PDNS_API_KEY}|' "$compose_file"
                ok "Updated docker-compose PDNS_AUTH_API_KEY mapping"
            fi
        fi
    done

    echo "$api_key"
}

# ── Write ACME email into Traefik static config ─────────────────────────────
# Reads ACME_EMAIL from the .env and writes it into docker/traefik/traefik.yml
# so Let's Encrypt registration uses the correct contact address.
_setup_acme_email() {
    local email traefik_yml

    # Read email from .env (check multiple locations)
    email=""
    for src_env in "${ENV_SOURCE}" "${PROJECT_ROOT}/.env" "/opt/gnukontrolr/.env"; do
        if [[ -f "$src_env" ]]; then
            email=$(grep "^ACME_EMAIL=" "$src_env" | head -1 | cut -d= -f2-)
            [[ -n "$email" ]] && break
        fi
    done

    if [[ -z "$email" ]]; then
        warn "ACME_EMAIL not found in any .env — using fallback placeholder"
        warn "Set ACME_EMAIL in your .env and re-run with --update-acme-email"
        email="admin@example.com"
    fi

    # Reject example.com domain
    if [[ "$email" == *"@example.com" ]]; then
        die "ACME_EMAIL=${email} uses forbidden domain example.com. Set a real email in .env (e.g. ACME_EMAIL=admin@yourdomain.com)"
    fi

    # Update the static config file(s)
    for traefik_yml in "${PROJECT_ROOT}/docker/traefik/traefik.yml" \
                       "/opt/gnukontrolr/docker/traefik/traefik.yml"; do
        if [[ -f "$traefik_yml" ]]; then
            sed -i "s|^\( *email: \).*|\1\"${email}\"  # set by secrets-init.sh|" "$traefik_yml"
            ok "Updated ACME email → ${traefik_yml} (${email})"
        fi
    done

    # Also ensure it's set in all .env files
    for src_env in "${ENV_SOURCE}" "${PROJECT_ROOT}/.env" "/opt/gnukontrolr/.env"; do
        if [[ -f "$src_env" ]]; then
            if grep -q "^ACME_EMAIL=" "$src_env" 2>/dev/null; then
                _set_env_var "$src_env" "ACME_EMAIL" "$email"
            else
                echo "" >> "$src_env"
                echo "# ── Let's Encrypt / ACME ────────────────────────────────────────" >> "$src_env"
                echo "ACME_EMAIL=${email}" >> "$src_env"
                ok "Added ACME_EMAIL to ${src_env}"
            fi
        fi
    done

    info "ACME email configured: ${BOLD}${email}${NC}"
}

# ── Initialize fresh vault ───────────────────────────────────────────────────
init_vault() {
    echo ""
    echo -e "${BOLD}━━━ Initialising Secrets Vault ──────${NC}"

    ensure_secrets_root
    ensure_version

    # Generate installation UUID
    local uuid
    uuid=$(get_install_uuid)
    info "Installation UUID: ${BOLD}${uuid}${NC}"
    ok "install.id created"

    local vault
    vault=$(get_vault_path)
    info "Vault path: ${vault}"

    # Create directory structure
    ensure_vault_dir "env"
    ensure_vault_dir "tls"
    ensure_vault_dir "ssh"
    ensure_vault_dir "config"
    ensure_vault_dir "dkim"
    ok "Directory structure created (0700 root:root)"

    # Migrate .env if it exists
    if [[ -f "$ENV_SOURCE" ]]; then
        copy_to_vault "$ENV_SOURCE" "env/main.env" 600
        ok "Migrated .env → vault"
    else
        warn "No .env found at ${ENV_SOURCE}"
        warn "Run 'setup.sh install' first, or create .env manually."
    fi

    # Migrate existing secrets from known locations
    migrate_existing

    # ══════════════════════════════════════════════════════════════════════
    # Generate PowerDNS API key — writes to:
    #   vault config/pdns.conf, source docker/powerdns/pdns.conf,
    #   vault env/main.env, and source .env files
    # ══════════════════════════════════════════════════════════════════════
    _setup_pdns_key > /dev/null

    # ══════════════════════════════════════════════════════════════════════
    # Write ACME email into Traefik static config — reads from .env so
    # Let's Encrypt registration uses the correct contact address.
    # ══════════════════════════════════════════════════════════════════════
    _setup_acme_email

    # Generate security matrix manifest
    bash "${SCRIPT_DIR}/write-secrets-manifest.sh" 2>&1 | sed 's/^/    /'

    # Update docker-compose files with the new UUID
    _update_compose_uuid "$uuid"

    # Lock down permissions
    lockdown_secrets

    echo ""
    echo -e "${GREEN}${BOLD}━━━ Secrets Vault initialised ────────${NC}"
    echo -e "  UUID: ${BOLD}${uuid}${NC}"
    echo -e "  Path: ${vault}"
    echo -e "  $(find "${vault}" -type f 2>/dev/null | wc -l) secrets stored"
    echo ""
}

# ── Migrate existing secrets from known locations ────────────────────────────
migrate_existing() {
    local vault
    vault=$(get_vault_path)

    # Docker-compose (may contain service passwords)
    if [[ -f "$DOCKER_COMPOSE" ]]; then
        copy_to_vault "$DOCKER_COMPOSE" "config/docker-compose.yml" 600 2>/dev/null || true
    fi

    # PowerDNS config
    local pdns_src
    for pdns_src in "${PROJECT_ROOT}/docker/powerdns/pdns.conf" \
                    "/opt/gnukontrolr/docker/powerdns/pdns.conf"; do
        if [[ -f "$pdns_src" ]]; then
            copy_to_vault "$pdns_src" "config/pdns.conf" 600
            break
        fi
    done

    # MySQL client config (if exists)
    for f in "${PROJECT_ROOT}/docker/mysql/my.cnf" \
             "/opt/gnukontrolr/docker/mysql/my.cnf" \
             "${PROJECT_ROOT}/docker/mysql/mysql.cnf" \
             "/opt/gnukontrolr/docker/mysql/mysql.cnf"; do
        if [[ -f "$f" ]]; then
            copy_to_vault "$f" "config/mysql.cnf" 600 2>/dev/null || true
            break
        fi
    done

    # Container API TLS certs
    for cert_dir in "${PROJECT_ROOT}/docker/tls" \
                    "/opt/gnukontrolr/docker/tls"; do
        if [[ -d "$cert_dir" ]]; then
            for cert_file in "$cert_dir"/*; do
                if [[ -f "$cert_file" ]]; then
                    local base mode
                    base=$(basename "$cert_file")
                    case "$base" in
                        *-key.pem|*.key) mode=600 ;;
                        *)              mode=644 ;;
                    esac
                    copy_to_vault "$cert_file" "tls/${base}" "$mode" 2>/dev/null || true
                fi
            done
        fi
    done

    # Panel SSH keys
    for ssh_dir in "/var/webpanel/panel_ssh" \
                   "${PROJECT_ROOT}/ssh" \
                   "/opt/gnukontrolr/ssh"; do
        if [[ -d "$ssh_dir" ]]; then
            for ssh_file in "$ssh_dir"/*; do
                if [[ -f "$ssh_file" ]]; then
                    local base mode
                    base=$(basename "$ssh_file")
                    case "$base" in
                        *.pub) mode=644 ;;
                        *)     mode=600 ;;
                    esac
                    copy_to_vault "$ssh_file" "ssh/${base}" "$mode" 2>/dev/null || true
                fi
            done
        fi
    done

    # DKIM keys (from Docker volume or host path)
    for dkim_dir in "/var/lib/docker/volumes/gnukontrolr_dkim_keys/_data" \
                   "/etc/opendkim/keys"; do
        if [[ -d "$dkim_dir" ]]; then
            find "$dkim_dir" -type f 2>/dev/null | while read -r f; do
                local rel_path mode
                rel_path="dkim/${f#${dkim_dir}/}"
                case "$(basename "$f")" in
                    *.private|*key) mode=600 ;;
                    *.txt|*.pub)    mode=644 ;;
                    *)              mode=600 ;;
                esac
                copy_to_vault "$f" "$rel_path" "$mode" 2>/dev/null || true
            done
        fi
    done

    # .env.webpanel from customer sites (contains passwords)
    find /var/webpanel/sites -name ".env.webpanel" -type f 2>/dev/null | while read -r f; do
        local site_rel
        site_rel="${f#/var/webpanel/sites/}"
        copy_to_vault "$f" "env/${site_rel}" 600 2>/dev/null || true
    done

    # MySQL SSL/TLS certs from Docker volume
    local mysql_vol="/var/lib/docker/volumes/gnukontrolr_mysql_data/_data"
    if [[ -d "$mysql_vol" ]]; then
        for f in "$mysql_vol"/ca-key.pem "$mysql_vol"/ca.pem \
                 "$mysql_vol"/server-cert.pem "$mysql_vol"/server-key.pem \
                 "$mysql_vol"/client-cert.pem "$mysql_vol"/client-key.pem; do
            if [[ -f "$f" ]]; then
                local base mode
                base=$(basename "$f")
                case "$base" in
                    *-key.pem|*.key) mode=600 ;;
                    *)              mode=644 ;;
                esac
                copy_to_vault "$f" "tls/mysql/${base}" "$mode" 2>/dev/null || true
            fi
        done
    fi

    ok "Migrated existing secrets from known locations"
}

# ── Main ─────────────────────────────────────────────────────────────────────
case "${1:-}" in
    --status|-s)
        status
        ;;
    --migrate|-m)
        ensure_secrets_root
        ensure_version
        get_install_uuid > /dev/null
        migrate_existing
        lockdown_secrets
        echo ""
        ok "Migration complete"
        ;;
    --rotate-pdns-key|-r)
        echo ""
        echo -e "${BOLD}━━━ Rotating PowerDNS API Key ────────${NC}"
        if ! is_vault_initialized; then
            die "Vault not initialised. Run without flags first."
        fi
        old_key=$(read_secret "config/pdns.conf" 2>/dev/null | grep "^api-key=" | cut -d= -f2 || echo "unknown")
        new_key=$(_setup_pdns_key)
        echo ""
        echo -e "  ${YELLOW}Old key:${NC} ${old_key}"
        echo -e "  ${GREEN}New key:${NC} ${new_key}"
        echo ""
        # Update manifest
        bash "${SCRIPT_DIR}/write-secrets-manifest.sh" 2>&1 | sed 's/^/    /'
        lockdown_secrets
        echo ""
        echo -e "${GREEN}${BOLD}━━━ PDNS API key rotated ───────────${NC}"
        echo -e "  ${YELLOW}⚠ Next step:${NC} Restart PowerDNS and webpanel containers:"
        echo -e "     docker restart webpanel_powerdns webpanel_api"
        echo ""
        ;;
    --update-acme-email|-a)
        echo ""
        echo -e "${BOLD}━━━ Updating ACME Email ──────────────${NC}"
        _setup_acme_email
        echo ""
        echo -e "${GREEN}${BOLD}━━━ ACME email updated ────────────${NC}"
        echo -e "  ${YELLOW}⚠ Next step:${NC} Restart Traefik to pick up the new email:"
        echo -e "     docker restart webpanel_traefik"
        echo ""
        ;;
    --help|-h)
        echo "Usage: bash secrets-init.sh [--status|--migrate|--rotate-pdns-key|--update-acme-email|--help]"
        echo ""
        echo "  (no args)                Interactive initialisation (first install)"
        echo "  --status                 Print vault status"
        echo "  --migrate                Migrate existing secrets into the vault"
        echo "  --rotate-pdns-key        Generate a new 2-pair PDNS API key"
        echo "  --update-acme-email      Write ACME_EMAIL from .env into traefik.yml"
        echo "  --help                   This message"
        ;;
    *)
        if is_vault_initialized; then
            echo -e "  ${YELLOW}⚠${NC} Secrets vault already initialised."
            echo "  Run with --status to check, or --migrate to update."
        else
            init_vault
        fi
        ;;
esac
