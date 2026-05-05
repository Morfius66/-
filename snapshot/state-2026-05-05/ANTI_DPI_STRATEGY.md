# Anti-DPI стратегия Xservis (РКН/ТСПУ 2024-2026)

## Методы блокировки и контрмеры

| Метод РКН/ТСПУ | Как работает | Контрмера в Xservis |
|----------------|--------------|---------------------|
| **SNI inspection** | DPI читает имя домена в TLS ClientHello | Reality + чужой SNI из whitelist (vk.com, gosuslugi.ru, …) |
| **SNI whitelisting** | МТС/Билайн пускают ТОЛЬКО whitelist-домены | До 10 SNI из RU whitelist в одной подписке |
| **JA3/JA4 fingerprint** | DPI определяет VPN-клиента по TLS-fingerprint | uTLS подмена под Chrome/Firefox/iOS/Safari/Android/Edge |
| **Active probing** | ТСПУ сам подключается к подозрительному IP, проверяет — VPN или нет | Reality steal-TLS: на «странный» хендшейк сервер отвечает как настоящий vk.com (proxy-pass на dest) |
| **Pattern matching** | DPI ищет VLESS/VMess сигнатуры | Reality маскируется под TLS 1.3, XHTTP под HTTP/2 |
| **Throttling YouTube/Instagram** | Не блок, а замедление до 50 КБ/с на TCP к их IP | Маршрутизация всего трафика через VPN |
| **QUIC/UDP блок** | UDP/443 режется целиком | TCP-only (`security: reality`, `network: tcp`), QUIC отключён |
| **WireGuard блок** | По fingerprint первого UDP-пакета handshake | НЕ используем WireGuard, только VLESS+Reality на TCP |
| **IKEv2 блок** | По UDP/500, UDP/4500 | НЕ используем IPsec/IKEv2 |

## Multi-region стратегия (v4)

Каждая подписка содержит **до 60 профилей** = декартова матрица:

- **10 SNI** из whitelist (`gosuslugi.ru`, `vk.com`, `ok.ru`, `mail.ru`, `yandex.ru`, `microsoft.com`, `cloudflare.com`, `github.com`, `aliexpress.ru`, `tinkoff.ru`)
- **6 fingerprints** (chrome / firefox / ios / safari / android / edge)

Клиент (V2RayTun, Hiddify) пингует все 60 профилей и подключается к самому быстрому. Если МТС блокирует SNI=microsoft.com — клиент пробует SNI=vk.com и сработает. Если Билайн режет JA3=Chrome — клиент пробует JA3=Firefox.

## Идеальная конфигурация 3X-UI

### Reality inbound (есть — расширить serverNames)

```json
{
  "tag": "reality-443",
  "port": 443,
  "protocol": "vless",
  "settings": {
    "decryption": "none",
    "clients": [...]
  },
  "streamSettings": {
    "network": "tcp",
    "security": "reality",
    "realitySettings": {
      "show": false,
      "dest": "www.gosuslugi.ru:443",
      "serverNames": [
        "www.gosuslugi.ru",
        "vk.com",
        "ok.ru",
        "mail.ru",
        "yandex.ru",
        "www.microsoft.com",
        "www.cloudflare.com",
        "github.com",
        "www.aliexpress.ru",
        "tinkoff.ru"
      ],
      "shortIds": ["", "0123abcd"]
    }
  }
}
```

**Важно:** SNI на клиенте должен быть в этом списке `serverNames`. Иначе handshake провалится.

### XHTTP fallback inbound (создать если не создан)

Для регионов где DPI режет даже Reality (новейшие версии ТСПУ умеют детектить Reality по timing-side-channels):

```json
{
  "tag": "xhttp-443",
  "port": 443,           // если порт занят — 8443 или 2096
  "protocol": "vless",
  "settings": {...},
  "streamSettings": {
    "network": "xhttp",
    "security": "reality",
    "xhttpSettings": {
      "host": "www.cloudflare.com",
      "path": "/",
      "mode": "auto"
    },
    "realitySettings": {...}
  }
}
```

Backend учитывает `GEO_INBOUND_XHTTP_FALLBACK` env var → автоматически добавляет XHTTP-профили в подписку.

### Multi-port (если хочется максимум)

Дополнительно — inbound на нестандартном порту:
- **8443** — частая альтернатива HTTPS (некоторые ISP режут только 443)
- **2096** — Cloudflare HTTPS-on-WS (домашний интернет почти всегда пропускает)

Поддержка реализуется через переменную `EXTRA_NODES_JSON`:
```env
EXTRA_NODES_JSON=[
  {"label":"BACKUP-8443","host":"<VPS>","port":8443,"pbk":"<PBK>","sni":"vk.com","sid":"abcd","uuid":"<UUID>"},
  {"label":"BACKUP-2096","host":"<VPS>","port":2096,"pbk":"<PBK>","sni":"vk.com","sid":"abcd","uuid":"<UUID>"}
]
```

## Что РКН/ТСПУ НЕ умеет (но скоро научится)

- ❓ Reality + uTLS Chrome — почти не детектится, т.к. handshake ВЫГЛЯДИТ как настоящий Chrome к настоящему vk.com (через steal-TLS).
- ❓ XHTTP transport — новый, в открытых базах сигнатур ТСПУ ещё нет.
- ❓ Multi-port (8443/2096) — DPI работает на L4 фильтрации, нестандартный порт = меньше внимания.

Регулярно следить за ChatGFW/RKN evasion communities на предмет новых методов блокировки.

## Что в Xservis НЕ используется (намеренно)

- ❌ **WireGuard** — fingerprint первого пакета handshake детектится за миллисекунды
- ❌ **OpenVPN** — даже с tls-crypt легко детектится по pattern
- ❌ **L2TP/IPsec** — UDP/500, блокируется тривиально
- ❌ **QUIC/HTTP3** — UDP/443 режется на ТСПУ
- ❌ **Plain Trojan-Go** — без Reality легко детектится по TLS-fingerprint Go-сервера
- ❌ **Shadowsocks без obfs** — pattern matching по структуре пакетов

Только **VLESS+Reality** (и опционально XHTTP) на TCP/443 (или 8443/2096).
