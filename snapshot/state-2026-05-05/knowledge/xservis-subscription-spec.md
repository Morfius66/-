# Xservis — спецификация subscription endpoint и deep-link авто-импорта

Спецификация описывает, как Xservis backend должен отдавать подписку и как клиентские кнопки в боте/WebApp должны открывать VPN-приложения, чтобы пользователь не делал ничего, кроме одного тапа.

## Цели

1. **Один тап → подключение.** Юзер нажал «Подключить» → V2RayTun или Hiddify открылся → подписка импортирована → лучший сервер выбран автоматически.
2. **Имя профиля = `Xservis`.** Не `xservis.pro`, не `Subscription`, не пустота, не имя домена. Всегда ровно `Xservis`.
3. **Auto-switch** между серверами по latency без действий пользователя.
4. **Стабильность имени профиля** не зависит от приложения.

## 1. Subscription endpoint (backend)

### URL
```
GET /api/sub/{user_id}?token=<secret>
```

или с подписанным токеном в path:
```
GET /sub/{signed_token}
```

### HTTP-заголовки ответа (обязательные)

```
Content-Type: text/plain; charset=utf-8
Content-Disposition: attachment; filename="Xservis"
Profile-Title: Xservis
Profile-Update-Interval: 24
Subscription-Userinfo: upload=0; download=<used_bytes>; total=<total_bytes>; expire=<unix_ts>
```

**Ключевой заголовок:** `Profile-Title: Xservis`. Без него V2RayTun, Clash, Hiddify, sing-box, NekoBox берут имя профиля из URL, домена или пустой строки — и пользователь видит «xservis.pro» / «Subscription» / мусор.

`Profile-Update-Interval: 24` означает, что клиент обновляет подписку раз в 24 часа.

`Subscription-Userinfo` — стандарт SIP008 / V2Board, V2RayTun и Hiddify его рендерят на главном экране как «использовано X / Y, истекает через Z дней». Позволяет показать пользователю баланс без открытия бота.

### Body — формат зависит от User-Agent

Backend должен **разные форматы** возвращать разным клиентам, потому что V2RayTun и Hiddify хотят разное:

```python
ua = request.headers.get("user-agent", "").lower()

if "clash" in ua or "stash" in ua or "mihomo" in ua:
    return clash_yaml(user)
elif "sing-box" in ua or "sfa" in ua or "sfi" in ua or "nekobox" in ua:
    return singbox_json(user)
elif "v2raytun" in ua or "v2rayng" in ua or "v2box" in ua or "shadowrocket" in ua or "streisand" in ua:
    return base64_vless(user)
elif "hiddify" in ua:
    return clash_yaml(user)
else:
    return base64_vless(user)
```

### Формат A — base64 VLESS (для V2RayTun, V2RayN, V2RayNG, V2Box, Shadowrocket)

Plain-text → base64-encoded. Каждая строка — один VLESS+Reality URL с fragment-меткой:

```
vless://<uuid>@de1.xservis.pro:443?encryption=none&security=reality&sni=<masked>&fp=chrome&pbk=<pubkey>&sid=<short_id>&type=tcp&flow=xtls-rprx-vision#Xservis-DE-1
vless://<uuid>@nl1.xservis.pro:443?encryption=none&security=reality&sni=<masked>&fp=chrome&pbk=<pubkey>&sid=<short_id>&type=tcp&flow=xtls-rprx-vision#Xservis-NL-1
vless://<uuid>@fi1.xservis.pro:443?encryption=none&security=reality&sni=<masked>&fp=chrome&pbk=<pubkey>&sid=<short_id>&type=tcp&flow=xtls-rprx-vision#Xservis-FI-1
```

Fragment `#Xservis-DE-1` после `#` — это remark, который отображается в списке нод. **Важно:** все ноды начинаются с `Xservis-`, чтобы юзер видел консистентный бренд.

После сборки списка → `base64.b64encode(text.encode()).decode()` → возвращаем как body.

**Auto-switch в V2RayTun на base64-формате не работает автоматически.** Юзер вручную нажимает «Test latency» в приложении. Чтобы дать auto-switch — отдавать sing-box JSON по User-Agent (см. формат C).

### Формат B — Clash YAML (для Clash, Stash, Mihomo, Hiddify)

```yaml
mixed-port: 7890
allow-lan: false
mode: rule
log-level: info
external-controller: 127.0.0.1:9090

dns:
  enable: true
  nameserver: [https://1.1.1.1/dns-query, https://8.8.8.8/dns-query]
  fallback: [https://dns.google/dns-query]

proxies:
  - name: Xservis-DE-1
    type: vless
    server: de1.xservis.pro
    port: 443
    uuid: <uuid>
    network: tcp
    tls: true
    udp: true
    flow: xtls-rprx-vision
    servername: <masked-sni>
    reality-opts:
      public-key: <pubkey>
      short-id: <short_id>
    client-fingerprint: chrome
  - name: Xservis-NL-1
    type: vless
    # ... аналогично
  - name: Xservis-FI-1
    type: vless
    # ... аналогично

proxy-groups:
  - name: Xservis-Auto
    type: url-test
    url: http://www.gstatic.com/generate_204
    interval: 300
    tolerance: 50
    proxies:
      - Xservis-DE-1
      - Xservis-NL-1
      - Xservis-FI-1
  - name: Xservis
    type: select
    proxies:
      - Xservis-Auto
      - Xservis-DE-1
      - Xservis-NL-1
      - Xservis-FI-1
      - DIRECT

rules:
  - GEOIP,private,DIRECT,no-resolve
  - GEOIP,RU,DIRECT
  - GEOIP,BY,DIRECT
  - DOMAIN-SUFFIX,ru,DIRECT
  - DOMAIN-SUFFIX,by,DIRECT
  - MATCH,Xservis
```

**Что это даёт:**
- `proxy-groups[0]` = `Xservis-Auto` с `type: url-test` → клиент сам пингует все ноды каждые 5 минут и автоматически выбирает быстрейшую.
- `proxy-groups[1]` = `Xservis` (selector) → юзер видит группу `Xservis` в UI, по умолчанию это Auto, но он может переключиться вручную.
- `rules`: трафик RU/BY → DIRECT (не идёт через VPN), всё остальное → через `Xservis` группу.

Если halal-аудитория запрашивает блокировку конкретных доменов — добавить в `rules`:
```yaml
  - DOMAIN-SUFFIX,gambling-domain.com,REJECT
  - DOMAIN-SUFFIX,adult-content.com,REJECT
```
(Это уже отдельная фича `halal_filter`, не делать сейчас, пока нет валидации спроса.)

### Формат C — sing-box JSON (для sing-box, NekoBox, V2RayTun beta)

```json
{
  "log": { "level": "info" },
  "dns": {
    "servers": [
      { "tag": "remote", "address": "https://1.1.1.1/dns-query", "detour": "Xservis-Auto" },
      { "tag": "local", "address": "local", "detour": "direct" }
    ],
    "rules": [
      { "geosite": ["category-ru"], "server": "local" }
    ]
  },
  "outbounds": [
    {
      "type": "selector",
      "tag": "Xservis",
      "outbounds": ["Xservis-Auto", "Xservis-DE-1", "Xservis-NL-1", "Xservis-FI-1", "direct"],
      "default": "Xservis-Auto"
    },
    {
      "type": "urltest",
      "tag": "Xservis-Auto",
      "outbounds": ["Xservis-DE-1", "Xservis-NL-1", "Xservis-FI-1"],
      "url": "http://www.gstatic.com/generate_204",
      "interval": "5m",
      "tolerance": 50,
      "interrupt_exist_connections": false
    },
    {
      "type": "vless",
      "tag": "Xservis-DE-1",
      "server": "de1.xservis.pro",
      "server_port": 443,
      "uuid": "<uuid>",
      "flow": "xtls-rprx-vision",
      "tls": {
        "enabled": true,
        "server_name": "<masked-sni>",
        "utls": { "enabled": true, "fingerprint": "chrome" },
        "reality": {
          "enabled": true,
          "public_key": "<pubkey>",
          "short_id": "<short_id>"
        }
      }
    },
    { "type": "direct", "tag": "direct" },
    { "type": "block", "tag": "block" }
  ],
  "route": {
    "auto_detect_interface": true,
    "rules": [
      { "geoip": ["private"], "outbound": "direct" },
      { "geoip": ["ru", "by"], "outbound": "direct" }
    ],
    "final": "Xservis"
  }
}
```

**Что это даёт:** аналогично Clash, но через sing-box нативно. `urltest` outbound с `interval: 5m` — auto-switch.

`interrupt_exist_connections: false` — при переключении ноды активные TCP-сессии не разрываются (важно для UX).

## 2. Deep-link кнопки в боте и WebApp

### Принцип

Кнопка не отдаёт сырой URL подписки. Она отдаёт `<scheme>://import?url=<URL_ENCODED_SUB_URL>&name=Xservis`. Клиент расшифровывает scheme → открывает приложение → импортирует.

### V2RayTun (Android, iOS)

```
v2raytun://import/<URL_ENCODED_SUBSCRIPTION_URL>?name=Xservis
```

Альтернативный синтаксис, который V2RayTun тоже принимает:
```
v2raytun://import-sub?url=<URL_ENCODED_SUB_URL>&name=Xservis
```

### Hiddify (все платформы)

```
hiddify://install-config?url=<URL_ENCODED_SUBSCRIPTION_URL>&name=Xservis
```

Hiddify сам определяет формат подписки (Clash YAML / sing-box JSON / base64-VLESS) — нужно лишь, чтобы backend отдавал правильный формат по User-Agent.

### Универсальный fallback (если ни одно VPN-приложение не установлено)

```
clash://install-config?url=<URL_ENCODED>&name=Xservis
```

Большинство Clash-совместимых приложений (Clash for Windows/Mac, Stash, ClashX, Mihomo) принимают этот URI.

### Реализация в боте

В `bot/handlers/connect.py`:

```python
from urllib.parse import quote

async def cmd_connect(message: Message, user: User):
    sub_url = build_subscription_url(user)  # https://xservis.pro/api/sub/<user_id>?token=...
    encoded = quote(sub_url, safe="")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📲 Открыть в V2RayTun", url=f"v2raytun://import/{encoded}?name=Xservis")],
        [InlineKeyboardButton(text="📲 Открыть в Hiddify", url=f"hiddify://install-config?url={encoded}&name=Xservis")],
        [InlineKeyboardButton(text="📋 Скопировать ссылку", callback_data=f"copy_sub:{user.id}")],
        [InlineKeyboardButton(text="❓ Не знаю что выбрать", callback_data="help_choose_app")],
    ])
    
    await message.answer(
        "Выбери приложение и нажми кнопку — подписка импортируется автоматически.\n\n"
        "<b>V2RayTun</b> — лёгкий, быстрый, для Android/iOS.\n"
        "<b>Hiddify</b> — больше функций, авто-выбор лучшего сервера, для всех платформ.\n",
        reply_markup=kb
    )
```

### Реализация в WebApp

В `webapp/index.html`:

```html
<button id="connect-v2raytun">Открыть в V2RayTun</button>
<button id="connect-hiddify">Открыть в Hiddify</button>

<script>
const tg = window.Telegram.WebApp;
const SUB_URL = encodeURIComponent("https://xservis.pro/api/sub/" + USER_ID + "?token=" + TOKEN);

document.getElementById("connect-v2raytun").onclick = () => {
  tg.openLink(`v2raytun://import/${SUB_URL}?name=Xservis`);
};
document.getElementById("connect-hiddify").onclick = () => {
  tg.openLink(`hiddify://install-config?url=${SUB_URL}&name=Xservis`);
};
</script>
```

`tg.openLink` правильно обрабатывает кастомные URI scheme в Telegram WebApp.

## 3. Что НЕ контролирует backend

### Тёмная/светлая тема приложения

Backend не контролирует визуальную тему V2RayTun или Hiddify. Если пользователь жалуется «тема меняется при переходе» — это либо:

(a) Имя профиля меняется (это backend исправит через `Profile-Title`).

(b) Визуальная тема приложения — настраивается в самом V2RayTun (Settings → Appearance → Theme: Dark / Light / System). Объяснить пользователю один раз в FAQ или онбординг-видео.

### Системный auto-start приложения при загрузке устройства

Это настройка ОС (Android: Battery → No restrictions; iOS: VPN configuration in Settings). Backend не влияет.

## 4. Файлы кодовой базы Xservis (предположительно)

Реальные пути могут отличаться — проверить структуру проекта перед изменениями:

- `backend/app/api/subscription.py` — endpoint, headers, User-Agent роутинг.
- `backend/app/services/subscription_builder.py` — генерация base64-VLESS / Clash YAML / sing-box JSON.
- `backend/app/models/user.py` — UUID, пиковая длина, expire.
- `bot/handlers/connect.py` — кнопки deep-link в Telegram-боте.
- `webapp/index.html` или `webapp/src/components/Connect.jsx` — кнопки в WebApp.
- `infra/Caddyfile` — proxy `/api/sub/*` → backend.

## 5. Проверка после внедрения

```bash
# 1. Headers корректны
curl -I -H "User-Agent: V2RayTun/1.0" "https://xservis.pro/api/sub/<test_user_id>?token=..."
# Ожидаем: Profile-Title: Xservis, Profile-Update-Interval: 24, Subscription-Userinfo: ...

# 2. Тело base64 для V2RayTun
curl -H "User-Agent: V2RayTun/1.0" "https://xservis.pro/api/sub/<test_user_id>?token=..." | base64 -d | head -5
# Ожидаем строки vless://...#Xservis-DE-1

# 3. Тело Clash YAML для Hiddify
curl -H "User-Agent: Hiddify/2.0" "https://xservis.pro/api/sub/<test_user_id>?token=..." | head -30
# Ожидаем YAML с proxy-groups[0].type: url-test

# 4. Тело sing-box JSON
curl -H "User-Agent: sing-box/1.8" "https://xservis.pro/api/sub/<test_user_id>?token=..." | jq .outbounds[0]
# Ожидаем {"type":"selector","tag":"Xservis","default":"Xservis-Auto",...}

# 5. Deep-link открывается на тестовом устройстве
# Android: открыть https://xservis.pro/test-link → нажать кнопку → V2RayTun должен открыться
```

## 6. Антипаттерны (как НЕ делать)

- ❌ Не отдавать одинаковый формат на все User-Agent. V2RayTun не понимает sing-box JSON в base64-обёртке.
- ❌ Не зашивать имя профиля в URL (`/api/sub/Xservis-<user_id>`). Используй `Profile-Title` header.
- ❌ Не перенаправлять deep-link через HTTP-страницу-промежуточник. Браузер блокирует кастомные scheme через redirect.
- ❌ Не передавать токен в URL fragment (`#token=...`) — он не попадает на backend.
- ❌ Не использовать одну ноду в `proxy-groups` с `type: url-test` — auto-switch требует минимум 2 ноды для сравнения.
- ❌ Не делать `auto-detect-interface: false` — без этого VPN не работает на роуминге между Wi-Fi и LTE.

## 7. Версия

Xservis Subscription Spec v1.0 — V2RayTun + Hiddify auto-import + auto-switch.
