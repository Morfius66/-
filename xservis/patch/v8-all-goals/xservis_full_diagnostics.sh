#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# Xservis Full Diagnostics — read-only, non-destructive
# Install: cp to /root/xservis_full_diagnostics.sh && chmod +x
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

C_R='\033[31m'; C_G='\033[32m'; C_Y='\033[33m'; C_B='\033[36m'; C_N='\033[0m'
OK="${C_G}[OK]${C_N}"; FAIL="${C_R}[FAIL]${C_N}"; WARN="${C_Y}[WARN]${C_N}"
OVERALL=0

section() { printf "\n${C_B}═══ %s ═══${C_N}\n" "$1"; }
pass()    { printf "  ${OK} %s\n" "$1"; }
fail()    { printf "  ${FAIL} %s\n" "$1"; OVERALL=1; }
warn_()   { printf "  ${WARN} %s\n" "$1"; }

DOC=/opt/xservis
ENV_FILE="$DOC/.env"

# ── 1. Docker Compose Status ─────────────────────────────────────
section "1. Docker Compose"
if [ -f "$DOC/docker-compose.yml" ]; then
    docker compose -f "$DOC/docker-compose.yml" ps 2>/dev/null && pass "docker compose ps" || fail "docker compose ps"
else
    fail "docker-compose.yml not found at $DOC"
fi

# ── 2. Backend Health ─────────────────────────────────────────────
section "2. Backend Health"
HTTP_LOCAL=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/app/ 2>/dev/null || echo "000")
if [ "$HTTP_LOCAL" = "200" ]; then pass "http://127.0.0.1:8000/app/ → $HTTP_LOCAL"
else fail "http://127.0.0.1:8000/app/ → $HTTP_LOCAL"; fi

HTTP_PUBLIC=$(curl -sk -o /dev/null -w "%{http_code}" https://xservis.pro:9443/app/ 2>/dev/null || echo "000")
if [ "$HTTP_PUBLIC" = "200" ]; then pass "https://xservis.pro:9443/app/ → $HTTP_PUBLIC"
else fail "https://xservis.pro:9443/app/ → $HTTP_PUBLIC"; fi

# ── 3. PostgreSQL ─────────────────────────────────────────────────
section "3. PostgreSQL"
PG_CONTAINER=$(docker ps --format '{{.Names}}' 2>/dev/null | grep -iE 'postgres' | head -1)
if [ -n "$PG_CONTAINER" ]; then
    pass "PostgreSQL container: $PG_CONTAINER"

    # pg_isready
    if docker exec "$PG_CONTAINER" pg_isready -U postgres 2>/dev/null | grep -q "accepting"; then
        pass "pg_isready: accepting connections"
    else
        fail "pg_isready: not ready"
    fi

    # List tables (find DB name from env)
    DB_NAME=""
    if [ -f "$ENV_FILE" ]; then
        DB_NAME=$(grep -oP 'DATABASE_URL=.*?/\K[^?]+' "$ENV_FILE" 2>/dev/null || true)
    fi
    DB_NAME="${DB_NAME:-xservis}"

    TABLES=$(docker exec "$PG_CONTAINER" psql -U postgres -d "$DB_NAME" -t -c "SELECT tablename FROM pg_tables WHERE schemaname='public';" 2>/dev/null || echo "")
    if [ -n "$TABLES" ]; then
        pass "Tables found:"
        echo "$TABLES" | while read -r t; do [ -n "$t" ] && printf "      - %s\n" "$(echo "$t" | xargs)"; done
    else
        warn_ "No public tables found (DB: $DB_NAME)"
    fi

    # Check users/tg_users
    for TBL in users tg_users; do
        EXISTS=$(docker exec "$PG_CONTAINER" psql -U postgres -d "$DB_NAME" -t -c "SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='$TBL';" 2>/dev/null | xargs)
        if [ "$EXISTS" = "1" ]; then
            COUNT=$(docker exec "$PG_CONTAINER" psql -U postgres -d "$DB_NAME" -t -c "SELECT count(*) FROM $TBL;" 2>/dev/null | xargs)
            pass "Table '$TBL': $COUNT rows"
        else
            warn_ "Table '$TBL' does not exist"
        fi
    done
else
    fail "No PostgreSQL container found"
fi

# ── 4. Qdrant ─────────────────────────────────────────────────────
section "4. Qdrant"
QDRANT_URL=""
if [ -f "$ENV_FILE" ]; then
    QDRANT_URL=$(grep -oP 'QDRANT_URL=\K.*' "$ENV_FILE" 2>/dev/null | tr -d '"' || true)
fi
QDRANT_URL="${QDRANT_URL:-http://127.0.0.1:6333}"

QDRANT_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "$QDRANT_URL/healthz" 2>/dev/null || echo "000")
if [ "$QDRANT_HEALTH" = "200" ]; then
    pass "Qdrant healthz: OK ($QDRANT_URL)"
else
    # Check via docker
    QD_CONTAINER=$(docker ps --format '{{.Names}}' 2>/dev/null | grep -iE 'qdrant' | head -1)
    if [ -n "$QD_CONTAINER" ]; then
        warn_ "Qdrant container '$QD_CONTAINER' exists but healthz returned $QDRANT_HEALTH"
    else
        warn_ "Qdrant not reachable ($QDRANT_URL → $QDRANT_HEALTH), no container found"
    fi
fi

# Collections
COLLECTIONS=$(curl -s "$QDRANT_URL/collections" 2>/dev/null || echo "")
if echo "$COLLECTIONS" | grep -q '"collections"'; then
    COLL_COUNT=$(echo "$COLLECTIONS" | grep -oP '"name"' | wc -l)
    pass "Qdrant collections: $COLL_COUNT"
    echo "$COLLECTIONS" | grep -oP '"name"\s*:\s*"\K[^"]+' 2>/dev/null | while read -r c; do
        printf "      - %s\n" "$c"
    done
else
    warn_ "Could not list Qdrant collections"
fi

# ── 5. Bot ────────────────────────────────────────────────────────
section "5. Bot"
BACKEND_CONTAINER=$(docker ps --format '{{.Names}}' 2>/dev/null | grep -iE 'backend' | head -1)
if [ -n "$BACKEND_CONTAINER" ]; then
    LOGS=$(docker logs --tail 50 "$BACKEND_CONTAINER" 2>&1 || true)
    if echo "$LOGS" | grep -qiE "polling|startup|started|running"; then
        pass "Backend logs show startup/polling"
    else
        warn_ "No polling/startup keyword in last 50 log lines"
    fi
fi

# WEBAPP_URL
if [ -f "$ENV_FILE" ]; then
    WA_URL=$(grep -oP 'WEBAPP_URL=\K.*' "$ENV_FILE" 2>/dev/null | tr -d '"' || true)
    if [ -n "$WA_URL" ]; then pass "WEBAPP_URL=$WA_URL"
    else warn_ "WEBAPP_URL not set in .env"; fi
fi

# getChatMenuButton (token is NOT printed)
BOT_TOKEN=""
if [ -f "$ENV_FILE" ]; then
    BOT_TOKEN=$(grep -oP 'BOT_TOKEN=\K.*' "$ENV_FILE" 2>/dev/null | tr -d '"' || true)
fi
if [ -n "$BOT_TOKEN" ]; then
    MENU=$(curl -s "https://api.telegram.org/bot${BOT_TOKEN}/getChatMenuButton" 2>/dev/null || echo "")
    if echo "$MENU" | grep -q '"ok":true'; then
        pass "getChatMenuButton: OK"
        echo "$MENU" | grep -oP '"type"\s*:\s*"\K[^"]+' | head -1 | while read -r mt; do
            printf "      menu type: %s\n" "$mt"
        done
    else
        warn_ "getChatMenuButton failed (check BOT_TOKEN)"
    fi
else
    warn_ "BOT_TOKEN not found in .env — skipping Telegram API check"
fi

# ── 6. WebApp Content ─────────────────────────────────────────────
section "6. WebApp Content Verification"
HTML=$(curl -sk https://xservis.pro:9443/app/ 2>/dev/null || echo "")

# Must NOT contain referral banner
for PATTERN in "Приведи друга" "реферальную ссылку" "7 дней бесплатно"; do
    if echo "$HTML" | grep -q "$PATTERN"; then
        fail "Found '$PATTERN' — referral banner still present!"
    else
        pass "No '$PATTERN' ✓"
    fi
done

# Must contain key components
for PATTERN in "Спросить Айму" "Скачать приложение" "Hiddify" "V2RayTun"; do
    if echo "$HTML" | grep -q "$PATTERN"; then
        pass "Found '$PATTERN' ✓"
    else
        fail "'$PATTERN' missing from WebApp!"
    fi
done

# ── 7. Summary ────────────────────────────────────────────────────
section "SUMMARY"
if [ "$OVERALL" -eq 0 ]; then
    printf "  ${C_G}STATUS: ALL OK${C_N}\n"
else
    printf "  ${C_R}STATUS: SOME CHECKS FAILED${C_N}\n"
fi
exit $OVERALL
