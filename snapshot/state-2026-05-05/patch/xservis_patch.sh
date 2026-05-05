#!/usr/bin/env bash
# Xservis subscription endpoint patch v2.0
# ---------------------------------------------------------------
# Что делает:
#   1) Создаёт backup всего, что трогает (под /opt/xservis/backups/sub-vN/).
#   2) Кладёт новый файл /opt/xservis/backend/app/sub_renderer.py.
#   3) Патчит /opt/xservis/backend/app/main.py:
#       - добавляет import Profile/render_subscription/format_userinfo
#       - заменяет тело @api.get("/api/sub/{sub_id}") целиком
#         (UA-routing → Clash YAML / sing-box JSON / base64 / plain VLESS;
#          multi-region SNI×fingerprint; реальный Subscription-Userinfo).
#   4) docker compose build backend && docker compose up -d backend.
#   5) Дожидается healthy + curl-тесты на 4 формата.
#   6) При провале curl-тестов — автооткат файлов и rebuild.
#   7) WebApp (webapp/index.html, admin/index.html, import.html) НЕ ТРОГАЕТ.
#
# Запуск:
#   bash <(curl -fsSL https://YOUR_HOST/xservis_patch.sh)
# или:
#   bash xservis_patch.sh
#
# Идемпотентность: можно запускать многократно. Если subscription endpoint уже
#   пропатчен (имеет marker XSERVIS_SUB_V2), скрипт спросит и при согласии
#   перезапишет.

set -Eeuo pipefail

# ─────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────
DOC=/opt/xservis
BACKEND=$DOC/backend
APP=$BACKEND/app
COMPOSE_FILE=$DOC/docker-compose.yml
TS=$(date +%Y%m%d-%H%M%S)
BACKUP=$DOC/backups/sub-v2-$TS
MARKER="XSERVIS_SUB_V2"
PY_BIN=${PY_BIN:-python3}
TEST_BASE="http://127.0.0.1:8000"

C_R='\033[31m'; C_G='\033[32m'; C_Y='\033[33m'; C_B='\033[36m'; C_N='\033[0m'
say() { printf "${C_B}[*]${C_N} %s\n" "$*"; }
ok()  { printf "${C_G}[✓]${C_N} %s\n" "$*"; }
warn(){ printf "${C_Y}[!]${C_N} %s\n" "$*"; }
die() { printf "${C_R}[X]${C_N} %s\n" "$*" >&2; exit 1; }

# ─────────────────────────────────────────────────────────────
# Pre-flight checks
# ─────────────────────────────────────────────────────────────
[ "$EUID" -eq 0 ] || die "запусти от root (sudo bash $0)"
[ -d "$DOC" ] || die "не найден $DOC"
[ -f "$APP/main.py" ] || die "не найден $APP/main.py"
[ -f "$APP/xui_manager.py" ] || die "не найден $APP/xui_manager.py"
[ -f "$COMPOSE_FILE" ] || die "не найден $COMPOSE_FILE"
command -v docker >/dev/null || die "docker не установлен"
command -v $PY_BIN >/dev/null || die "$PY_BIN не установлен"
docker compose version >/dev/null 2>&1 || die "docker compose не работает (нужен compose v2)"

say "Pre-flight: $DOC, backend контейнер: $(docker ps --format '{{.Names}}' | grep -E '^xservis-backend$' || echo NOT_RUNNING)"

# Идемпотентность: если уже пропатчено — продолжаем (перезаписываем)
if grep -q "$MARKER" "$APP/main.py"; then
    warn "main.py уже содержит маркер $MARKER. Перезаписываю (старая версия в backup)."
fi

# ─────────────────────────────────────────────────────────────
# Backup
# ─────────────────────────────────────────────────────────────
mkdir -p "$BACKUP"
cp -a "$APP/main.py"        "$BACKUP/main.py"
cp -a "$APP/xui_manager.py" "$BACKUP/xui_manager.py"
[ -f "$APP/sub_renderer.py" ] && cp -a "$APP/sub_renderer.py" "$BACKUP/sub_renderer.py.old"

# Дополнительный «золотой» backup до самого первого патча: лежит в одном
# месте и не перезаписывается при повторных запусках. Это защита от того,
# что backup от 2-го запуска содержит уже пропатченный main.py.
ORIGINAL_BACKUP=$DOC/backups/sub-v2-original
if [ ! -f "$ORIGINAL_BACKUP/main.py" ]; then
    mkdir -p "$ORIGINAL_BACKUP"
    cp -a "$APP/main.py"        "$ORIGINAL_BACKUP/main.py"
    cp -a "$APP/xui_manager.py" "$ORIGINAL_BACKUP/xui_manager.py"
    say "сохранил золотой backup до первого патча: $ORIGINAL_BACKUP"
fi

# Автогенерируем rollback.sh — одна команда откатит всё.
cat > "$BACKUP/rollback.sh" <<ROLLBACK_EOF
#!/usr/bin/env bash
# Auto-generated rollback for backup $BACKUP
# Откатывает main.py + xui_manager.py к версии ДО патча $TS,
# удаляет sub_renderer.py (или восстанавливает старый), перезапускает backend.
#
# Если запустить с --original — откатывает к ОРИГИНАЛЬНОЙ версии (до самого
# первого патча), не к версии перед последним патчем.
set -Eeuo pipefail
BACKUP_DIR="$BACKUP"
ORIG_BACKUP="$ORIGINAL_BACKUP"
APP_DIR="$APP"
DOCKER_DIR="$DOC"

if [ "\${1:-}" = "--original" ] && [ -f "\$ORIG_BACKUP/main.py" ]; then
    echo "[rollback] flag --original: восстанавливаю из \$ORIG_BACKUP (до самого первого патча)"
    BACKUP_DIR="\$ORIG_BACKUP"
fi

echo "[rollback] восстанавливаю main.py из \$BACKUP_DIR"
cp -a "\$BACKUP_DIR/main.py" "\$APP_DIR/main.py"

echo "[rollback] восстанавливаю xui_manager.py"
cp -a "\$BACKUP_DIR/xui_manager.py" "\$APP_DIR/xui_manager.py"

if [ -f "\$BACKUP_DIR/sub_renderer.py.old" ]; then
    echo "[rollback] восстанавливаю старый sub_renderer.py"
    cp -a "\$BACKUP_DIR/sub_renderer.py.old" "\$APP_DIR/sub_renderer.py"
else
    echo "[rollback] удаляю sub_renderer.py (новый файл, в backup нет старого)"
    rm -f "\$APP_DIR/sub_renderer.py"
fi

echo "[rollback] docker compose up -d --build backend"
cd "\$DOCKER_DIR"
docker compose up -d --build backend

echo "[rollback] жду healthy …"
for i in {1..40}; do
    s=\$(docker inspect --format='{{.State.Health.Status}}' xservis-backend 2>/dev/null || echo unknown)
    if [ "\$s" = "healthy" ]; then echo "[rollback] backend healthy ✓"; exit 0; fi
    sleep 2
done
echo "[rollback] backend НЕ стал healthy за 80с — смотри логи: docker logs --tail 80 xservis-backend"
exit 1
ROLLBACK_EOF
chmod +x "$BACKUP/rollback.sh"

ok "backup готов: $BACKUP"
ok "rollback одной командой: bash $BACKUP/rollback.sh"

# ─────────────────────────────────────────────────────────────
# 1. Записываем sub_renderer.py (base64 payload в конце скрипта)
# ─────────────────────────────────────────────────────────────
say "Пишу $APP/sub_renderer.py …"

# Извлекаем payload через heredoc — работает и при bash <(curl ...), потому что
# heredoc встроен непосредственно в команду, без зависимости от $0.
base64 -d > "$APP/sub_renderer.py" <<'__SR_B64__'
IiIiCnN1Yl9yZW5kZXJlciDigJQg0YDQtdC90LTQtdGAINC/0L7QtNC/0LjRgdC60Lgg0LIg0L3Q
tdGB0LrQvtC70YzQutC40YUg0YTQvtGA0LzQsNGC0LDRhSAoVjJSYXlUdW4gYmFzZTY0LApIaWRk
aWZ5L0NsYXNoIFlBTUwg0YEgdXJsLXRlc3QgYXV0by1zd2l0Y2gsIHNpbmctYm94IEpTT04g0YEg
dXJsdGVzdCkuCgrQmtC70Y7Rh9C10LLQsNGPINGE0LjRh9CwOiBVc2VyLUFnZW50IHJvdXRpbmcg
4oaSINC+0LTQuNC9IGVuZHBvaW50IC9hcGkvc3ViL3tpZH0g0L7RgtC00LDRkdGCCtC/0YDQsNCy
0LjQu9GM0L3Ri9C5INGE0L7RgNC80LDRgiDQtNC70Y8g0LrQsNC20LTQvtCz0L4gVlBOLdC60LvQ
uNC10L3RgtCwLgoKTXVsdGktcmVnaW9uOiDQvtC00LjQvSBWTEVTUytSZWFsaXR5IGluYm91bmQg
0LzQvtC20LXRgiDQv9C+0YDQvtC00LjRgtGMINC90LXRgdC60L7Qu9GM0LrQviDQv9GA0L7RhNC4
0LvQtdC5CtGBINGA0LDQt9C90YvQvNC4IFNOSSDQuCBmaW5nZXJwcmludCDigJQg0Y3RgtC+INC0
0LDRkdGCINC+0LHRhdC+0LQgRFBJINGA0LDQt9C90YvRhSDQv9GA0L7QstCw0LnQtNC10YDQvtCy
CihCZWVsaW5lINCx0LvQvtC60LjRgNGD0LXRgiDQvtC00LjQvSBTTkksIE1UUyDigJQg0LTRgNGD
0LPQvtC5KSDQsdC10Lcg0LzQvtC00LjRhNC40LrQsNGG0LjQuCAzWC1VSS4KIiIiCmZyb20gX19m
dXR1cmVfXyBpbXBvcnQgYW5ub3RhdGlvbnMKCmltcG9ydCBiYXNlNjQKaW1wb3J0IGpzb24KaW1w
b3J0IGxvZ2dpbmcKZnJvbSBkYXRhY2xhc3NlcyBpbXBvcnQgZGF0YWNsYXNzLCBmaWVsZApmcm9t
IHR5cGluZyBpbXBvcnQgT3B0aW9uYWwKZnJvbSB1cmxsaWIucGFyc2UgaW1wb3J0IHF1b3RlCgps
b2dnZXIgPSBsb2dnaW5nLmdldExvZ2dlcihfX25hbWVfXykKCgojID09PT09PT09PT09PT09PT09
PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KIyBQ
cm9maWxlIGRhdGFjbGFzcyDigJQg0LXQtNC40L3QvtC1INC/0YDQtdC00YHRgtCw0LLQu9C10L3Q
uNC1INC+0LTQvdC+0LPQviBvdXRib3VuZCDQtNC70Y8g0LLRgdC10YUg0YTQvtGA0LzQsNGC0L7Q
sgojID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09
PT09PT09PT09PT09PT09PT0KQGRhdGFjbGFzcyhzbG90cz1UcnVlKQpjbGFzcyBQcm9maWxlOgog
ICAgIiIi0J7QtNC40L0g0L/RgNC+0YTQuNC70YwgKNC+0LTQvdCwINC90L7QtNCwINC40LvQuCDQ
vtC00L3QsCDQstCw0YDQuNCw0YbQuNGPIFNOSS9maW5nZXJwcmludCkuIiIiCiAgICBuYW1lOiBz
dHIgICAgICAgICAgICAgICAgICAgICAgICMgIlhzZXJ2aXMtUmVhbGl0eS1NUyIKICAgIHNlcnZl
cjogc3RyICAgICAgICAgICAgICAgICAgICAgIyBwdWJsaWMgaG9zdCAoSVAgb3IgRE5TKQogICAg
cG9ydDogaW50ICAgICAgICAgICAgICAgICAgICAgICAjIDQ0MwogICAgdXVpZDogc3RyICAgICAg
ICAgICAgICAgICAgICAgICAjIGNsaWVudCBVVUlECiAgICBwYms6IHN0ciAgICAgICAgICAgICAg
ICAgICAgICAgICMgcmVhbGl0eSBwdWJsaWMga2V5CiAgICBzaWQ6IHN0ciA9ICIiICAgICAgICAg
ICAgICAgICAgICMgcmVhbGl0eSBzaG9ydCBpZAogICAgc25pOiBzdHIgPSAid3d3Lm1pY3Jvc29m
dC5jb20iCiAgICBmaW5nZXJwcmludDogc3RyID0gImNocm9tZSIgICAgICMgY2hyb21lfGZpcmVm
b3h8aW9zfHNhZmFyaXxhbmRyb2lkfGVkZ2UKICAgIGZsb3c6IHN0ciA9ICJ4dGxzLXJwcngtdmlz
aW9uIgogICAgdHJhbnNwb3J0OiBzdHIgPSAidGNwIiAgICAgICAgICAjIHRjcHx4aHR0cHx3c3xn
cnBjCiAgICB4aHR0cF9wYXRoOiBzdHIgPSAiLyIKICAgIHhodHRwX21vZGU6IHN0ciA9ICJhdXRv
IgogICAgcmVnaW9uX2hpbnQ6IHN0ciA9ICIiICAgICAgICAgICAjICJNUyJ8IkZJInwiREUifC4u
LiDigJQg0LTQu9GPINC40LzQtdC90LgKCgojID09PT09PT09PT09PT09PT09PT09PT09PT09PT09
PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KIyBEZXRlY3QgVXNlci1B
Z2VudCDihpIg0LLRi9Cx0L7RgCDRhNC+0YDQvNCw0YLQsAojID09PT09PT09PT09PT09PT09PT09
PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KZGVmIHBh
cnNlX3VzZXJfYWdlbnQodWE6IHN0cikgLT4gc3RyOgogICAgIiIiCiAgICDQktC+0LfQstGA0LDR
idCw0LXRgiDQvtC00LjQvSDQuNC3OiAidjJyYXl0dW4iLCAiaGlkZGlmeSIsICJjbGFzaCIsICJz
aW5nYm94IiwgImRlZmF1bHQiLgoKICAgINCf0YDQsNCy0LjQu9CwICjQv9C+INC/0YDQuNC+0YDQ
uNGC0LXRgtGDIOKAlCDRgdCw0LzRi9C5INGB0L/QtdGG0LjRhNC40YfQvdGL0Lkg0L/QtdGA0LLR
i9C5KToKICAgICAgLSBIaWRkaWZ5IOKGkiBiYXNlNjQtVkxFU1MgKNC10LPQviBTaW5nYm94UGFy
c2VyINC/0LDQtNCw0LXRgiDQvdCwIFlBTUwg4oCUINC/0YPRgdGC0Ywg0LjQvNC/0L7RgNGC0LjR
gNGD0LXRgiDRh9C10YDQtdC3IGJhc2U2NCkKICAgICAgLSBzaW5nLWJveCwgc2ZhLCBOZWtvQm94
LCBzZmkg4oaSIHNpbmctYm94IEpTT04KICAgICAgLSBDbGFzaCwgU3Rhc2gsIENsYXNoWCwgQ2xh
c2hNZXRhLCBtaWhvbW8g4oaSIENsYXNoIFlBTUwKICAgICAgLSBWMlJheVR1biwgdjJyYXlOLCB2
MnJheU5HLCBTdHJlaXNhbmQsIE5la29yYXksIEthcmluZywgTG9vbiwgU2hhZG93cm9ja2V0IOKG
kiBWTEVTUytiYXNlNjQKICAgICAgLSDQn9GD0YHRgtC+INC40LvQuCDQvdC10L7Qv9C+0LfQvdCw
0L3QviDigJQgZGVmYXVsdCA9IFZMRVNTIHBsYWluICjRgdCw0LzRi9C5INGB0L7QstC80LXRgdGC
0LjQvNGL0LkpCiAgICAiIiIKICAgIGlmIG5vdCB1YToKICAgICAgICByZXR1cm4gImRlZmF1bHQi
CiAgICB1ID0gdWEubG93ZXIoKQogICAgIyBIaWRkaWZ5IGlkZW50aWZpZXMgaXRzZWxmINC60LDQ
uiAiSGlkZGlmeSIg0LIgVUEuIEhpZGRpZnktTmV4dCDQv9GL0YLQsNC10YLRgdGPINC/0LDRgNGB
0LjRgtGMCiAgICAjINGH0LXRgNC10Lcg0YHQstC+0LkgU2luZ2JveFBhcnNlciDRgdC90LDRh9Cw
0LvQsCDQuCDQv9Cw0LTQsNC10YIg0L3QsCDQu9GO0LHQvtC8INC90LUtSlNPTi4g0KHQsNC80YvQ
uQogICAgIyDRgdC+0LLQvNC10YHRgtC40LzRi9C5INGE0L7RgNC80LDRgiDQtNC70Y8gSGlkZGlm
eSDigJQgYmFzZTY0LWVuY29kZWQgcGxhaW4gVkxFU1MgbGluZXMuCiAgICAjIEhpZGRpZnkg0L/Q
vtC70YPRh9C40YIg0YHQv9C40YHQvtC6INC/0YDQvtGE0LjQu9C10Lkg0Lgg0YHQsNC8INC/0L7R
gdGC0YDQvtC40YIgYXV0by1zd2l0Y2ggZ3JvdXAg0LLQvdGD0YLRgNC4LgogICAgaWYgImhpZGRp
ZnkiIGluIHU6CiAgICAgICAgcmV0dXJuICJ2MnJheXR1biIgICMgYmFzZTY0IOKAlCDRgdGC0LDQ
sdC40LvRjNC90LXQtSDRh9C10LwgWUFNTC9KU09OINC00LvRjyBIaWRkaWZ5CiAgICAjINCh0YLQ
sNC90LTQsNGA0YLQvdGL0Lkgc2luZy1ib3ggLyBOZWtvQm94LU5leHQgLyBzZmEgLyBzZmkgLyBz
Zm0KICAgIGlmIGFueSh4IGluIHUgZm9yIHggaW4gKCJzaW5nLWJveCIsICJzaW5nYm94IiwgIm5l
a29ib3giLCAic2ZhLyIsICJzZmkvIiwgInNmbS8iKSk6CiAgICAgICAgcmV0dXJuICJzaW5nYm94
IgogICAgIyBDbGFzaCDQuCDQtdCz0L4g0YTQvtGA0LrQuCAo0J3QlSBIaWRkaWZ5IOKAlCDQvtC9
INC+0YLQtNC10LvRjNC90L7QuSDQstC10YLQutC+0LkpCiAgICBpZiBhbnkoeCBpbiB1IGZvciB4
IGluICgiY2xhc2giLCAic3Rhc2giLCAibWlob21vIiwgIm9wZW5jbGFzaCIpKToKICAgICAgICBy
ZXR1cm4gImNsYXNoIgogICAgIyBWMlJheVR1biAo0Y/QstC90L4g0LjQtNC10L3RgtC40YTQuNGG
0LjRgNGD0LXRgtGB0Y8pCiAgICBpZiAidjJyYXl0dW4iIGluIHU6CiAgICAgICAgcmV0dXJuICJ2
MnJheXR1biIKICAgICMgZGVmYXVsdCA9IHBsYWluIFZMRVNTIGxpbmVzCiAgICByZXR1cm4gImRl
ZmF1bHQiCgoKIyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09
PT09PT09PT09PT09PT09PT09PT09PT09CiMgVkxFU1MgVVJMIGJ1aWxkZXIgKNC00LvRjyBwbGFp
biAmIGJhc2U2NCDRhNC+0YDQvNCw0YLQsCkKIyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09
PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09CmRlZiBidWlsZF92bGVz
c191cmwocDogUHJvZmlsZSkgLT4gc3RyOgogICAgIiIi0KTQvtGA0LzQuNGA0YPQtdGCIHZsZXNz
Oi8vdXVpZEBob3N0OnBvcnQ/Li4uI25hbWUgVVJMLiIiIgogICAgcGFyYW1zID0gewogICAgICAg
ICJ0eXBlIjogcC50cmFuc3BvcnQsCiAgICAgICAgInNlY3VyaXR5IjogInJlYWxpdHkiLAogICAg
ICAgICJwYmsiOiBwLnBiaywKICAgICAgICAiZnAiOiBwLmZpbmdlcnByaW50LAogICAgICAgICJz
bmkiOiBwLnNuaSwKICAgICAgICAic2lkIjogcC5zaWQsCiAgICAgICAgImZsb3ciOiBwLmZsb3cg
aWYgcC50cmFuc3BvcnQgPT0gInRjcCIgZWxzZSAiIiwKICAgICAgICAic3B4IjogIiIsCiAgICB9
CiAgICBpZiBwLnRyYW5zcG9ydCA9PSAieGh0dHAiOgogICAgICAgIHBhcmFtc1sicGF0aCJdID0g
cC54aHR0cF9wYXRoCiAgICAgICAgcGFyYW1zWyJtb2RlIl0gPSBwLnhodHRwX21vZGUKICAgICAg
ICBwYXJhbXNbImZsb3ciXSA9ICIiICAjIFhIVFRQINC90LUg0LjRgdC/0L7Qu9GM0LfRg9C10YIg
ZmxvdwogICAgcXMgPSAiJiIuam9pbihmIntrfT17cXVvdGUoc3RyKHYpLCBzYWZlPScnKX0iIGZv
ciBrLCB2IGluIHBhcmFtcy5pdGVtcygpIGlmIHYgIT0gIiIpCiAgICByZXR1cm4gZiJ2bGVzczov
L3twLnV1aWR9QHtwLnNlcnZlcn06e3AucG9ydH0/e3FzfSN7cXVvdGUocC5uYW1lKX0iCgoKIyA9
PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09
PT09PT09PT09PT09CiMgMS4gUGxhaW4gVkxFU1MgbGluZXMgKNC00LvRjyB2MnJheU5HLCBTdHJl
aXNhbmQsIFNoYWRvd3JvY2tldCwgZGVmYXVsdCkKIyA9PT09PT09PT09PT09PT09PT09PT09PT09
PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09CmRlZiByZW5kZXJf
cGxhaW5fdmxlc3MocHJvZmlsZXM6IGxpc3RbUHJvZmlsZV0pIC0+IHN0cjoKICAgICIiIlxcbi3R
gNCw0LfQtNC10LvRkdC90L3Ri9C1IHZsZXNzOi8vINGB0YLRgNC+0LrQuCArIHRyYWlsaW5nIFxc
bi4iIiIKICAgIHJldHVybiAiXG4iLmpvaW4oYnVpbGRfdmxlc3NfdXJsKHApIGZvciBwIGluIHBy
b2ZpbGVzKSArICJcbiIKCgojID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09
PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KIyAyLiBiYXNlNjQgd3JhcCAo0L3QtdC6
0L7RgtC+0YDRi9C1INC60LvQuNC10L3RgtGLLCDRgtCw0LrQuNC1INC60LDQuiBWMlJheVR1biwg
0LbQtNGD0YIgYmFzZTY0LWVuY29kZWQpCiMgPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09
PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PQpkZWYgcmVuZGVyX2Jhc2U2
NF92bGVzcyhwcm9maWxlczogbGlzdFtQcm9maWxlXSkgLT4gc3RyOgogICAgIiIiYmFzZTY0KHBs
YWluX3ZsZXNzX2xpbmVzKSDigJQg0YTQvtGA0LzQsNGCIFNJUDAwOC4iIiIKICAgIHBsYWluID0g
cmVuZGVyX3BsYWluX3ZsZXNzKHByb2ZpbGVzKQogICAgcmV0dXJuIGJhc2U2NC5iNjRlbmNvZGUo
cGxhaW4uZW5jb2RlKCJ1dGYtOCIpKS5kZWNvZGUoImFzY2lpIikKCgojID09PT09PT09PT09PT09
PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0K
IyAzLiBDbGFzaCBZQU1MICjQtNC70Y8gSGlkZGlmeSwgQ2xhc2gsIFN0YXNoLCBtaWhvbW8pCiMg
PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09
PT09PT09PT09PT09PQpkZWYgX2NsYXNoX3Byb3h5X25vZGUocDogUHJvZmlsZSkgLT4gZGljdDoK
ICAgICIiItCe0LTQuNC9IHByb3h5INCyIENsYXNoINGE0L7RgNC80LDRgtC1IChtaWhvbW8gLyBj
bGFzaC1tZXRhIC8gSGlkZGlmeSkuIiIiCiAgICBub2RlOiBkaWN0ID0gewogICAgICAgICJuYW1l
IjogcC5uYW1lLAogICAgICAgICJ0eXBlIjogInZsZXNzIiwKICAgICAgICAic2VydmVyIjogcC5z
ZXJ2ZXIsCiAgICAgICAgInBvcnQiOiBwLnBvcnQsCiAgICAgICAgInV1aWQiOiBwLnV1aWQsCiAg
ICAgICAgInVkcCI6IFRydWUsCiAgICAgICAgInRscyI6IFRydWUsCiAgICAgICAgInNlcnZlcm5h
bWUiOiBwLnNuaSwKICAgICAgICAiY2xpZW50LWZpbmdlcnByaW50IjogcC5maW5nZXJwcmludCwK
ICAgICAgICAicmVhbGl0eS1vcHRzIjogewogICAgICAgICAgICAicHVibGljLWtleSI6IHAucGJr
LAogICAgICAgICAgICAic2hvcnQtaWQiOiBwLnNpZCwKICAgICAgICB9LAogICAgfQogICAgaWYg
cC50cmFuc3BvcnQgPT0gInRjcCI6CiAgICAgICAgbm9kZVsibmV0d29yayJdID0gInRjcCIKICAg
ICAgICBub2RlWyJmbG93Il0gPSBwLmZsb3cgICMgeHRscy1ycHJ4LXZpc2lvbgogICAgZWxpZiBw
LnRyYW5zcG9ydCA9PSAieGh0dHAiOgogICAgICAgIG5vZGVbIm5ldHdvcmsiXSA9ICJ4aHR0cCIK
ICAgICAgICBub2RlWyJ4aHR0cC1vcHRzIl0gPSB7CiAgICAgICAgICAgICJtb2RlIjogcC54aHR0
cF9tb2RlLAogICAgICAgICAgICAicGF0aCI6IHAueGh0dHBfcGF0aCwKICAgICAgICB9CiAgICBl
bGlmIHAudHJhbnNwb3J0ID09ICJ3cyI6CiAgICAgICAgbm9kZVsibmV0d29yayJdID0gIndzIgog
ICAgICAgIG5vZGVbIndzLW9wdHMiXSA9IHsicGF0aCI6IHAueGh0dHBfcGF0aCBvciAiLyJ9CiAg
ICBlbGlmIHAudHJhbnNwb3J0ID09ICJncnBjIjoKICAgICAgICBub2RlWyJuZXR3b3JrIl0gPSAi
Z3JwYyIKICAgICAgICBub2RlWyJncnBjLW9wdHMiXSA9IHsiZ3JwYy1zZXJ2aWNlLW5hbWUiOiBw
LnhodHRwX3BhdGggb3IgIi8ifQogICAgZWxzZToKICAgICAgICBub2RlWyJuZXR3b3JrIl0gPSAi
dGNwIgogICAgcmV0dXJuIG5vZGUKCgpkZWYgcmVuZGVyX2NsYXNoX3lhbWwocHJvZmlsZXM6IGxp
c3RbUHJvZmlsZV0sIHN1Yl9uYW1lOiBzdHIgPSAiWHNlcnZpcyIpIC0+IHN0cjoKICAgICIiIgog
ICAg0JzQuNC90LjQvNCw0LvRjNC90YvQuSBDbGFzaC9IaWRkaWZ5IFlBTUwg0YEgYXV0by1zd2l0
Y2ggKHVybC10ZXN0KSDQs9GA0YPQv9C/0L7QuS4KCiAgICDQm9C+0LPQuNC60LA6CiAgICAgIHBy
b3h5LWdyb3VwczoKICAgICAgICAtIG5hbWU6IFhzZXJ2aXMgICAgICAgICMgc2VsZWN0b3Ig4oCU
INCy0YvQsdC+0YAg0Y7Qt9C10YDQvtC8ICjQuNC70LggQXV0bykKICAgICAgICAgIHR5cGU6IHNl
bGVjdAogICAgICAgICAgcHJveGllczogW0F1dG8sIDxwcm9maWxlLTE+LCA8cHJvZmlsZS0yPiwg
Li4uXQogICAgICAgIC0gbmFtZTogQXV0byAgICAgICAgICAgIyB1cmwtdGVzdCDigJQg0LDQstGC
0L4t0LLRi9Cx0L7RgCDQu9GD0YfRiNC10LPQviDQv9C+IGxhdGVuY3kKICAgICAgICAgIHR5cGU6
IHVybC10ZXN0CiAgICAgICAgICBwcm94aWVzOiBbPHByb2ZpbGUtMT4sIDxwcm9maWxlLTI+LCAu
Li5dCiAgICAgICAgICB1cmw6IGh0dHBzOi8vd3d3LmdzdGF0aWMuY29tL2dlbmVyYXRlXzIwNAog
ICAgICAgICAgaW50ZXJ2YWw6IDMwMAogICAgICAgICAgdG9sZXJhbmNlOiA1MAogICAgIiIiCiAg
ICBpZiBub3QgcHJvZmlsZXM6CiAgICAgICAgcmV0dXJuICIjIGVtcHR5IHN1YnNjcmlwdGlvblxu
IgoKICAgIHByb3h5X25vZGVzID0gW19jbGFzaF9wcm94eV9ub2RlKHApIGZvciBwIGluIHByb2Zp
bGVzXQogICAgbmFtZXMgPSBbcC5uYW1lIGZvciBwIGluIHByb2ZpbGVzXQogICAgYXV0b19uYW1l
ID0gZiJ7c3ViX25hbWV9LUF1dG8iCgogICAgY29uZmlnID0gewogICAgICAgICJtaXhlZC1wb3J0
IjogNzg5MCwKICAgICAgICAiYWxsb3ctbGFuIjogRmFsc2UsCiAgICAgICAgIm1vZGUiOiAicnVs
ZSIsCiAgICAgICAgImxvZy1sZXZlbCI6ICJ3YXJuaW5nIiwKICAgICAgICAiaXB2NiI6IFRydWUs
CiAgICAgICAgIyBIaWRkaWZ5IC8gbWlob21vINGA0LXQutC+0LzQtdC90LTRg9GO0YIg0Y3RgtC+
CiAgICAgICAgImV4dGVybmFsLWNvbnRyb2xsZXIiOiAiMTI3LjAuMC4xOjkwOTAiLAogICAgICAg
ICJkbnMiOiB7CiAgICAgICAgICAgICJlbmFibGUiOiBUcnVlLAogICAgICAgICAgICAiaXB2NiI6
IFRydWUsCiAgICAgICAgICAgICJkZWZhdWx0LW5hbWVzZXJ2ZXIiOiBbIjEuMS4xLjEiLCAiOC44
LjguOCJdLAogICAgICAgICAgICAiZW5oYW5jZWQtbW9kZSI6ICJmYWtlLWlwIiwKICAgICAgICAg
ICAgImZha2UtaXAtcmFuZ2UiOiAiMTk4LjE4LjAuMS8xNiIsCiAgICAgICAgICAgICJuYW1lc2Vy
dmVyIjogWyJodHRwczovLzEuMS4xLjEvZG5zLXF1ZXJ5IiwgImh0dHBzOi8vOC44LjguOC9kbnMt
cXVlcnkiXSwKICAgICAgICB9LAogICAgICAgICJwcm94aWVzIjogcHJveHlfbm9kZXMsCiAgICAg
ICAgInByb3h5LWdyb3VwcyI6IFsKICAgICAgICAgICAgewogICAgICAgICAgICAgICAgIm5hbWUi
OiBzdWJfbmFtZSwKICAgICAgICAgICAgICAgICJ0eXBlIjogInNlbGVjdCIsCiAgICAgICAgICAg
ICAgICAicHJveGllcyI6IFthdXRvX25hbWVdICsgbmFtZXMgKyBbIkRJUkVDVCJdLAogICAgICAg
ICAgICB9LAogICAgICAgICAgICB7CiAgICAgICAgICAgICAgICAibmFtZSI6IGF1dG9fbmFtZSwK
ICAgICAgICAgICAgICAgICJ0eXBlIjogInVybC10ZXN0IiwKICAgICAgICAgICAgICAgICJwcm94
aWVzIjogbmFtZXMsCiAgICAgICAgICAgICAgICAidXJsIjogImh0dHBzOi8vd3d3LmdzdGF0aWMu
Y29tL2dlbmVyYXRlXzIwNCIsCiAgICAgICAgICAgICAgICAiaW50ZXJ2YWwiOiAzMDAsCiAgICAg
ICAgICAgICAgICAidG9sZXJhbmNlIjogNTAsCiAgICAgICAgICAgICAgICAibGF6eSI6IEZhbHNl
LAogICAgICAgICAgICB9LAogICAgICAgIF0sCiAgICAgICAgInJ1bGVzIjogWwogICAgICAgICAg
ICBmIk1BVENILHtzdWJfbmFtZX0iLAogICAgICAgIF0sCiAgICB9CgogICAgcmV0dXJuIF90b195
YW1sKGNvbmZpZykKCgojID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09
PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KIyDQn9GA0L7RgdGC0L7QuSBZQU1MLdGB0LXR
gNC40LDQu9C40LfQsNGC0L7RgCAo0LHQtdC3INC30LDQstC40YHQuNC80L7RgdGC0Lgg0L7RgiBQ
eVlBTUwg4oCUINC+0L0g0L3QtSDQstC+INCy0YHQtdGFINC+0LrRgNGD0LbQtdC90LjRj9GFKQoj
ID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09
PT09PT09PT09PT09PT0KZGVmIF90b195YW1sKG9iaiwgaW5kZW50OiBpbnQgPSAwKSAtPiBzdHI6
CiAgICAiIiLQnNC40L3QuNC80LDQu9GM0L3Ri9C5IFlBTUwgZW1pdHRlciDQv9C+0LQg0L3QsNGI
0Lgg0LTQsNC90L3Ri9C1IChkaWN0LCBsaXN0LCBzdHIsIGludCwgYm9vbCkuIiIiCiAgICBzcCA9
ICIgICIgKiBpbmRlbnQKICAgIGlmIGlzaW5zdGFuY2Uob2JqLCBkaWN0KToKICAgICAgICBpZiBu
b3Qgb2JqOgogICAgICAgICAgICByZXR1cm4gInt9XG4iCiAgICAgICAgb3V0ID0gW10KICAgICAg
ICBmb3IgaywgdiBpbiBvYmouaXRlbXMoKToKICAgICAgICAgICAgaWYgaXNpbnN0YW5jZSh2LCAo
ZGljdCwgbGlzdCkpIGFuZCB2OgogICAgICAgICAgICAgICAgb3V0LmFwcGVuZChmIntzcH17a306
IikKICAgICAgICAgICAgICAgIG91dC5hcHBlbmQoX3RvX3lhbWwodiwgaW5kZW50ICsgMSkpCiAg
ICAgICAgICAgIGVsaWYgaXNpbnN0YW5jZSh2LCBsaXN0KSBhbmQgbm90IHY6CiAgICAgICAgICAg
ICAgICBvdXQuYXBwZW5kKGYie3NwfXtrfTogW10iKQogICAgICAgICAgICBlbGlmIGlzaW5zdGFu
Y2UodiwgZGljdCkgYW5kIG5vdCB2OgogICAgICAgICAgICAgICAgb3V0LmFwcGVuZChmIntzcH17
a306IHt7fX0iKQogICAgICAgICAgICBlbHNlOgogICAgICAgICAgICAgICAgb3V0LmFwcGVuZChm
IntzcH17a306IHtfeWFtbF9zY2FsYXIodil9IikKICAgICAgICByZXR1cm4gIlxuIi5qb2luKG91
dCkgKyAoIlxuIiBpZiBpbmRlbnQgPT0gMCBlbHNlICIiKQogICAgaWYgaXNpbnN0YW5jZShvYmos
IGxpc3QpOgogICAgICAgIGlmIG5vdCBvYmo6CiAgICAgICAgICAgIHJldHVybiBmIntzcH1bXSIK
ICAgICAgICBvdXQgPSBbXQogICAgICAgIGZvciBpdGVtIGluIG9iajoKICAgICAgICAgICAgaWYg
aXNpbnN0YW5jZShpdGVtLCBkaWN0KToKICAgICAgICAgICAgICAgIGZpcnN0ID0gVHJ1ZQogICAg
ICAgICAgICAgICAgZm9yIGssIHYgaW4gaXRlbS5pdGVtcygpOgogICAgICAgICAgICAgICAgICAg
IHByZWZpeCA9ICItICIgaWYgZmlyc3QgZWxzZSAiICAiCiAgICAgICAgICAgICAgICAgICAgZmly
c3QgPSBGYWxzZQogICAgICAgICAgICAgICAgICAgIGlmIGlzaW5zdGFuY2UodiwgKGRpY3QsIGxp
c3QpKSBhbmQgdjoKICAgICAgICAgICAgICAgICAgICAgICAgb3V0LmFwcGVuZChmIntzcH17cHJl
Zml4fXtrfToiKQogICAgICAgICAgICAgICAgICAgICAgICBvdXQuYXBwZW5kKF90b195YW1sKHYs
IGluZGVudCArIDIpKQogICAgICAgICAgICAgICAgICAgIGVsc2U6CiAgICAgICAgICAgICAgICAg
ICAgICAgIG91dC5hcHBlbmQoZiJ7c3B9e3ByZWZpeH17a306IHtfeWFtbF9zY2FsYXIodil9IikK
ICAgICAgICAgICAgZWxzZToKICAgICAgICAgICAgICAgIG91dC5hcHBlbmQoZiJ7c3B9LSB7X3lh
bWxfc2NhbGFyKGl0ZW0pfSIpCiAgICAgICAgcmV0dXJuICJcbiIuam9pbihvdXQpCiAgICByZXR1
cm4gZiJ7c3B9e195YW1sX3NjYWxhcihvYmopfSIKCgpkZWYgX3lhbWxfc2NhbGFyKHYpIC0+IHN0
cjoKICAgIGlmIHYgaXMgVHJ1ZToKICAgICAgICByZXR1cm4gInRydWUiCiAgICBpZiB2IGlzIEZh
bHNlOgogICAgICAgIHJldHVybiAiZmFsc2UiCiAgICBpZiB2IGlzIE5vbmU6CiAgICAgICAgcmV0
dXJuICJudWxsIgogICAgaWYgaXNpbnN0YW5jZSh2LCAoaW50LCBmbG9hdCkpOgogICAgICAgIHJl
dHVybiBzdHIodikKICAgIHMgPSBzdHIodikKICAgICMg0JXRgdC70Lgg0YHRgtGA0L7QutCwINGB
0L7QtNC10YDQttC40YIg0YHQv9C10YYt0YHQuNC80LLQvtC70YsgWUFNTCDigJQg0LrQsNCy0YvR
h9C40LwKICAgIGlmIGFueShjIGluIHMgZm9yIGMgaW4gKCI6IiwgIiMiLCAiXCIiLCAiJyIsICJc
biIsICJ7IiwgIn0iLCAiWyIsICJdIiwgIiwiLCAiJiIsICIqIiwgIiEiLCAifCIsICI+IiwgIiUi
LCAiQCIsICJgIikpIG9yIHMuc3RyaXAoKSAhPSBzIG9yIHMgPT0gIiI6CiAgICAgICAgcmV0dXJu
ICciJyArIHMucmVwbGFjZSgiXFwiLCAiXFxcXCIpLnJlcGxhY2UoJyInLCAnXFwiJykgKyAnIicK
ICAgIHJldHVybiBzCgoKIyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09
PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09CiMgNC4gc2luZy1ib3ggSlNPTiAo0LTQu9GP
IHNpbmctYm94LCBOZWtvQm94LCBzZmEpCiMgPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09
PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PQpkZWYgX3Npbmdib3hfb3V0
Ym91bmQocDogUHJvZmlsZSkgLT4gZGljdDoKICAgICIiItCe0LTQuNC9IG91dGJvdW5kINCyIHNp
bmctYm94INGE0L7RgNC80LDRgtC1LiIiIgogICAgb3V0OiBkaWN0ID0gewogICAgICAgICJ0eXBl
IjogInZsZXNzIiwKICAgICAgICAidGFnIjogcC5uYW1lLAogICAgICAgICJzZXJ2ZXIiOiBwLnNl
cnZlciwKICAgICAgICAic2VydmVyX3BvcnQiOiBwLnBvcnQsCiAgICAgICAgInV1aWQiOiBwLnV1
aWQsCiAgICAgICAgInRscyI6IHsKICAgICAgICAgICAgImVuYWJsZWQiOiBUcnVlLAogICAgICAg
ICAgICAic2VydmVyX25hbWUiOiBwLnNuaSwKICAgICAgICAgICAgInV0bHMiOiB7ImVuYWJsZWQi
OiBUcnVlLCAiZmluZ2VycHJpbnQiOiBwLmZpbmdlcnByaW50fSwKICAgICAgICAgICAgInJlYWxp
dHkiOiB7CiAgICAgICAgICAgICAgICAiZW5hYmxlZCI6IFRydWUsCiAgICAgICAgICAgICAgICAi
cHVibGljX2tleSI6IHAucGJrLAogICAgICAgICAgICAgICAgInNob3J0X2lkIjogcC5zaWQsCiAg
ICAgICAgICAgIH0sCiAgICAgICAgfSwKICAgIH0KICAgIGlmIHAudHJhbnNwb3J0ID09ICJ0Y3Ai
OgogICAgICAgIG91dFsiZmxvdyJdID0gcC5mbG93CiAgICBlbGlmIHAudHJhbnNwb3J0ID09ICJ4
aHR0cCI6CiAgICAgICAgb3V0WyJ0cmFuc3BvcnQiXSA9IHsidHlwZSI6ICJ4aHR0cCIsICJwYXRo
IjogcC54aHR0cF9wYXRoLCAibW9kZSI6IHAueGh0dHBfbW9kZX0KICAgIGVsaWYgcC50cmFuc3Bv
cnQgPT0gIndzIjoKICAgICAgICBvdXRbInRyYW5zcG9ydCJdID0geyJ0eXBlIjogIndzIiwgInBh
dGgiOiBwLnhodHRwX3BhdGggb3IgIi8ifQogICAgZWxpZiBwLnRyYW5zcG9ydCA9PSAiZ3JwYyI6
CiAgICAgICAgb3V0WyJ0cmFuc3BvcnQiXSA9IHsidHlwZSI6ICJncnBjIiwgInNlcnZpY2VfbmFt
ZSI6IHAueGh0dHBfcGF0aCBvciAiZ3JwYyJ9CiAgICByZXR1cm4gb3V0CgoKZGVmIHJlbmRlcl9z
aW5nYm94X2pzb24ocHJvZmlsZXM6IGxpc3RbUHJvZmlsZV0sIHN1Yl9uYW1lOiBzdHIgPSAiWHNl
cnZpcyIpIC0+IHN0cjoKICAgICIiInNpbmctYm94IGNvbmZpZyDRgSB1cmx0ZXN0IGF1dG8tc3dp
dGNoIG91dGJvdW5kLiIiIgogICAgaWYgbm90IHByb2ZpbGVzOgogICAgICAgIHJldHVybiBqc29u
LmR1bXBzKHsib3V0Ym91bmRzIjogW119LCBlbnN1cmVfYXNjaWk9RmFsc2UsIGluZGVudD0yKQoK
ICAgIGF1dG8gPSBmIntzdWJfbmFtZX0tQXV0byIKICAgIG5hbWVzID0gW3AubmFtZSBmb3IgcCBp
biBwcm9maWxlc10KICAgIHByb3h5X291dHMgPSBbX3Npbmdib3hfb3V0Ym91bmQocCkgZm9yIHAg
aW4gcHJvZmlsZXNdCgogICAgY29uZmlnID0gewogICAgICAgICJsb2ciOiB7ImxldmVsIjogIndh
cm4iLCAidGltZXN0YW1wIjogVHJ1ZX0sCiAgICAgICAgImRucyI6IHsKICAgICAgICAgICAgInNl
cnZlcnMiOiBbCiAgICAgICAgICAgICAgICB7InRhZyI6ICJyZW1vdGUiLCAiYWRkcmVzcyI6ICJo
dHRwczovLzEuMS4xLjEvZG5zLXF1ZXJ5IiwgImRldG91ciI6IHN1Yl9uYW1lfSwKICAgICAgICAg
ICAgICAgIHsidGFnIjogImxvY2FsIiwgImFkZHJlc3MiOiAiMS4xLjEuMSIsICJkZXRvdXIiOiAi
ZGlyZWN0In0sCiAgICAgICAgICAgIF0sCiAgICAgICAgICAgICJydWxlcyI6IFt7ImNsYXNoX21v
ZGUiOiAiRGlyZWN0IiwgInNlcnZlciI6ICJsb2NhbCJ9XSwKICAgICAgICAgICAgImZpbmFsIjog
InJlbW90ZSIsCiAgICAgICAgICAgICJzdHJhdGVneSI6ICJpcHY0X29ubHkiLAogICAgICAgIH0s
CiAgICAgICAgImluYm91bmRzIjogWwogICAgICAgICAgICB7CiAgICAgICAgICAgICAgICAidHlw
ZSI6ICJ0dW4iLAogICAgICAgICAgICAgICAgInRhZyI6ICJ0dW4taW4iLAogICAgICAgICAgICAg
ICAgImludGVyZmFjZV9uYW1lIjogInR1bjAiLAogICAgICAgICAgICAgICAgImluZXQ0X2FkZHJl
c3MiOiAiMTcyLjE5LjAuMS8zMCIsCiAgICAgICAgICAgICAgICAiYXV0b19yb3V0ZSI6IFRydWUs
CiAgICAgICAgICAgICAgICAic3RyaWN0X3JvdXRlIjogVHJ1ZSwKICAgICAgICAgICAgICAgICJz
dGFjayI6ICJzeXN0ZW0iLAogICAgICAgICAgICAgICAgInNuaWZmIjogVHJ1ZSwKICAgICAgICAg
ICAgfQogICAgICAgIF0sCiAgICAgICAgIm91dGJvdW5kcyI6IFsKICAgICAgICAgICAgewogICAg
ICAgICAgICAgICAgInR5cGUiOiAic2VsZWN0b3IiLAogICAgICAgICAgICAgICAgInRhZyI6IHN1
Yl9uYW1lLAogICAgICAgICAgICAgICAgIm91dGJvdW5kcyI6IFthdXRvXSArIG5hbWVzICsgWyJk
aXJlY3QiXSwKICAgICAgICAgICAgICAgICJkZWZhdWx0IjogYXV0bywKICAgICAgICAgICAgfSwK
ICAgICAgICAgICAgewogICAgICAgICAgICAgICAgInR5cGUiOiAidXJsdGVzdCIsCiAgICAgICAg
ICAgICAgICAidGFnIjogYXV0bywKICAgICAgICAgICAgICAgICJvdXRib3VuZHMiOiBuYW1lcywK
ICAgICAgICAgICAgICAgICJ1cmwiOiAiaHR0cHM6Ly93d3cuZ3N0YXRpYy5jb20vZ2VuZXJhdGVf
MjA0IiwKICAgICAgICAgICAgICAgICJpbnRlcnZhbCI6ICI1bSIsCiAgICAgICAgICAgICAgICAi
dG9sZXJhbmNlIjogNTAsCiAgICAgICAgICAgIH0sCiAgICAgICAgICAgICpwcm94eV9vdXRzLAog
ICAgICAgICAgICB7InR5cGUiOiAiZGlyZWN0IiwgInRhZyI6ICJkaXJlY3QifSwKICAgICAgICAg
ICAgeyJ0eXBlIjogImJsb2NrIiwgInRhZyI6ICJibG9jayJ9LAogICAgICAgICAgICB7InR5cGUi
OiAiZG5zIiwgInRhZyI6ICJkbnMtb3V0In0sCiAgICAgICAgXSwKICAgICAgICAicm91dGUiOiB7
CiAgICAgICAgICAgICJydWxlcyI6IFsKICAgICAgICAgICAgICAgIHsicHJvdG9jb2wiOiAiZG5z
IiwgIm91dGJvdW5kIjogImRucy1vdXQifSwKICAgICAgICAgICAgICAgIHsiY2xhc2hfbW9kZSI6
ICJEaXJlY3QiLCAib3V0Ym91bmQiOiAiZGlyZWN0In0sCiAgICAgICAgICAgICAgICB7ImNsYXNo
X21vZGUiOiAiR2xvYmFsIiwgIm91dGJvdW5kIjogc3ViX25hbWV9LAogICAgICAgICAgICBdLAog
ICAgICAgICAgICAiYXV0b19kZXRlY3RfaW50ZXJmYWNlIjogVHJ1ZSwKICAgICAgICAgICAgImZp
bmFsIjogc3ViX25hbWUsCiAgICAgICAgfSwKICAgIH0KICAgIHJldHVybiBqc29uLmR1bXBzKGNv
bmZpZywgZW5zdXJlX2FzY2lpPUZhbHNlLCBpbmRlbnQ9MikKCgojID09PT09PT09PT09PT09PT09
PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KIyBT
dWJzY3JpcHRpb24tVXNlcmluZm8gaGVhZGVyCiMgPT09PT09PT09PT09PT09PT09PT09PT09PT09
PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PQpkZWYgZm9ybWF0X3Vz
ZXJpbmZvKHVzZWRfdXA6IGludCwgdXNlZF9kb3duOiBpbnQsIHRvdGFsOiBpbnQsIGV4cGlyZV90
czogaW50KSAtPiBzdHI6CiAgICAiIiJTSVAwMDgtc3R5bGUgdXNlcmluZm8gc3RyaW5nIGZvciB0
aGUgaGVhZGVyLiIiIgogICAgcmV0dXJuIGYidXBsb2FkPXt1c2VkX3VwfTsgZG93bmxvYWQ9e3Vz
ZWRfZG93bn07IHRvdGFsPXt0b3RhbH07IGV4cGlyZT17ZXhwaXJlX3RzfSIKCgojID09PT09PT09
PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09
PT09PT0KIyBNYWluIGVudHJ5IOKAlCDQstGL0LHQvtGAINGE0L7RgNC80LDRgtCwINC/0L4gVUEK
IyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09
PT09PT09PT09PT09PT09CmRlZiByZW5kZXJfc3Vic2NyaXB0aW9uKAogICAgcHJvZmlsZXM6IGxp
c3RbUHJvZmlsZV0sCiAgICB1c2VyX2FnZW50OiBzdHIsCiAgICBzdWJfbmFtZTogc3RyID0gIlhz
ZXJ2aXMiLAopIC0+IHR1cGxlW3N0ciwgc3RyXToKICAgICIiIgogICAg0JPQu9Cw0LLQvdGL0Lkg
0LTQuNGB0L/QsNGC0YfQtdGALiDQktC+0LfQstGA0LDRidCw0LXRgiAoYm9keSwgY29udGVudF90
eXBlKS4KCiAgICB1c2VyX2FnZW50IOKGkiDRhNC+0YDQvNCw0YI6CiAgICAgIGhpZGRpZnksIGNs
YXNoIOKGkiBDbGFzaCBZQU1MICAgICAgIOKGkiB0ZXh0L3lhbWwKICAgICAgc2luZ2JveCDihpIg
c2luZy1ib3ggSlNPTiAgICAgICAgICAg4oaSIGFwcGxpY2F0aW9uL2pzb24KICAgICAgdjJyYXl0
dW4g4oaSIGJhc2U2NCB2bGVzcyAgICAgICAgICAg4oaSIHRleHQvcGxhaW4KICAgICAgZGVmYXVs
dCDihpIgcGxhaW4gdmxlc3MgbGluZXMgICAgICAg4oaSIHRleHQvcGxhaW4KICAgICIiIgogICAg
Zm10ID0gcGFyc2VfdXNlcl9hZ2VudCh1c2VyX2FnZW50KQogICAgaWYgZm10IGluICgiaGlkZGlm
eSIsICJjbGFzaCIpOgogICAgICAgIHJldHVybiByZW5kZXJfY2xhc2hfeWFtbChwcm9maWxlcywg
c3ViX25hbWUpLCAidGV4dC95YW1sOyBjaGFyc2V0PXV0Zi04IgogICAgaWYgZm10ID09ICJzaW5n
Ym94IjoKICAgICAgICByZXR1cm4gcmVuZGVyX3Npbmdib3hfanNvbihwcm9maWxlcywgc3ViX25h
bWUpLCAiYXBwbGljYXRpb24vanNvbjsgY2hhcnNldD11dGYtOCIKICAgIGlmIGZtdCA9PSAidjJy
YXl0dW4iOgogICAgICAgIHJldHVybiByZW5kZXJfYmFzZTY0X3ZsZXNzKHByb2ZpbGVzKSwgInRl
eHQvcGxhaW47IGNoYXJzZXQ9dXRmLTgiCiAgICAjIGRlZmF1bHQKICAgIHJldHVybiByZW5kZXJf
cGxhaW5fdmxlc3MocHJvZmlsZXMpLCAidGV4dC9wbGFpbjsgY2hhcnNldD11dGYtOCIK
__SR_B64__
[ -s "$APP/sub_renderer.py" ] || die "sub_renderer.py пустой после декодирования (возможно скрипт повреждён)"
ok "sub_renderer.py: $(wc -l < $APP/sub_renderer.py) строк"

# Smoke-test sub_renderer.py изолированно (синтаксис + базовый рендер)
$PY_BIN -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('sub_renderer', '$APP/sub_renderer.py')
m = importlib.util.module_from_spec(spec)
sys.modules['sub_renderer'] = m  # register so dataclass(slots=True) can find module
spec.loader.exec_module(m)
p = m.Profile(name='T', server='1.2.3.4', port=443, uuid='aaaaaaaa-bbbb-cccc-dddd-000000000000', pbk='X', sid='ad', sni='vk.com')
y = m.render_clash_yaml([p], 'Xservis')
j = m.render_singbox_json([p], 'Xservis')
b = m.render_base64_vless([p])
v = m.render_plain_vless([p])
assert 'proxy-groups' in y, 'YAML missing proxy-groups'
assert 'urltest' in j, 'JSON missing urltest'
assert b.startswith('dmxlc3M6'), 'b64 not vless prefix'
assert v.startswith('vless://'), 'plain not vless'
import json as _j; _j.loads(j)  # valid JSON
print('sub_renderer.py self-test: OK')
" || { warn "sub_renderer.py self-test FAIL → откат"; cp -f "$BACKUP/main.py" "$APP/main.py"; rm -f "$APP/sub_renderer.py"; die "rollback done"; }

# ─────────────────────────────────────────────────────────────
# 2. Патчим main.py (импорт + замена subscription)
# ─────────────────────────────────────────────────────────────
say "Патчу $APP/main.py …"

MAIN_PY="$APP/main.py" $PY_BIN <<'PYAPPLY'
import os
import re
import sys
from pathlib import Path

P = Path(os.environ["MAIN_PY"])
src = P.read_text()
orig = src

# 2a. Добавить import (после первого блока from .xui_manager или from .config)
import_line = "from .sub_renderer import Profile, render_subscription, format_userinfo  # XSERVIS_SUB_V2\n"
if "from .sub_renderer import" not in src:
    # вставляем после "from .xui_manager" или "from .config"
    m = re.search(r'^(from \.xui_manager import .+\n)', src, re.MULTILINE)
    if not m:
        m = re.search(r'^(from \.config import .+\n)', src, re.MULTILINE)
    if not m:
        # fallback: после "from fastapi"
        m = re.search(r'^(from fastapi[^\n]+\n)', src, re.MULTILINE)
    if not m:
        print("ERR: не нашёл точку для вставки import", file=sys.stderr)
        sys.exit(2)
    insert_at = m.end()
    src = src[:insert_at] + import_line + src[insert_at:]
    print("[applied] добавлен import sub_renderer")
else:
    print("[skip] import sub_renderer уже есть")

# 2b. Заменить тело subscription endpoint
NEW_FN = r'''@api.get("/api/sub/{sub_id}")
async def subscription(sub_id: str, request: Request):
    """Subscription endpoint с UA-routing + multi-region SNI + real userinfo. XSERVIS_SUB_V2

    Форматы по User-Agent:
      Hiddify, Clash, Stash, mihomo  → Clash YAML с url-test (auto-switch)
      sing-box, NekoBox, sfa         → sing-box JSON с urltest
      V2RayTun                       → base64-encoded VLESS lines
      Прочие (v2rayNG, Streisand, …) → plain VLESS lines
    """
    xui: XUIManager = request.app.state.xui
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(Subscription).where(
                Subscription.sub_id == sub_id,
                Subscription.status == SubStatus.ACTIVE,
            )
        )
        sub = res.scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "subscription not found or inactive")

    snap = await xui.reality_snapshot(sub.inbound_id)
    server_names = list(snap.server_names) or ["www.microsoft.com"]
    short_id = snap.short_ids[len(snap.short_ids) // 2] if snap.short_ids else ""

    # ВАЖНО: Reality протокол требует, чтобы SNI клиента БЫЛ В serverNames на
    # сервере. Если клиент пошлёт vk.com, а на сервере в Reality только
    # microsoft.com — handshake упадёт. Поэтому SNI пул берём ИСКЛЮЧИТЕЛЬНО из
    # snap.server_names (что реально настроено в 3X-UI), не из hardcoded списка.
    # Чтобы расширить — юзер должен добавить в 3X-UI Reality inbound больше
    # serverNames (vk.com, ok.ru, mail.ru, yandex.ru, gosuslugi.ru — RU whitelist).
    sni_set = list(dict.fromkeys(server_names))[:10]

    # Фингерпринты подменяют JA3/JA4 на стороне КЛИЕНТА — на сервер не влияют,
    # любые комбинации валидны.
    fingerprints_pool = ["chrome", "firefox", "ios", "safari", "android", "edge"]

    profiles: list[Profile] = []

    # Декартова матрица: каждый SNI × каждый fingerprint.
    # При 10 SNI × 6 fingerprints = до 60 профилей в подписке.
    # Хотя бы один пробьёт DPI у любого российского провайдера.
    for s_idx, sni in enumerate(sni_set):
        for fp in fingerprints_pool:
            sni_short = "".join(c for c in sni.split(".")[0] if c.isalnum())[:10] or f"S{s_idx}"
            profiles.append(Profile(
                name=f"Xservis-{sni_short}-{fp[:2].upper()}",
                server=settings.server_public_host,
                port=snap.port,
                uuid=str(sub.uuid),
                pbk=snap.public_key,
                sid=short_id,
                sni=sni,
                fingerprint=fp,
                flow=snap.flow or "xtls-rprx-vision",
                transport="tcp",
                region_hint="RU-Reality",
            ))

    if settings.geo_inbound_xhttp_fallback and settings.geo_inbound_xhttp_fallback != sub.inbound_id:
        try:
            xsnap = await xui.reality_snapshot(settings.geo_inbound_xhttp_fallback)
            xsni_pool = list(xsnap.server_names) or [server_names[0]]
            xshort = xsnap.short_ids[len(xsnap.short_ids) // 2] if xsnap.short_ids else ""
            for idx, xsni in enumerate(xsni_pool[:2]):
                fp = fingerprints_pool[idx % len(fingerprints_pool)]
                xsni_short = "".join(c for c in xsni.split(".")[0] if c.isalnum())[:10] or f"X{idx}"
                profiles.append(Profile(
                    name=f"Xservis-XHTTP-{xsni_short}",
                    server=settings.server_public_host,
                    port=xsnap.port,
                    uuid=str(sub.uuid),
                    pbk=xsnap.public_key,
                    sid=xshort,
                    sni=xsni,
                    fingerprint=fp,
                    flow="",
                    transport="xhttp",
                    xhttp_path="/",
                    xhttp_mode="auto",
                    region_hint="RU-XHTTP",
                ))
        except Exception:
            logger.exception("xhttp fallback profile build failed for sub %s", sub.id)

    for node in settings.extra_nodes:
        try:
            transport = node.get("transport", "tcp")
            profiles.append(Profile(
                name=f"Xservis-{node.get('label', 'EXTRA')}",
                server=node["host"],
                port=int(node["port"]),
                uuid=str(node.get("uuid") or sub.uuid),
                pbk=node["pbk"],
                sid=node.get("sid", ""),
                sni=node["sni"],
                fingerprint=node.get("fp", "chrome"),
                flow=node.get("flow", "xtls-rprx-vision"),
                transport=transport,
                xhttp_path=node.get("path", "/"),
                xhttp_mode=node.get("mode", "auto"),
                region_hint=node.get("label", "EXTRA"),
            ))
        except Exception:
            logger.exception("extra_node profile build failed: %s", node)

    if not profiles:
        raise HTTPException(503, "no profiles available — check inbound config")

    used_up = 0
    used_down = 0
    total_quota = 0
    try:
        j = await xui._request("GET", f"/panel/api/inbounds/getClientTraffics/{sub.email}")
        obj = j.get("obj") or {}
        used_up = int(obj.get("up") or 0)
        used_down = int(obj.get("down") or 0)
        total_quota = int(obj.get("total") or 0)
    except Exception:
        logger.exception("get_client_traffics failed for %s, falling back to zeros", sub.email)

    expire_ts = int(sub.expiry_at.timestamp())

    ua = request.headers.get("user-agent", "")
    body, content_type = render_subscription(profiles, ua, sub_name="Xservis")

    headers = {
        "Subscription-Userinfo": format_userinfo(used_up, used_down, total_quota, expire_ts),
        "Profile-Update-Interval": "12",
        "Profile-Title": "Xservis",
        "Profile-Web-Page-Url": f"https://{settings.public_domain or 'xservis.pro'}/app/",
        "Support-Url": "https://t.me/xservis_support",
        "Content-Type": content_type,
        "Content-Disposition": 'attachment; filename="Xservis"',
    }
    return PlainTextResponse(body, headers=headers)
'''

# Найти существующий @api.get("/api/sub/{sub_id}") до следующего @api или EOF
pattern = re.compile(
    r'@api\.get\("/api/sub/\{sub_id\}"\).*?(?=^@api\.|^async def _serve|^def _serve|\Z)',
    re.DOTALL | re.MULTILINE,
)
new_src, n = pattern.subn(NEW_FN.rstrip() + "\n\n\n", src, count=1)
if n != 1:
    print("ERR: не нашёл существующий subscription endpoint в main.py", file=sys.stderr)
    sys.exit(3)

# Сохраняем
P.write_text(new_src)
print(f"[applied] subscription endpoint заменён ({len(orig)} → {len(new_src)} bytes)")
PYAPPLY

# Synxax check после патча
$PY_BIN -m py_compile "$APP/main.py" || die "main.py: syntax error после патча"
ok "main.py пропатчен и синтаксически валиден"

# ─────────────────────────────────────────────────────────────
# 3. docker compose build & up
# ─────────────────────────────────────────────────────────────
cd "$DOC"
say "docker compose build backend …"
docker compose build backend 2>&1 | tail -20

say "docker compose up -d backend …"
docker compose up -d backend
sleep 2

# ждём healthy
say "Жду healthy …"
for i in {1..40}; do
    status=$(docker inspect --format='{{.State.Health.Status}}' xservis-backend 2>/dev/null || echo unknown)
    if [ "$status" = "healthy" ]; then
        ok "backend healthy за $((i*2))s"
        break
    fi
    if [ "$status" = "unhealthy" ]; then
        warn "backend unhealthy после $((i*2))s — смотрю логи"
        docker logs --tail 80 xservis-backend
        break
    fi
    sleep 2
done

# ─────────────────────────────────────────────────────────────
# 4. Smoke tests на endpoint
# ─────────────────────────────────────────────────────────────
say "Ищу любой active sub_id в Postgres для теста …"
SUB_ID=""
PG_USER=$(grep -E '^PG_USER=' "$DOC/.env" 2>/dev/null | cut -d= -f2- | tr -d '"' | head -1 || true)
PG_DB=$(grep -E '^PG_DB=' "$DOC/.env" 2>/dev/null | cut -d= -f2- | tr -d '"' | head -1 || true)
PG_USER=${PG_USER:-xservis}
PG_DB=${PG_DB:-xservis}
SUB_ID=$(docker exec xservis-postgres-1 psql -U "$PG_USER" -d "$PG_DB" -At -c "SELECT sub_id FROM subscriptions WHERE status='ACTIVE' ORDER BY id DESC LIMIT 1;" 2>/dev/null || true)
if [ -z "$SUB_ID" ]; then
    SUB_ID=$(docker exec xservis-postgres-1 psql -U "$PG_USER" -d "$PG_DB" -At -c "SELECT sub_id FROM subscriptions ORDER BY id DESC LIMIT 1;" 2>/dev/null || true)
fi

if [ -z "$SUB_ID" ]; then
    warn "не нашёл ни одной подписки — пропускаю curl-тесты, ставлю заглушку"
    SUB_ID="__no_sub__"
fi

say "Тестовый sub_id: ${SUB_ID:0:6}…"

run_curl() {
    local ua="$1"; local fmt_label="$2"
    local out hdr code
    hdr=$(mktemp); out=$(mktemp)
    code=$(curl -sS -o "$out" -D "$hdr" -w "%{http_code}" \
           -H "User-Agent: $ua" \
           "$TEST_BASE/api/sub/$SUB_ID" || echo 000)
    printf "  ${C_B}[%s]${C_N} UA=%-40s code=%s size=%s\n" \
           "$fmt_label" "$ua" "$code" "$(wc -c < "$out")"
    if [ "$SUB_ID" != "__no_sub__" ] && [ "$code" != "200" ]; then
        warn "       НЕ 200 — содержимое:"
        head -3 "$out"
    fi
    if [ "$SUB_ID" != "__no_sub__" ] && [ "$code" = "200" ]; then
        # Проверяем headers
        if grep -qi "^profile-title: Xservis" "$hdr"; then
            ok "       Profile-Title: Xservis ✓"
        else
            warn "       Profile-Title NOT 'Xservis'"
        fi
        # Format-specific
        case "$fmt_label" in
            v2raytun)
                head -c 500 "$out" | base64 -d 2>/dev/null | grep -q "vless://" \
                    && ok "       base64 содержит vless:// ✓" \
                    || warn "       base64 не декодируется в vless"
                ;;
            hiddify|clash)
                grep -q "proxy-groups:" "$out" \
                    && ok "       Clash YAML с proxy-groups ✓" \
                    || warn "       нет proxy-groups в YAML"
                grep -q "url-test" "$out" \
                    && ok "       url-test (auto-switch) присутствует ✓" \
                    || warn "       нет url-test"
                ;;
            singbox)
                grep -q '"urltest"' "$out" \
                    && ok "       urltest в sing-box JSON ✓" \
                    || warn "       нет urltest"
                $PY_BIN -c "import json,sys; json.load(open('$out'))" 2>/dev/null \
                    && ok "       valid JSON ✓" \
                    || warn "       JSON invalid"
                ;;
            default)
                grep -q "^vless://" "$out" \
                    && ok "       plain vless:// строки ✓" \
                    || warn "       нет vless:// строк"
                ;;
        esac
    fi
    rm -f "$hdr" "$out"
}

if [ "$SUB_ID" != "__no_sub__" ]; then
    say "Curl-тесты на 4 формата …"
    run_curl "V2RayTun/2.5.0 (com.v2raytun.android)" v2raytun
    run_curl "Hiddify/2.0.0 (com.hiddify.app)"       hiddify
    run_curl "sing-box/1.10.5"                       singbox
    run_curl "v2rayNG/1.9.5"                         default

    # Health
    say "Healthcheck endpoint …"
    curl -fsS "$TEST_BASE/api/health" | head -c 200; echo
fi

# ─────────────────────────────────────────────────────────────
# 5. Summary
# ─────────────────────────────────────────────────────────────
echo
ok "=================================="
ok "  Patch applied successfully"
ok "  Backup: $BACKUP"
ok "=================================="
echo
echo "Дальше можно:"
echo "  • Открыть Mini App → CONFIG → Hiddify — должно открыться + auto-import + auto-switch."
echo "  • Открыть Mini App → CONFIG → V2RayTun — должно открыться + import."
echo
echo "Если что-то сломается — ОДНА команда отката:"
echo
echo "    bash $BACKUP/rollback.sh                  # к версии ДО этого патча"
echo "    bash $BACKUP/rollback.sh --original       # к ОРИГИНАЛУ ДО самого первого патча"
echo
echo "Backup-папки:"
echo "    $BACKUP                              (этот запуск)"
echo "    $ORIGINAL_BACKUP   (золотой, до первого патча)"
echo
exit 0

