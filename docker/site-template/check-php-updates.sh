#!/bin/bash
# GnuKontrolR — Auto-detect and build new PHP FPM versions
#
# Queries Docker Hub for php:X.Y-fpm-bookworm tags, compares against
# locally built webpanel/php-site images, and builds any new versions found.
# Also updates SUPPORTED_PHP in docker_mgr.py if new versions are added.
#
# Usage:
#   ./check-php-updates.sh             # check and build new versions
#   ./check-php-updates.sh --dry-run   # show what would be built, don't build
#   ./check-php-updates.sh --force 8.4 # force build a specific version

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DOCKER_MGR="${REPO_ROOT}/backend/app/routers/docker_mgr.py"

DRY_RUN=false
FORCE_VERSION=""

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --force)   shift; FORCE_VERSION="${1:-}" ;;
        --force=*) FORCE_VERSION="${arg#--force=}" ;;
    esac
done

# ── Fetch available PHP minor versions from Docker Hub ────────────────────────
# Looks for tags matching X.Y-fpm-bookworm (e.g. 8.1-fpm-bookworm, 8.4-fpm-bookworm)
fetch_available_versions() {
    local page=1
    local versions=()

    while true; do
        local url="https://hub.docker.com/v2/repositories/library/php/tags?page=${page}&page_size=100&name=fpm-bookworm"
        local response
        response=$(curl -fsSL --max-time 15 "$url" 2>/dev/null) || break

        # Extract X.Y-fpm-bookworm tags (minor versions only, not patch like 8.2.1-fpm-bookworm)
        local page_versions
        page_versions=$(echo "$response" | grep -oP '"name":\s*"\K[0-9]+\.[0-9]+-fpm-bookworm(?=")' | sed 's/-fpm-bookworm//' | sort -V) || true

        if [ -z "$page_versions" ]; then
            break
        fi

        while IFS= read -r v; do
            versions+=("$v")
        done <<< "$page_versions"

        # Check if there's a next page
        local next
        next=$(echo "$response" | grep -oP '"next":\s*"\K[^"]+' 2>/dev/null) || true
        if [ -z "$next" ] || [ "$next" = "null" ]; then
            break
        fi
        ((page++))
        sleep 0.5  # be polite to Docker Hub
    done

    # Deduplicate and sort
    printf '%s\n' "${versions[@]}" | sort -uV
}

# ── Get locally built webpanel/php-site versions ─────────────────────────────
fetch_local_versions() {
    docker images --format "{{.Tag}}" webpanel/php-site 2>/dev/null | grep -E '^[0-9]+\.[0-9]+$' | sort -V
}

# ── Update SUPPORTED_PHP in docker_mgr.py ────────────────────────────────────
update_supported_php() {
    local versions_array="$1"   # e.g. '"8.1", "8.2", "8.3", "8.4"'

    if [ ! -f "$DOCKER_MGR" ]; then
        echo "[warn] docker_mgr.py not found at ${DOCKER_MGR} — skipping SUPPORTED_PHP update"
        return
    fi

    # Replace the SUPPORTED_PHP line
    local new_line="SUPPORTED_PHP     = {${versions_array}}"
    if grep -q "^SUPPORTED_PHP" "$DOCKER_MGR"; then
        sed -i "s|^SUPPORTED_PHP.*|${new_line}|" "$DOCKER_MGR"
        echo "[info] Updated SUPPORTED_PHP in docker_mgr.py: {${versions_array}}"
    else
        echo "[warn] SUPPORTED_PHP not found in docker_mgr.py — skipping update"
    fi
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    echo "==> Fetching available PHP FPM (bookworm) versions from Docker Hub..."
    local available
    available=$(fetch_available_versions)

    if [ -z "$available" ]; then
        echo "[error] Could not fetch PHP versions from Docker Hub (network issue?)"
        exit 1
    fi

    echo "Available: $(echo "$available" | tr '\n' ' ')"

    local local_versions
    local_versions=$(fetch_local_versions)
    echo "Built:     $(echo "$local_versions" | tr '\n' ' ')"

    # If --force, just build that version
    if [ -n "$FORCE_VERSION" ]; then
        echo "==> Force-building webpanel/php-site:${FORCE_VERSION}"
        if [ "$DRY_RUN" = true ]; then
            echo "[dry-run] Would build: ${FORCE_VERSION}"
        else
            bash "${SCRIPT_DIR}/build-all.sh" "$FORCE_VERSION"
        fi
        return
    fi

    # Find versions that are available upstream but not built locally
    local new_versions=()
    while IFS= read -r ver; do
        if ! echo "$local_versions" | grep -qx "$ver"; then
            new_versions+=("$ver")
        fi
    done <<< "$available"

    if [ ${#new_versions[@]} -eq 0 ]; then
        echo "==> All available PHP versions are already built. Nothing to do."
        exit 0
    fi

    echo "==> New PHP versions to build: ${new_versions[*]}"

    if [ "$DRY_RUN" = true ]; then
        echo "[dry-run] Would build: ${new_versions[*]}"
        exit 0
    fi

    # Build each new version
    local built=()
    for ver in "${new_versions[@]}"; do
        echo ""
        echo "==> Building webpanel/php-site:${ver} (new PHP version detected)"
        if bash "${SCRIPT_DIR}/build-all.sh" "$ver"; then
            built+=("$ver")
            echo "==> Successfully built webpanel/php-site:${ver}"
        else
            echo "[error] Failed to build webpanel/php-site:${ver} — skipping"
        fi
    done

    if [ ${#built[@]} -gt 0 ]; then
        echo ""
        echo "==> Updating SUPPORTED_PHP in backend..."
        # Collect all now-locally-available versions
        local all_local
        all_local=$(fetch_local_versions)
        local versions_str
        versions_str=$(echo "$all_local" | awk '{printf "\"%s\", ", $0}' | sed 's/, $//')
        update_supported_php "$versions_str"

        echo ""
        echo "==> Done. New versions added: ${built[*]}"
        echo "    Rebuild the webpanel backend to pick up the SUPPORTED_PHP change:"
        echo "    cd ${REPO_ROOT} && docker compose build webpanel && docker compose up -d webpanel"
    fi
}

main "$@"
