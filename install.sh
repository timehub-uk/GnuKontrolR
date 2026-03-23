#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# GnuKontrolR — Installer
# Usage: curl -sSL https://raw.githubusercontent.com/timehub-uk/GnuKontrolR/master/install.sh | bash
#   or:  bash install.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()     { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }
header()  { echo -e "\n${BOLD}${CYAN}▶ $*${NC}"; }

INSTALL_DIR="${INSTALL_DIR:-/opt/gnukontrolr}"
REPO_URL="https://github.com/timehub-uk/GnuKontrolR.git"
MIN_DOCKER="24.0"
MIN_COMPOSE="2.20"

# When piped from curl, BASH_SOURCE[0] is not a file — detect this so we can
# clone the repo and re-exec the real install.sh from inside it.
RUNNING_FROM_CURL=false
_src="${BASH_SOURCE[0]:-}"
[[ -z "$_src" || "$_src" == "/dev/stdin" || "$_src" == "bash" || ! -f "$_src" ]] && RUNNING_FROM_CURL=true

# ─── Banner ───────────────────────────────────────────────────────────────────
echo -e "${BOLD}"
cat <<'EOF'
  ____            _  __            _             _  ____
 / ___| _ __  _  | |/ / ___  _ _ | |_ _ __ ___ | ||  _ \
| |  _ | '_ \| | | ' / / _ \| '_|| __| '__/ _ \| || |_) |
| |_| || | | | |_| . \| (_) | |  | |_| | | (_) | ||  _ <
 \____||_| |_|\___/_|\_\\___/|_|   \__|_|  \___/|_||_| \_\

         Multi-domain Web Hosting Control Panel
EOF
echo -e "${NC}"

# ─── Root check ──────────────────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || die "Run as root: sudo bash install.sh"

# ─── If piped from curl: clone first, then re-exec the real install.sh ───────
if $RUNNING_FROM_CURL; then
  header "Bootstrapping from curl"
  need_curl() { command -v curl &>/dev/null || { apt-get update -qq && apt-get install -y -qq curl; }; }
  need_git()  { command -v git  &>/dev/null || { apt-get update -qq && apt-get install -y -qq git;  }; }
  need_curl; need_git

  if [[ -d "$INSTALL_DIR/.git" ]]; then
    info "Updating existing install at $INSTALL_DIR..."
    git -C "$INSTALL_DIR" pull --ff-only
  else
    info "Cloning GnuKontrolR to $INSTALL_DIR..."
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone "$REPO_URL" "$INSTALL_DIR"
  fi
  ok "Repository ready"
  info "Re-running installer from $INSTALL_DIR/install.sh..."
  exec bash "$INSTALL_DIR/install.sh"
fi

# ─── OS check ────────────────────────────────────────────────────────────────
header "Checking system"
if [[ -f /etc/os-release ]]; then
  . /etc/os-release
  info "Detected OS: $PRETTY_NAME"
  case "$ID" in
    ubuntu|debian) PKG=apt ;;
    centos|rhel|fedora|rocky|almalinux) PKG=dnf ;;
    *) warn "Untested OS '$ID' — proceeding anyway"; PKG=apt ;;
  esac
else
  die "Cannot detect OS. /etc/os-release not found."
fi

# ─── Dependency checks ───────────────────────────────────────────────────────
header "Checking dependencies"

need_pkg() {
  local cmd=$1 pkg=${2:-$1}
  if ! command -v "$cmd" &>/dev/null; then
    warn "$cmd not found — installing..."
    if [[ $PKG == apt ]]; then
      apt-get update -qq && apt-get install -y -qq "$pkg"
    else
      dnf install -y "$pkg"
    fi
  fi
  ok "$cmd is available"
}

need_pkg curl
need_pkg git
need_pkg openssl
need_pkg python3

# Docker
if ! command -v docker &>/dev/null; then
  warn "Docker not found — installing via get.docker.com..."
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
fi
DOCKER_VER=$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo "0")
ok "Docker $DOCKER_VER"

# Docker Compose (plugin)
if ! docker compose version &>/dev/null; then
  warn "Docker Compose plugin not found — installing..."
  if [[ $PKG == apt ]]; then
    apt-get install -y -qq docker-compose-plugin
  else
    dnf install -y docker-compose-plugin
  fi
fi
ok "Docker Compose $(docker compose version --short 2>/dev/null)"

# ─── Clone / update repo ─────────────────────────────────────────────────────
header "Setting up files"

if [[ -d "$INSTALL_DIR/.git" ]]; then
  info "Existing installation found at $INSTALL_DIR — pulling latest..."
  git -C "$INSTALL_DIR" pull --ff-only
else
  info "Cloning to $INSTALL_DIR..."
  git clone "$REPO_URL" "$INSTALL_DIR"
fi
ok "Files ready at $INSTALL_DIR"

cd "$INSTALL_DIR"

# ─── Generate .env ───────────────────────────────────────────────────────────
header "Configuring environment"

if [[ -f .env ]]; then
  warn ".env already exists — skipping generation (delete it to regenerate)"
else
  info "Generating secure .env..."

  gen_secret() { openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | head -c 48; }

  # Interactive prompts
  read -rp "  Panel domain (e.g. panel.example.com): " PANEL_DOMAIN
  read -rp "  Mail hostname (e.g. mail.example.com): " MAIL_HOST
  read -rp "  Let's Encrypt email: " ACME_EMAIL
  read -rp "  Timezone [UTC]: " TZ_INPUT
  TZ_INPUT="${TZ_INPUT:-UTC}"

  cat > .env <<ENVEOF
# Generated by install.sh on $(date -u +"%Y-%m-%d %Human:%M UTC")

# ── Panel ────────────────────────────────────────────────────────────────────
SECRET_KEY=$(gen_secret)
CONTAINER_API_TOKEN=$(gen_secret)
PANEL_DOMAIN=${PANEL_DOMAIN}
ENVIRONMENT=production
PANEL_ORIGIN=https://${PANEL_DOMAIN}

# ── MySQL ────────────────────────────────────────────────────────────────────
MYSQL_ROOT_PASSWORD=$(gen_secret)
MYSQL_PASSWORD=$(gen_secret)

# ── Redis ────────────────────────────────────────────────────────────────────
REDIS_PASSWORD=$(gen_secret)

# ── PowerDNS ─────────────────────────────────────────────────────────────────
PDNS_API_KEY=$(gen_secret)

# ── Mail ─────────────────────────────────────────────────────────────────────
MAIL_HOSTNAME=${MAIL_HOST}
ALLOWED_SENDER_DOMAINS=${MAIL_HOST#mail.}

# ── Grafana ──────────────────────────────────────────────────────────────────
GRAFANA_USER=admin
GRAFANA_PASSWORD=$(gen_secret)

# ── Let's Encrypt ─────────────────────────────────────────────────────────────
ACME_EMAIL=${ACME_EMAIL}

# ── Timezone ─────────────────────────────────────────────────────────────────
TZ=${TZ_INPUT}
ENVEOF

  chmod 600 .env
  ok ".env written (secrets auto-generated)"
fi

# ─── Build frontend ──────────────────────────────────────────────────────────
header "Building frontend"

if command -v node &>/dev/null; then
  cd frontend
  info "Installing npm packages..."
  npm ci --silent
  info "Building React app..."
  npm run build --silent
  cd ..
  ok "Frontend built → frontend/dist/"
else
  warn "Node.js not found — skipping frontend build. Run manually:"
  warn "  cd $INSTALL_DIR/frontend && npm ci && npm run build"
fi

# ─── Start stack ─────────────────────────────────────────────────────────────
header "Starting services"

docker compose pull --quiet
docker compose up -d --build --remove-orphans

ok "All services started"

# ─── Wait for API ─────────────────────────────────────────────────────────────
header "Waiting for panel API"
MAX=30; i=0
until curl -sf http://localhost:8000/api/health &>/dev/null || [[ $i -ge $MAX ]]; do
  echo -n "."; sleep 2; ((i++))
done
echo
if [[ $i -ge $MAX ]]; then
  warn "API not responding yet — check: docker compose logs webpanel"
else
  ok "API is up"
fi

# ─── Create admin user ───────────────────────────────────────────────────────
header "Admin account"

read -rp "  Admin username [admin]: " ADMIN_USER
ADMIN_USER="${ADMIN_USER:-admin}"
read -rsp "  Admin password: " ADMIN_PASS; echo
read -rsp "  Confirm password: " ADMIN_PASS2; echo
[[ "$ADMIN_PASS" == "$ADMIN_PASS2" ]] || die "Passwords do not match"

docker compose exec -T webpanel python3 - <<PYEOF
import asyncio, sys
sys.path.insert(0, '/app')
from app.database import init_db, AsyncSessionLocal
from app.models.user import User
from app.auth import hash_password
from sqlalchemy import select

async def create_admin():
    await init_db()
    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(User).where(User.username == '${ADMIN_USER}'))).scalar_one_or_none()
        if existing:
            print('Admin user already exists — skipping')
            return
        user = User(username='${ADMIN_USER}', hashed_password=hash_password('${ADMIN_PASS}'), is_admin=True)
        db.add(user)
        await db.commit()
        print('Admin user created')

asyncio.run(create_admin())
PYEOF

# ─── Done ────────────────────────────────────────────────────────────────────
PANEL_DOMAIN_VAL=$(grep PANEL_DOMAIN .env 2>/dev/null | cut -d= -f2 | head -1)

echo ""
echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}${BOLD}  GnuKontrolR installed successfully!${NC}"
echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  Panel URL   : ${CYAN}https://${PANEL_DOMAIN_VAL:-your-domain}${NC}"
echo -e "  Grafana     : ${CYAN}https://${PANEL_DOMAIN_VAL:-your-domain}/grafana${NC}"
echo -e "  Admin user  : ${YELLOW}${ADMIN_USER}${NC}"
echo ""
echo -e "  Manage with : ${BOLD}cd $INSTALL_DIR && docker compose [up|down|logs]${NC}"
echo ""
echo -e "${YELLOW}  ⚠  Keep .env secure — it contains all secrets${NC}"
echo ""

# ─── Launch browser ──────────────────────────────────────────────────────────
PANEL_URL="https://${PANEL_DOMAIN_VAL:-localhost}"

open_browser() {
  # Try common browser launchers in order
  for cmd in xdg-open open sensible-browser gnome-open x-www-browser; do
    if command -v "$cmd" &>/dev/null; then
      info "Opening $PANEL_URL in browser..."
      nohup "$cmd" "$PANEL_URL" &>/dev/null &
      return 0
    fi
  done
  # No GUI browser available (headless server) — print instructions instead
  warn "No graphical browser detected."
  info "Open this URL in your browser: ${CYAN}${PANEL_URL}${NC}"
}

open_browser
