#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# GnuKontrolR — Setup / management helper
# Usage: bash setup.sh [command]
#
# Commands:
#   install     Full first-time installation (packages, dirs, env, build, start)
#   start       Start all services
#   stop        Stop all services
#   restart     Restart all services
#   status      Show service status
#   logs        Tail logs (all or: logs webpanel)
#   update      Pull latest code and rebuild
#   backup      Dump all data to backups/
#   restore     Restore from a backup
#   reset-pass  Reset admin password
#   add-user    Add a panel user
#   uninstall   Remove GnuKontrolR (data preserved)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$INSTALL_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
BLUE='\033[0;34m'; MAGENTA='\033[0;35m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'

info()    { echo -e "  ${CYAN}◆${NC}  $*"; }
ok()      { echo -e "  ${GREEN}✔${NC}  $*"; }
warn()    { echo -e "  ${YELLOW}⚠${NC}  $*"; }
die()     { echo -e "\n  ${RED}✘  ERROR:${NC} $*\n" >&2; exit 1; }
step()    { echo -e "\n${BOLD}${BLUE}  ┌─  $*${NC}"; }
done_step(){ echo -e "${BOLD}${GREEN}  └─  done${NC}"; }

banner() {
  echo -e "${BOLD}${MAGENTA}"
  echo '  ╔══════════════════════════════════════════════════════════╗'
  echo '  ║                                                          ║'
  echo '  ║    ██████╗ ███╗   ██╗██╗   ██╗██╗  ██╗                 ║'
  echo '  ║   ██╔════╝ ████╗  ██║██║   ██║██║ ██╔╝                 ║'
  echo '  ║   ██║  ███╗██╔██╗ ██║██║   ██║█████╔╝                  ║'
  echo '  ║   ██║   ██║██║╚██╗██║██║   ██║██╔═██╗                  ║'
  echo '  ║   ╚██████╔╝██║ ╚████║╚██████╔╝██║  ██╗                 ║'
  echo '  ║    ╚═════╝ ╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═╝                ║'
  echo '  ║                                                          ║'
  echo -e "  ║   ${CYAN}KontrolR${MAGENTA}  —  Web Hosting Control Panel            v1.0  ║"
  echo '  ╚══════════════════════════════════════════════════════════╝'
  echo -e "${NC}"
}

CMD="${1:-help}"

# ─── Helpers ──────────────────────────────────────────────────────────────────

dc() { docker compose "$@"; }

require_root() {
  [[ "$EUID" -eq 0 ]] || die "This command must be run as root (sudo bash setup.sh $CMD)"
}

require_env() {
  [[ -f .env ]] || die ".env not found. Run: bash setup.sh install"
}

gen_secret() {
  openssl rand -hex 48 2>/dev/null || tr -dc 'a-f0-9' </dev/urandom | head -c 96
}

# Spinner — run a command in background while showing | / - \ animation
# Usage: spin "label" cmd args...
spin() {
  local label="$1"; shift
  local chars='|/-\' i=0
  "$@" &>/tmp/gnukontrolr_spin_out &
  local pid=$!
  printf "  ${CYAN}◆${NC}  %s " "$label"
  while kill -0 "$pid" 2>/dev/null; do
    printf '\b%s' "${chars:$((i % 4)):1}"
    i=$((i+1))
    sleep 0.12
  done
  wait "$pid"
  local rc=$?
  if [[ $rc -eq 0 ]]; then
    printf '\b'"${GREEN}✔${NC}\n"
  else
    printf '\b'"${RED}✘${NC}\n"
    cat /tmp/gnukontrolr_spin_out >&2
  fi
  rm -f /tmp/gnukontrolr_spin_out
  return $rc
}

# Wait up to $1 seconds for a container health check to pass
wait_healthy() {
  local name="$1" timeout="${2:-120}" elapsed=0
  info "Waiting for $name to be healthy..."
  while ! docker inspect --format='{{.State.Health.Status}}' "$name" 2>/dev/null | grep -q "healthy"; do
    sleep 3; elapsed=$((elapsed+3))
    [[ $elapsed -lt $timeout ]] || { warn "$name did not become healthy in ${timeout}s"; return 1; }
  done
  ok "$name is healthy"
}

# ─── Install ──────────────────────────────────────────────────────────────────

cmd_install() {
  require_root
  banner

  echo -e "${BOLD}  Installation Checklist${NC}"
  echo -e "${DIM}  ──────────────────────────────────────────────────────────${NC}"
  echo -e "  ${DIM}Step 1${NC}  System packages & Docker Engine"
  echo -e "  ${DIM}Step 2${NC}  System users, groups"
  echo -e "  ${DIM}Step 3${NC}  Host directories & permissions"
  echo -e "  ${DIM}Step 4${NC}  Environment configuration (.env)"
  echo -e "  ${DIM}Step 5${NC}  Panel SSH keypair"
  echo -e "  ${DIM}Step 6${NC}  Docker image builds"
  echo -e "  ${DIM}Step 7${NC}  Start services & create admin account"
  echo -e "${DIM}  ──────────────────────────────────────────────────────────${NC}\n"

  step "Step 1 / 7 — System packages & Docker Engine"

  # Detect package manager
  if command -v apt-get &>/dev/null; then
    info "Updating package lists..."
    apt-get update -qq
    info "Installing base dependencies..."
    apt-get install -y -qq \
      curl wget git openssl ca-certificates gnupg \
      lsb-release software-properties-common \
      python3 python3-pip acl \
      2>/dev/null
    ok "Base packages installed"

    if ! command -v docker &>/dev/null; then
      info "Installing Docker Engine (official repo)..."
      install -m 0755 -d /etc/apt/keyrings
      curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null
      chmod a+r /etc/apt/keyrings/docker.gpg
      echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
        > /etc/apt/sources.list.d/docker.list
      apt-get update -qq
      apt-get install -y -qq \
        docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
      systemctl enable --now docker
      ok "Docker Engine installed"
    else
      ok "Docker already installed  ($(docker --version | awk '{print $3}' | tr -d ','))"
    fi

  elif command -v dnf &>/dev/null; then
    dnf install -y -q curl wget git openssl ca-certificates python3 python3-pip acl
    if ! command -v docker &>/dev/null; then
      dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
      dnf install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
      systemctl enable --now docker
      ok "Docker Engine installed"
    fi
  else
    warn "Unsupported package manager — install Docker Engine manually then re-run"
    warn "See: https://docs.docker.com/engine/install/"
  fi

  docker compose version &>/dev/null || die "docker compose plugin not found. Install docker-compose-plugin."
  ok "docker compose  $(docker compose version --short)"
  done_step

  # ── UID/GID constants ──────────────────────────────────────────────────────
  # panelapi user inside the webpanel container is UID/GID 999.
  # Host bind-mount dirs must be owned by numeric 999 so panelapi can r/w.
  PANEL_UID=999
  PANEL_GID=999
  # Docker socket GID — webpanel container uses group_add to gain access.
  DOCKER_SOCK_GID=$(stat -c '%g' /var/run/docker.sock 2>/dev/null || echo 984)

  step "Step 2 / 7 — System users & groups"

  # ── Groups ────────────────────────────────────────────────────────────────
  # gnukontrolr  (GID 999) — maps to panelapi inside containers
  if ! getent group gnukontrolr &>/dev/null; then
    groupadd -r -g "$PANEL_GID" gnukontrolr
    ok "Group 'gnukontrolr' created  (GID ${PANEL_GID})"
  else
    ok "Group 'gnukontrolr' exists   (GID $(getent group gnukontrolr | cut -d: -f3))"
  fi

  # docker  (GID = socket GID) — ensures host tools can also run docker commands
  if ! getent group docker &>/dev/null; then
    groupadd -g "$DOCKER_SOCK_GID" docker
    ok "Group 'docker' created       (GID ${DOCKER_SOCK_GID})"
  else
    ok "Group 'docker' exists        (GID $(getent group docker | cut -d: -f3))"
  fi

  # ── Service user ─────────────────────────────────────────────────────────
  # panelapi  (UID 999) — no login shell, no home, in gnukontrolr + docker groups
  if ! getent passwd panelapi &>/dev/null; then
    useradd -r -u "$PANEL_UID" -g gnukontrolr \
      -G docker \
      -s /usr/sbin/nologin \
      -d /var/webpanel \
      -c "GnuKontrolR panel service" \
      -M panelapi
    ok "User 'panelapi' created      (UID ${PANEL_UID}, groups: gnukontrolr,docker)"
  else
    # Ensure existing user is in the right groups
    usermod -aG docker,gnukontrolr panelapi 2>/dev/null || true
    ok "User 'panelapi' exists       (UID $(id -u panelapi 2>/dev/null || echo '?'))"
  fi

  done_step

  step "Step 3 / 7 — Host directories & permissions"

  # Format: "path:owner:group:mode:description"
  declare -a HOST_DIRS=(
    "/var/webpanel:root:root:755:webpanel root"
    "/var/webpanel/sites:${PANEL_UID}:gnukontrolr:755:customer web roots"
    "/var/webpanel/panel_ssh:${PANEL_UID}:gnukontrolr:700:panel SSH keypair (private)"
    "/var/webpanel/app-cache:${PANEL_UID}:gnukontrolr:755:marketplace app archive cache"
    "/var/webpanel/localdns:${PANEL_UID}:gnukontrolr:755:dnsmasq hosts file"
    "/var/webpanel/backups:root:root:750:panel-triggered backups"
    "/var/log/gnukontrolr:root:adm:755:panel host log files"
    "/etc/opendkim:root:root:755:OpenDKIM base dir"
    "/etc/opendkim/keys:${PANEL_UID}:gnukontrolr:750:DKIM private keys"
  )

  for entry in "${HOST_DIRS[@]}"; do
    IFS=':' read -r dir owner grp perms desc <<< "$entry"
    [[ -d "$dir" ]] || mkdir -p "$dir"
    chown "${owner}:${grp}" "$dir" 2>/dev/null || true
    chmod "$perms" "$dir"
    ok "$(printf '%-38s' "$dir")  ${owner}:${grp}  ${perms}  ${DIM}${desc}${NC}"
  done

  # Recursively fix ownership on any pre-existing content
  chown -R "${PANEL_UID}:gnukontrolr" /var/webpanel/sites     2>/dev/null || true
  chown -R "${PANEL_UID}:gnukontrolr" /var/webpanel/panel_ssh 2>/dev/null || true
  chown -R "${PANEL_UID}:gnukontrolr" /var/webpanel/app-cache 2>/dev/null || true
  chown -R "${PANEL_UID}:gnukontrolr" /var/webpanel/localdns  2>/dev/null || true
  chown -R "${PANEL_UID}:gnukontrolr" /etc/opendkim/keys      2>/dev/null || true

  done_step

  step "Step 4 / 7 — Environment (.env)"

  if [[ ! -f .env ]]; then
    info "Generating .env — please answer a few questions:"
    echo ""

    # Auto-detect server IP
    DETECTED_IP=$(ip -4 route get 8.8.8.8 2>/dev/null | grep -oP 'src \K[0-9.]+' || hostname -I | awk '{print $1}')

    echo -e "${DIM}  ─────────────────────────────────────────────────────────${NC}"
    read -rp "  Panel domain  (e.g. panel.example.com) : " PANEL_DOMAIN_VAL
    read -rp "  Server IP     [${DETECTED_IP}]         : " SERVER_IP_VAL
    SERVER_IP_VAL="${SERVER_IP_VAL:-$DETECTED_IP}"
    read -rp "  SSL email     (Let's Encrypt)           : " ACME_EMAIL_VAL
    read -rp "  Timezone      [UTC]                     : " TZ_VAL
    TZ_VAL="${TZ_VAL:-UTC}"
    echo -e "${DIM}  ─────────────────────────────────────────────────────────${NC}\n"

    info "Generating cryptographic secrets..."
    SECRET_KEY_VAL=$(gen_secret)
    CONTAINER_TOKEN_VAL=$(gen_secret)
    MYSQL_ROOT_PASS=$(gen_secret | head -c 32)
    MYSQL_PASS=$(gen_secret | head -c 32)
    REDIS_PASS=$(gen_secret | head -c 32)
    PDNS_KEY=$(gen_secret | head -c 64)
    GRAFANA_PASS=$(gen_secret | head -c 20)

    cat > .env <<EOF
# GnuKontrolR — Runtime Environment
# Generated by setup.sh install on $(date -u +%Y-%m-%dT%H:%M:%SZ)
# Keep this file secret (chmod 600).

# ── Panel ────────────────────────────────────────────────────────────────────
PANEL_DOMAIN=${PANEL_DOMAIN_VAL}
SERVER_IP=${SERVER_IP_VAL}
SECRET_KEY=${SECRET_KEY_VAL}
CONTAINER_API_TOKEN=${CONTAINER_TOKEN_VAL}
DEBUG_LEVEL=0

# ── MySQL ────────────────────────────────────────────────────────────────────
MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PASS}
MYSQL_PASSWORD=${MYSQL_PASS}

# ── Redis ────────────────────────────────────────────────────────────────────
REDIS_PASSWORD=${REDIS_PASS}

# ── PowerDNS ─────────────────────────────────────────────────────────────────
PDNS_API_KEY=${PDNS_KEY}

# ── Mail ─────────────────────────────────────────────────────────────────────
MAIL_HOSTNAME=mail.${PANEL_DOMAIN_VAL}
ALLOWED_SENDER_DOMAINS=${PANEL_DOMAIN_VAL}
RELAYHOST=

# ── Grafana ──────────────────────────────────────────────────────────────────
GRAFANA_USER=admin
GRAFANA_PASSWORD=${GRAFANA_PASS}

# ── Let's Encrypt ─────────────────────────────────────────────────────────────
ACME_EMAIL=${ACME_EMAIL_VAL}

# ── Timezone ─────────────────────────────────────────────────────────────────
TZ=${TZ_VAL}
EOF

    chmod 600 .env
    ok ".env generated  (secrets randomised, mode 600)"
  else
    ok ".env exists — skipping generation"
  fi

  # Always sync PDNS_API_KEY from .env → pdns.conf
  PDNS_KEY_LIVE=$(grep '^PDNS_API_KEY=' .env | cut -d= -f2-)
  if [[ -n "$PDNS_KEY_LIVE" ]] && [[ -f docker/powerdns/pdns.conf ]]; then
    sed -i "s/^api-key=.*/api-key=${PDNS_KEY_LIVE}/" docker/powerdns/pdns.conf
    ok "pdns.conf api-key synced"
  fi

  done_step

  step "Step 5 / 7 — Panel SSH keypair"

  PANEL_SSH_DIR=/var/webpanel/panel_ssh
  if [[ ! -f "${PANEL_SSH_DIR}/id_ecdsa" ]]; then
    ssh-keygen -t ecdsa -b 521 -N "" \
      -C "gnukontrolr-panel-$(date +%Y%m%d)" \
      -f "${PANEL_SSH_DIR}/id_ecdsa" -q
    chown -R "${PANEL_UID}:gnukontrolr" "${PANEL_SSH_DIR}"
    chmod 700 "${PANEL_SSH_DIR}"
    chmod 600 "${PANEL_SSH_DIR}/id_ecdsa"
    chmod 644 "${PANEL_SSH_DIR}/id_ecdsa.pub"
    ok "ECDSA-521 keypair generated  →  ${PANEL_SSH_DIR}/id_ecdsa"
  else
    ok "Panel SSH keypair already exists"
  fi

  done_step

  step "Step 6 / 7 — Docker image builds"

  spin "Pulling nginx:alpine"   docker pull nginx:alpine   --quiet
  spin "Pulling mysql:8.4"      docker pull mysql:8.4      --quiet
  spin "Pulling redis:8-alpine" docker pull redis:8-alpine --quiet
  spin "Pulling traefik:v3.3"   docker pull traefik:v3.3   --quiet

  echo ""
  for ver in 8.1 8.2 8.3 8.4; do
    spin "Building webpanel/php-site:${ver}" \
      docker build --build-arg PHP_VERSION="${ver}" \
        -t "webpanel/php-site:${ver}" docker/site-template/ --quiet \
      || warn "webpanel/php-site:${ver} failed — skipping"
  done

  echo ""
  spin "Building localdns (dnsmasq)" \
    docker build -t webpanel/localdns docker/localdns/ --quiet

  echo ""
  spin "Building panel API + frontend  (this takes ~1 min)" \
    docker compose build --no-cache webpanel
  ok "gnukontrolr-webpanel image built"

  # Extract compiled frontend from image to host bind-mount path
  info "Extracting frontend dist to ./frontend/dist ..."
  CID=$(docker create gnukontrolr-webpanel)
  docker cp "${CID}:/app/frontend/dist/." ./frontend/dist/
  docker rm "$CID" >/dev/null
  ok "Frontend dist ready"

  done_step

  step "Step 7 / 7 — Start services & create admin account"

  info "Starting all services..."
  dc up -d --remove-orphans
  ok "Services started"

  wait_healthy webpanel_mysql 120 || true
  info "Waiting for panel API to initialise database..."
  sleep 8

  echo ""
  echo -e "${DIM}  ─────────────────────────────────────────────────────────${NC}"
  info "Creating superadmin account:"
  read -rp "  Username  [admin] : " ADMIN_USER;  ADMIN_USER="${ADMIN_USER:-admin}"
  read -rp "  Email             : " ADMIN_EMAIL
  read -rsp "  Password          : " ADMIN_PASS;  echo
  read -rsp "  Confirm           : " ADMIN_PASS2; echo
  [[ "$ADMIN_PASS" == "$ADMIN_PASS2" ]] || die "Passwords do not match"
  echo -e "${DIM}  ─────────────────────────────────────────────────────────${NC}\n"

  dc exec -T webpanel python3 - <<PYEOF
import asyncio, sys
sys.path.insert(0, '/app')
from app.database import init_db, AsyncSessionLocal
from app.models.user import User, Role
from app.auth import hash_password
from sqlalchemy import select

async def main():
    await init_db()
    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(User).where(User.username == '${ADMIN_USER}'))).scalar_one_or_none()
        if existing:
            existing.hashed_password = hash_password('${ADMIN_PASS}')
            existing.role = Role.superadmin
            existing.is_active = True
        else:
            db.add(User(
                username='${ADMIN_USER}',
                email='${ADMIN_EMAIL}',
                hashed_password=hash_password('${ADMIN_PASS}'),
                role=Role.superadmin,
                is_active=True,
            ))
        await db.commit()
        print("ok")

asyncio.run(main())
PYEOF

  ok "Superadmin '${ADMIN_USER}' ready"
  done_step

  _DOMAIN=$(grep '^PANEL_DOMAIN=' .env | cut -d= -f2-)
  _IP=$(grep '^SERVER_IP=' .env | cut -d= -f2-)

  echo ""
  echo -e "${BOLD}${GREEN}"
  echo '  ╔══════════════════════════════════════════════════════════╗'
  echo -e "  ║  ${NC}${BOLD}  Installation complete!${GREEN}                               ║"
  echo '  ╠══════════════════════════════════════════════════════════╣'
  echo -e "  ║  Panel URL  ${CYAN}https://${_DOMAIN}${GREEN}$(printf '%*s' $((29 - ${#_DOMAIN})) '')║"
  echo -e "  ║  API direct ${CYAN}http://${_IP}:8000${GREEN}$(printf '%*s' $((30 - ${#_IP})) '')║"
  echo -e "  ║  Admin user ${CYAN}${ADMIN_USER}${GREEN}$(printf '%*s' $((40 - ${#ADMIN_USER})) '')║"
  echo '  ╠══════════════════════════════════════════════════════════╣'
  echo -e "  ║  ${NC}${YELLOW}Next steps:${GREEN}                                           ║"
  echo -e "  ║  ${NC}1. Point DNS A-record for ${_DOMAIN} → ${_IP}${GREEN}$(printf '%*s' $((1)) '')║"
  echo    '  ║  2. Open ports: 80 443 25 587 143 993 110 995 53       ║'
  echo    '  ║  3. Traefik will auto-issue SSL once DNS resolves       ║'
  echo    '  ║  4. Local DNS test:                                     ║'
  echo -e "  ║     ${NC}dig @${_IP} -p 5335 ${_DOMAIN}${GREEN}$(printf '%*s' $((1)) '')║"
  echo '  ╚══════════════════════════════════════════════════════════╝'
  echo -e "${NC}"
  echo -e "  ${YELLOW}Next steps:${NC}"
  echo -e "  1. Point your domain's DNS A-record to $(grep '^SERVER_IP=' .env | cut -d= -f2-)"
  echo -e "  2. Open port 80/443/25/587/143/993/110/995/53 in your firewall"
  echo -e "  3. Traefik will auto-issue Let's Encrypt certs once DNS resolves"
  echo ""
}

# ─── Commands ────────────────────────────────────────────────────────────────

cmd_start() {
  require_env
  info "Starting GnuKontrolR..."
  dc up -d
  ok "All services running"
  cmd_status
}

cmd_stop() {
  info "Stopping GnuKontrolR..."
  dc stop
  ok "Stopped"
}

cmd_restart() {
  require_env
  info "Restarting services..."
  dc restart
  ok "Restarted"
  cmd_status
}

cmd_status() {
  dc ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
}

cmd_logs() {
  shift || true
  dc logs -f --tail=100 "$@"
}

cmd_update() {
  require_env
  banner
  step "Update — pulling latest code"
  git pull --ff-only
  ok "Code up to date  ($(git log -1 --format='%h %s'))"
  done_step

  step "Update — rebuilding images"
  info "Pulling updated base images..."
  dc pull --quiet

  info "Rebuilding panel API + frontend..."
  dc build --no-cache webpanel
  ok "Panel image rebuilt"

  info "Extracting frontend dist..."
  CID=$(docker create gnukontrolr-webpanel)
  docker cp "${CID}:/app/frontend/dist/." ./frontend/dist/
  docker rm "$CID" >/dev/null
  ok "Frontend dist updated"
  done_step

  step "Update — restarting containers"
  dc up -d --build --remove-orphans
  ok "All containers running"
  done_step

  echo -e "\n  ${GREEN}${BOLD}Update complete.${NC}\n"
}

cmd_repair() {
  require_root
  require_env
  banner
  step "Repair — host directories & permissions"

  PANEL_UID=999; PANEL_GID=999

  declare -a REPAIR_DIRS=(
    "/var/webpanel:root:root:755"
    "/var/webpanel/sites:${PANEL_UID}:gnukontrolr:755"
    "/var/webpanel/panel_ssh:${PANEL_UID}:gnukontrolr:700"
    "/var/webpanel/app-cache:${PANEL_UID}:gnukontrolr:755"
    "/var/webpanel/localdns:${PANEL_UID}:gnukontrolr:755"
    "/var/webpanel/backups:root:root:750"
    "/var/log/gnukontrolr:root:adm:755"
    "/etc/opendkim:root:root:755"
    "/etc/opendkim/keys:${PANEL_UID}:gnukontrolr:750"
  )

  for entry in "${REPAIR_DIRS[@]}"; do
    IFS=':' read -r dir owner grp perms <<< "$entry"
    [[ -d "$dir" ]] || { mkdir -p "$dir"; info "Created $dir"; }
    chown "${owner}:${grp}" "$dir" 2>/dev/null || true
    chmod "$perms" "$dir"
    ok "$(printf '%-38s' "$dir")  ${owner}:${grp}  ${perms}"
  done

  # Recurse into dirs owned by panelapi
  for d in /var/webpanel/sites /var/webpanel/panel_ssh /var/webpanel/app-cache \
            /var/webpanel/localdns /etc/opendkim/keys; do
    chown -R "${PANEL_UID}:gnukontrolr" "$d" 2>/dev/null || true
  done

  # Panel SSH key permissions
  [[ -f /var/webpanel/panel_ssh/id_ecdsa ]] && \
    chmod 600 /var/webpanel/panel_ssh/id_ecdsa && \
    chmod 644 /var/webpanel/panel_ssh/id_ecdsa.pub 2>/dev/null || true
  done_step

  step "Repair — groups & users"
  DOCKER_SOCK_GID=$(stat -c '%g' /var/run/docker.sock 2>/dev/null || echo 984)
  getent group gnukontrolr &>/dev/null || groupadd -r -g "$PANEL_GID" gnukontrolr
  getent group docker       &>/dev/null || groupadd    -g "$DOCKER_SOCK_GID" docker
  getent passwd panelapi    &>/dev/null || \
    useradd -r -u "$PANEL_UID" -g gnukontrolr -G docker -s /usr/sbin/nologin \
            -d /var/webpanel -c "GnuKontrolR panel service" -M panelapi
  usermod -aG docker,gnukontrolr panelapi 2>/dev/null || true
  ok "Users and groups verified"
  done_step

  step "Repair — PowerDNS API key sync"
  PDNS_KEY_LIVE=$(grep '^PDNS_API_KEY=' .env | cut -d= -f2-)
  if [[ -n "$PDNS_KEY_LIVE" ]] && [[ -f docker/powerdns/pdns.conf ]]; then
    sed -i "s/^api-key=.*/api-key=${PDNS_KEY_LIVE}/" docker/powerdns/pdns.conf
    ok "pdns.conf api-key synced"
  fi
  done_step

  step "Repair — MySQL database & user"
  if dc ps mysql 2>/dev/null | grep -q "running"; then
    MYSQL_ROOT=$(grep '^MYSQL_ROOT_PASSWORD=' .env | cut -d= -f2-)
    MYSQL_PASS=$(grep '^MYSQL_PASSWORD='      .env | cut -d= -f2-)
    dc exec -T mysql mysql -u root -p"${MYSQL_ROOT}" 2>/dev/null <<SQL || true
CREATE DATABASE IF NOT EXISTS webpanel CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'webpanel'@'%' IDENTIFIED BY '${MYSQL_PASS}';
GRANT ALL PRIVILEGES ON webpanel.* TO 'webpanel'@'%';
FLUSH PRIVILEGES;
SQL
    ok "MySQL: database 'webpanel' and user verified"
  else
    warn "MySQL not running — skipping DB repair"
  fi
  done_step

  step "Repair — container restart"
  dc up -d --remove-orphans
  ok "All services running"
  done_step

  echo -e "\n  ${GREEN}${BOLD}Repair complete.${NC}\n"
}

cmd_test() {
  require_env
  banner
  local PASS=0 FAIL=0
  _pass() { echo -e "  ${GREEN}✔${NC}  $*"; PASS=$((PASS+1)); }
  _fail() { echo -e "  ${RED}✘${NC}  $*"; FAIL=$((FAIL+1)); }
  _test() {
    local desc="$1"; shift
    if "$@" &>/dev/null; then _pass "$desc"; else _fail "$desc"; fi
  }

  step "System"
  _test "Docker running"              docker info
  _test "docker compose available"    docker compose version
  _test ".env exists"                 test -f .env
  _test "Panel SSH key exists"        test -f /var/webpanel/panel_ssh/id_ecdsa
  _test "/var/webpanel/sites exists"  test -d /var/webpanel/sites
  _test "/var/webpanel/localdns exists" test -d /var/webpanel/localdns
  done_step

  step "Containers"
  for svc in webpanel_api webpanel_mysql webpanel_redis webpanel_traefik \
             webpanel_powerdns webpanel_localdns webpanel_opendkim \
             webpanel_docker_api_proxy; do
    _test "$svc running" docker inspect --format='{{.State.Running}}' "$svc" | grep -q true
  done
  done_step

  step "API endpoints"
  API="http://localhost:8000"

  # Login
  TOKEN=$(curl -sf -X POST "$API/api/auth/token" \
    -d "username=admin&password=test123" 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)

  if [[ -n "$TOKEN" ]]; then
    _pass "POST /api/auth/token  (login)"
  else
    _fail "POST /api/auth/token  (login — check admin password)"
  fi

  AUTH_H="Authorization: Bearer ${TOKEN}"

  _test "GET  /api/docker/containers" \
    curl -sf -H "$AUTH_H" "$API/api/docker/containers"
  _test "GET  /api/docker/stats" \
    curl -sf -H "$AUTH_H" "$API/api/docker/stats"
  _test "GET  /api/localdns/hosts" \
    curl -sf -H "$AUTH_H" "$API/api/localdns/hosts"
  _test "GET  /api/server/stats" \
    curl -sf -H "$AUTH_H" "$API/api/server/stats"
  _test "GET  /api/dns/zones" \
    curl -sf -H "$AUTH_H" "$API/api/dns/zones"
  done_step

  step "DNS & mail"
  SERVER_IP_VAL=$(grep '^SERVER_IP=' .env | cut -d= -f2-)
  _test "localdns responds on port 5335" \
    dig @"$SERVER_IP_VAL" -p 5335 +time=3 +tries=1 version.bind CHAOS TXT
  done_step

  step "Docker socket proxy"
  _test "docker-api-proxy /version" \
    docker exec webpanel_docker_api_proxy curl -sf http://localhost:2375/version
  _test "docker-api-proxy v1.24 rewrite" \
    docker exec webpanel_docker_api_proxy curl -sf http://localhost:2375/v1.24/version
  done_step

  step "Local virtual DNS — end-to-end test"
  SERVER_IP_TEST=$(grep '^SERVER_IP=' .env | cut -d= -f2-)
  PANEL_DOM=$(grep '^PANEL_DOMAIN=' .env | cut -d= -f2-)

  # Resolve panel domain via local dnsmasq on port 5335
  RESOLVED=$(dig @"$SERVER_IP_TEST" -p 5335 +short +time=3 +tries=1 "$PANEL_DOM" 2>/dev/null | head -1 || true)
  if [[ "$RESOLVED" == "$SERVER_IP_TEST" ]]; then
    _pass "localdns resolves ${PANEL_DOM} → ${RESOLVED}"
  elif [[ -n "$RESOLVED" ]]; then
    _pass "localdns resolves ${PANEL_DOM} → ${RESOLVED}  (expected ${SERVER_IP_TEST})"
  else
    _fail "localdns did not resolve ${PANEL_DOM}  (is webpanel_localdns running?)"
  fi

  # Test a domain that was seeded by the panel (first in DB if any)
  if [[ -n "$TOKEN" ]]; then
    FIRST_DOMAIN=$(curl -sf -H "Authorization: Bearer ${TOKEN}" \
      http://localhost:8000/api/dns/zones 2>/dev/null \
      | python3 -c "import sys,json; z=json.load(sys.stdin); print(z[0].get('name','').rstrip('.')) if z else print('')" 2>/dev/null || true)

    if [[ -n "$FIRST_DOMAIN" ]]; then
      DOM_IP=$(dig @"$SERVER_IP_TEST" -p 5335 +short +time=3 +tries=1 "$FIRST_DOMAIN" 2>/dev/null | head -1 || true)
      if [[ -n "$DOM_IP" ]]; then
        _pass "localdns resolves ${FIRST_DOMAIN} → ${DOM_IP}"
      else
        _fail "localdns did not resolve ${FIRST_DOMAIN}"
      fi
    else
      info  "No customer domains provisioned yet — skipping domain DNS test"
    fi
  fi
  done_step

  echo ""
  echo -e "${DIM}  ──────────────────────────────────────${NC}"
  echo -e "  ${GREEN}${BOLD}Passed: ${PASS}${NC}   ${RED}${BOLD}Failed: ${FAIL}${NC}"
  if [[ $FAIL -eq 0 ]]; then
    echo -e "\n  ${GREEN}${BOLD}All tests passed.${NC}\n"
  else
    echo -e "\n  ${YELLOW}Some tests failed — check output above.${NC}\n"
    return 1
  fi
}

cmd_backup() {
  require_env
  BACKUP_DIR="$INSTALL_DIR/backups/$(date +%Y%m%d_%H%M%S)"
  mkdir -p "$BACKUP_DIR"

  info "Backing up MySQL..."
  dc exec -T mysql mysqldump \
    -u root -p"$(grep MYSQL_ROOT_PASSWORD .env | cut -d= -f2)" \
    --all-databases --single-transaction 2>/dev/null \
    > "$BACKUP_DIR/mysql_all.sql"

  info "Backing up .env..."
  cp .env "$BACKUP_DIR/env.bak"

  info "Backing up Docker volumes list..."
  docker volume ls --filter name=gnukontrolr > "$BACKUP_DIR/volumes.txt" 2>/dev/null || true
  docker volume ls --filter name=webpanel    >> "$BACKUP_DIR/volumes.txt" 2>/dev/null || true

  ok "Backup saved to $BACKUP_DIR"
}

cmd_restore() {
  require_env
  BACKUP_DIR="${2:-}"
  if [[ -z "$BACKUP_DIR" ]]; then
    echo "Available backups:"
    ls -1 "$INSTALL_DIR/backups/" 2>/dev/null || die "No backups found"
    read -rp "Enter backup folder name: " BACKUP_DIR
    BACKUP_DIR="$INSTALL_DIR/backups/$BACKUP_DIR"
  fi
  [[ -f "$BACKUP_DIR/mysql_all.sql" ]] || die "No mysql_all.sql in $BACKUP_DIR"

  warn "This will overwrite all databases. Continue? [y/N]"
  read -r CONFIRM
  [[ "$CONFIRM" =~ ^[Yy]$ ]] || { info "Aborted"; exit 0; }

  info "Restoring MySQL..."
  dc exec -T mysql mysql \
    -u root -p"$(grep MYSQL_ROOT_PASSWORD .env | cut -d= -f2)" \
    < "$BACKUP_DIR/mysql_all.sql"

  ok "Restore complete"
}

cmd_reset_pass() {
  require_env
  read -rp "Username to reset: " UNAME
  read -rsp "New password: " NPASS; echo
  read -rsp "Confirm: " NPASS2; echo
  [[ "$NPASS" == "$NPASS2" ]] || die "Passwords do not match"

  dc exec -T webpanel python3 - <<PYEOF
import asyncio, sys
sys.path.insert(0, '/app')
from app.database import init_db, AsyncSessionLocal
from app.models.user import User
from app.auth import hash_password
from sqlalchemy import select

async def main():
    await init_db()
    async with AsyncSessionLocal() as db:
        u = (await db.execute(select(User).where(User.username == '${UNAME}'))).scalar_one_or_none()
        if not u:
            print('User not found'); return
        u.hashed_password = hash_password('${NPASS}')
        await db.commit()
        print(f'Password updated for {u.username}')

asyncio.run(main())
PYEOF
}

cmd_add_user() {
  require_env
  read -rp "New username: " UNAME
  read -rp "Email: " UEMAIL
  read -rsp "Password: " UPASS; echo
  read -rp "Role [user/admin/reseller/superadmin] (default: user): " UROLE
  UROLE="${UROLE:-user}"

  dc exec -T webpanel python3 - <<PYEOF
import asyncio, sys
sys.path.insert(0, '/app')
from app.database import init_db, AsyncSessionLocal
from app.models.user import User, Role
from app.auth import hash_password
from sqlalchemy import select

async def main():
    await init_db()
    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(User).where(User.username == '${UNAME}'))).scalar_one_or_none()
        if existing:
            print('User already exists'); return
        try:
            role = Role('${UROLE}')
        except ValueError:
            print(f'Invalid role: ${UROLE}. Valid: user, admin, reseller, superadmin'); return
        user = User(
            username='${UNAME}',
            email='${UEMAIL}',
            hashed_password=hash_password('${UPASS}'),
            role=role,
        )
        db.add(user)
        await db.commit()
        print(f'User ${UNAME} created (role=${UROLE})')

asyncio.run(main())
PYEOF
}

cmd_uninstall() {
  warn "This will remove all containers and images (data volumes preserved)."
  warn "To also remove data: docker volume rm \$(docker volume ls -q | grep webpanel)"
  read -rp "Continue? [y/N]: " CONFIRM
  [[ "$CONFIRM" =~ ^[Yy]$ ]] || { info "Aborted"; exit 0; }
  dc down --rmi local
  ok "GnuKontrolR removed. Data volumes still exist."
}

cmd_help() {
  banner
  echo -e "${BOLD}  Usage:  sudo bash setup.sh <command>${NC}"
  echo ""
  echo -e "  ${BOLD}${CYAN}Lifecycle${NC}"
  echo -e "  ${CYAN}  install${NC}        Full first-time install — packages, users, dirs, build, start"
  echo -e "  ${CYAN}  update${NC}         Pull latest git code, rebuild images, restart"
  echo -e "  ${CYAN}  repair${NC}         Fix permissions, groups, DB users, resync configs"
  echo -e "  ${CYAN}  uninstall${NC}      Remove containers and images (data volumes preserved)"
  echo ""
  echo -e "  ${BOLD}${CYAN}Service control${NC}"
  echo -e "  ${CYAN}  start${NC}          Start all services"
  echo -e "  ${CYAN}  stop${NC}           Stop all services"
  echo -e "  ${CYAN}  restart${NC}        Restart all services"
  echo -e "  ${CYAN}  status${NC}         Show container status table"
  echo -e "  ${CYAN}  logs [svc]${NC}     Tail logs (optionally for one service)"
  echo ""
  echo -e "  ${BOLD}${CYAN}Data${NC}"
  echo -e "  ${CYAN}  backup${NC}         Dump MySQL + .env to backups/"
  echo -e "  ${CYAN}  restore${NC}        Restore from a backup"
  echo ""
  echo -e "  ${BOLD}${CYAN}Users${NC}"
  echo -e "  ${CYAN}  reset-pass${NC}     Reset a panel user's password"
  echo -e "  ${CYAN}  add-user${NC}       Create a new panel user"
  echo ""
  echo -e "  ${BOLD}${CYAN}Diagnostics${NC}"
  echo -e "  ${CYAN}  test${NC}           Run end-to-end test suite (containers, API, DNS)"
  echo ""
  echo -e "  ${DIM}First time?  →  sudo bash setup.sh install${NC}"
  echo ""
}

# ─── Dispatch ────────────────────────────────────────────────────────────────

case "$CMD" in
  install)          cmd_install ;;
  update|--update)  cmd_update ;;
  repair|--repair)  cmd_repair ;;
  test|--test)      cmd_test ;;
  start)            cmd_start ;;
  stop)             cmd_stop ;;
  restart)          cmd_restart ;;
  status)           cmd_status ;;
  logs)             cmd_logs "$@" ;;
  backup)           cmd_backup ;;
  restore)          cmd_restore "$@" ;;
  reset-pass)       cmd_reset_pass ;;
  add-user)         cmd_add_user ;;
  uninstall)        cmd_uninstall ;;
  help|--help|-h)   cmd_help ;;
  *) warn "Unknown command: $CMD"; cmd_help; exit 1 ;;
esac
