#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# GnuKontrolR — Post-install setup / management helper
# Usage: bash setup.sh [command]
#
# Commands:
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

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()   { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

CMD="${1:-help}"

# ─── Helpers ─────────────────────────────────────────────────────────────────

dc() { docker compose "$@"; }

require_env() {
  [[ -f .env ]] || die ".env not found. Run install.sh first."
}

run_py() {
  dc exec -T webpanel python3 - <<PYEOF
import asyncio, sys
sys.path.insert(0, '/app')
from app.database import init_db, AsyncSessionLocal
from app.models.user import User
from app.auth import hash_password
from sqlalchemy import select

$1

asyncio.run(main())
PYEOF
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
  info "Pulling latest code..."
  git pull --ff-only

  info "Rebuilding frontend..."
  if command -v node &>/dev/null; then
    cd frontend && npm ci --silent && npm run build --silent && cd ..
    ok "Frontend rebuilt"
  else
    warn "Node.js not available — skipping frontend rebuild"
  fi

  info "Rebuilding and restarting containers..."
  dc pull --quiet
  dc up -d --build --remove-orphans
  ok "Update complete"
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
  read -rsp "Password: " UPASS; echo
  read -rp "Admin? [y/N]: " IS_ADMIN
  ADMIN_FLAG="False"
  [[ "$IS_ADMIN" =~ ^[Yy]$ ]] && ADMIN_FLAG="True"

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
        existing = (await db.execute(select(User).where(User.username == '${UNAME}'))).scalar_one_or_none()
        if existing:
            print('User already exists'); return
        user = User(username='${UNAME}', hashed_password=hash_password('${UPASS}'), is_admin=${ADMIN_FLAG})
        db.add(user)
        await db.commit()
        print(f'User ${UNAME} created (admin=${ADMIN_FLAG})')

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
  echo ""
  echo -e "${BOLD}GnuKontrolR Setup Helper${NC}"
  echo ""
  echo "  bash setup.sh <command>"
  echo ""
  echo -e "  ${CYAN}start${NC}        Start all services"
  echo -e "  ${CYAN}stop${NC}         Stop all services"
  echo -e "  ${CYAN}restart${NC}      Restart all services"
  echo -e "  ${CYAN}status${NC}       Show container status"
  echo -e "  ${CYAN}logs [svc]${NC}   Tail logs (optionally for one service)"
  echo -e "  ${CYAN}update${NC}       Pull latest code + rebuild"
  echo -e "  ${CYAN}backup${NC}       Dump databases to backups/"
  echo -e "  ${CYAN}restore${NC}      Restore from a backup"
  echo -e "  ${CYAN}reset-pass${NC}   Reset a user's password"
  echo -e "  ${CYAN}add-user${NC}     Add a panel user"
  echo -e "  ${CYAN}uninstall${NC}    Remove containers (keeps data)"
  echo ""
}

# ─── Dispatch ────────────────────────────────────────────────────────────────

case "$CMD" in
  start)       cmd_start ;;
  stop)        cmd_stop ;;
  restart)     cmd_restart ;;
  status)      cmd_status ;;
  logs)        cmd_logs "$@" ;;
  update)      cmd_update ;;
  backup)      cmd_backup ;;
  restore)     cmd_restore "$@" ;;
  reset-pass)  cmd_reset_pass ;;
  add-user)    cmd_add_user ;;
  uninstall)   cmd_uninstall ;;
  help|--help|-h) cmd_help ;;
  *) warn "Unknown command: $CMD"; cmd_help; exit 1 ;;
esac
