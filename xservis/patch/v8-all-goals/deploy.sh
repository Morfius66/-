#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# Xservis v8 Deploy — All Goals
# ─────────────────────────────────────────────────────────────────
# Что делает:
#   1. Backup webapp/index.html
#   2. Заменяет webapp/index.html (без referral banner, с initData fallback)
#   3. Синхронизирует webapp → backend/app/webapp
#   4. Устанавливает диагностический скрипт
#   5. Обновляет BOT_TOKEN в .env (если передан аргумент)
#   6. Rebuild backend + caddy
#   7. Проверяет curl
#
# Запуск:
#   sudo bash deploy.sh [--token NEW_BOT_TOKEN]
#
# НЕ трогает: 443, VLESS/Reality, Xray, 3X-UI, Caddyfile, docker-compose.yml
# ─────────────────────────────────────────────────────────────────
set -Eeuo pipefail

DOC=/opt/xservis
WEBAPP=$DOC/webapp
BACKEND_WEBAPP=$DOC/backend/app/webapp
COMPOSE_FILE=$DOC/docker-compose.yml
TS=$(date +%Y%m%d-%H%M%S)
BACKUP=$DOC/backups/remove-referral-banner-final-$TS
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

C_R='\033[31m'; C_G='\033[32m'; C_Y='\033[33m'; C_B='\033[36m'; C_N='\033[0m'
say() { printf "${C_B}[*]${C_N} %s\n" "$*"; }
ok()  { printf "${C_G}[✓]${C_N} %s\n" "$*"; }
die() { printf "${C_R}[X]${C_N} %s\n" "$*" >&2; exit 1; }

# ── Pre-flight ────────────────────────────────────────────────────
[ "$EUID" -eq 0 ] || die "Запусти от root: sudo bash $0"
[ -d "$DOC" ] || die "Не найден $DOC"
[ -f "$COMPOSE_FILE" ] || die "Не найден $COMPOSE_FILE"

# Parse args
NEW_TOKEN=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --token) [ -z "${2:-}" ] && die "--token requires an argument"; NEW_TOKEN="$2"; shift 2;;
        *) shift;;
    esac
done

# ── 1. Backup ─────────────────────────────────────────────────────
say "Creating backup at $BACKUP"
mkdir -p "$BACKUP"
[ -f "$WEBAPP/index.html" ] && cp -a "$WEBAPP/index.html" "$BACKUP/webapp_index.html"
[ -f "$BACKEND_WEBAPP/index.html" ] && cp -a "$BACKEND_WEBAPP/index.html" "$BACKUP/backend_webapp_index.html"
[ -f "$DOC/.env" ] && cp -a "$DOC/.env" "$BACKUP/.env.bak"
ok "Backup done: $BACKUP"

# ── 2. Deploy webapp ─────────────────────────────────────────────
say "Deploying new webapp/index.html"
cp -a "$SCRIPT_DIR/../webapp/index.html" "$WEBAPP/index.html" 2>/dev/null || \
cp -a "$SCRIPT_DIR/webapp_index.html" "$WEBAPP/index.html" 2>/dev/null || \
die "Cannot find new index.html"
ok "webapp/index.html updated"

# ── 3. Sync webapp → backend ─────────────────────────────────────
say "Syncing webapp → backend/app/webapp"
mkdir -p "$BACKEND_WEBAPP"
rsync -a --delete "$WEBAPP/" "$BACKEND_WEBAPP/"
ok "Sync done"

# ── 4. Install diagnostics script ────────────────────────────────
say "Installing diagnostics script"
cp -a "$SCRIPT_DIR/xservis_full_diagnostics.sh" /root/xservis_full_diagnostics.sh
chmod +x /root/xservis_full_diagnostics.sh
ok "Diagnostics at /root/xservis_full_diagnostics.sh"

# ── 5. Update BOT_TOKEN if provided ──────────────────────────────
if [ -n "$NEW_TOKEN" ] && [ -f "$DOC/.env" ]; then
    say "Updating BOT_TOKEN in .env"
    if grep -q "^BOT_TOKEN=" "$DOC/.env"; then
        ESCAPED_TOKEN=$(printf '%s' "$NEW_TOKEN" | sed 's/[|&\/]/\\&/g')
        sed -i "s|^BOT_TOKEN=.*|BOT_TOKEN=$ESCAPED_TOKEN|" "$DOC/.env"
    else
        echo "BOT_TOKEN=$NEW_TOKEN" >> "$DOC/.env"
    fi
    ok "BOT_TOKEN updated"
fi

# ── 6. Rebuild & restart ─────────────────────────────────────────
say "Rebuilding backend"
docker compose -f "$COMPOSE_FILE" build backend
say "Restarting backend + caddy"
docker compose -f "$COMPOSE_FILE" --profile with-caddy up -d backend caddy
ok "Containers restarted"

# Wait for backend to be ready
say "Waiting for backend..."
for i in $(seq 1 15); do
    HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/app/ 2>/dev/null || echo "000")
    [ "$HTTP" = "200" ] && break
    sleep 2
done

# ── 7. Verification ──────────────────────────────────────────────
say "Running verification"

# Check HTTP status
HTTP_LOCAL=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/app/ 2>/dev/null || echo "000")
HTTP_PUBLIC=$(curl -sk -o /dev/null -w "%{http_code}" https://xservis.pro:9443/app/ 2>/dev/null || echo "000")

echo "  Local:  HTTP $HTTP_LOCAL"
echo "  Public: HTTP $HTTP_PUBLIC"

# Check referral banner removal
FOUND=$(curl -sk https://xservis.pro:9443/app/ 2>/dev/null | grep -cE "Приведи друга|реферальную ссылку|7 дней бесплатно" || true)
if [ "$FOUND" -eq 0 ]; then
    ok "Referral banner removed successfully"
else
    die "Referral banner still found! Check $BACKUP for rollback"
fi

# Check key components preserved
PRESERVED=$(curl -sk https://xservis.pro:9443/app/ 2>/dev/null | grep -cE "Спросить Айму|Скачать приложение|Hiddify|V2RayTun" || true)
if [ "$PRESERVED" -ge 3 ]; then
    ok "Key components preserved ($PRESERVED matches)"
else
    die "Key components missing! Only $PRESERVED found. Check $BACKUP for rollback"
fi

echo ""
ok "Deploy complete! Run /root/xservis_full_diagnostics.sh for full check."
echo ""
echo "Rollback: cp $BACKUP/webapp_index.html $WEBAPP/index.html && rsync -a $WEBAPP/ $BACKEND_WEBAPP/ && docker compose -f $COMPOSE_FILE --profile with-caddy up -d backend caddy"
