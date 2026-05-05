"""
sub_renderer — рендер подписки в нескольких форматах (V2RayTun base64,
Hiddify/Clash YAML с url-test auto-switch, sing-box JSON с urltest).

Ключевая фича: User-Agent routing → один endpoint /api/sub/{id} отдаёт
правильный формат для каждого VPN-клиента.

Multi-region: один VLESS+Reality inbound может породить несколько профилей
с разными SNI и fingerprint — это даёт обход DPI разных провайдеров
(Beeline блокирует один SNI, MTS — другой) без модификации 3X-UI.
"""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)


# ======================================================================
# Profile dataclass — единое представление одного outbound для всех форматов
# ======================================================================
@dataclass(slots=True)
class Profile:
    """Один профиль (одна нода или одна вариация SNI/fingerprint)."""
    name: str                       # "Xservis-Reality-MS"
    server: str                     # public host (IP or DNS)
    port: int                       # 443
    uuid: str                       # client UUID
    pbk: str                        # reality public key
    sid: str = ""                   # reality short id
    sni: str = "www.microsoft.com"
    fingerprint: str = "chrome"     # chrome|firefox|ios|safari|android|edge
    flow: str = "xtls-rprx-vision"
    transport: str = "tcp"          # tcp|xhttp|ws|grpc
    xhttp_path: str = "/"
    xhttp_mode: str = "auto"
    region_hint: str = ""           # "MS"|"FI"|"DE"|... — для имени


# ======================================================================
# Detect User-Agent → выбор формата
# ======================================================================
def parse_user_agent(ua: str) -> str:
    """
    Возвращает один из: "v2raytun", "hiddify", "clash", "singbox", "default".

    Правила (по приоритету — самый специфичный первый):
      - Hiddify → base64-VLESS (его SingboxParser падает на YAML — пусть импортирует через base64)
      - sing-box, sfa, NekoBox, sfi → sing-box JSON
      - Clash, Stash, ClashX, ClashMeta, mihomo → Clash YAML
      - V2RayTun, v2rayN, v2rayNG, Streisand, Nekoray, Karing, Loon, Shadowrocket → VLESS+base64
      - Пусто или неопознано — default = VLESS plain (самый совместимый)
    """
    if not ua:
        return "default"
    u = ua.lower()
    # Hiddify identifies itself как "Hiddify" в UA. Hiddify-Next пытается парсить
    # через свой SingboxParser сначала и падает на любом не-JSON. Самый
    # совместимый формат для Hiddify — base64-encoded plain VLESS lines.
    # Hiddify получит список профилей и сам построит auto-switch group внутри.
    if "hiddify" in u:
        return "v2raytun"  # base64 — стабильнее чем YAML/JSON для Hiddify
    # Стандартный sing-box / NekoBox-Next / sfa / sfi / sfm
    if any(x in u for x in ("sing-box", "singbox", "nekobox", "sfa/", "sfi/", "sfm/")):
        return "singbox"
    # Clash и его форки (НЕ Hiddify — он отдельной веткой)
    if any(x in u for x in ("clash", "stash", "mihomo", "openclash")):
        return "clash"
    # V2RayTun (явно идентифицируется)
    if "v2raytun" in u:
        return "v2raytun"
    # default = plain VLESS lines
    return "default"


# ======================================================================
# VLESS URL builder (для plain & base64 формата)
# ======================================================================
def build_vless_url(p: Profile) -> str:
    """Формирует vless://uuid@host:port?...#name URL."""
    params = {
        "type": p.transport,
        "security": "reality",
        "pbk": p.pbk,
        "fp": p.fingerprint,
        "sni": p.sni,
        "sid": p.sid,
        "flow": p.flow if p.transport == "tcp" else "",
        "spx": "",
    }
    if p.transport == "xhttp":
        params["path"] = p.xhttp_path
        params["mode"] = p.xhttp_mode
        params["flow"] = ""  # XHTTP не использует flow
    qs = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items() if v != "")
    return f"vless://{p.uuid}@{p.server}:{p.port}?{qs}#{quote(p.name)}"


# ======================================================================
# 1. Plain VLESS lines (для v2rayNG, Streisand, Shadowrocket, default)
# ======================================================================
def render_plain_vless(profiles: list[Profile]) -> str:
    """\\n-разделённые vless:// строки + trailing \\n."""
    return "\n".join(build_vless_url(p) for p in profiles) + "\n"


# ======================================================================
# 2. base64 wrap (некоторые клиенты, такие как V2RayTun, ждут base64-encoded)
# ======================================================================
def render_base64_vless(profiles: list[Profile]) -> str:
    """base64(plain_vless_lines) — формат SIP008."""
    plain = render_plain_vless(profiles)
    return base64.b64encode(plain.encode("utf-8")).decode("ascii")


# ======================================================================
# 3. Clash YAML (для Hiddify, Clash, Stash, mihomo)
# ======================================================================
def _clash_proxy_node(p: Profile) -> dict:
    """Один proxy в Clash формате (mihomo / clash-meta / Hiddify)."""
    node: dict = {
        "name": p.name,
        "type": "vless",
        "server": p.server,
        "port": p.port,
        "uuid": p.uuid,
        "udp": True,
        "tls": True,
        "servername": p.sni,
        "client-fingerprint": p.fingerprint,
        "reality-opts": {
            "public-key": p.pbk,
            "short-id": p.sid,
        },
    }
    if p.transport == "tcp":
        node["network"] = "tcp"
        node["flow"] = p.flow  # xtls-rprx-vision
    elif p.transport == "xhttp":
        node["network"] = "xhttp"
        node["xhttp-opts"] = {
            "mode": p.xhttp_mode,
            "path": p.xhttp_path,
        }
    elif p.transport == "ws":
        node["network"] = "ws"
        node["ws-opts"] = {"path": p.xhttp_path or "/"}
    elif p.transport == "grpc":
        node["network"] = "grpc"
        node["grpc-opts"] = {"grpc-service-name": p.xhttp_path or "/"}
    else:
        node["network"] = "tcp"
    return node


def render_clash_yaml(profiles: list[Profile], sub_name: str = "Xservis") -> str:
    """
    Минимальный Clash/Hiddify YAML с auto-switch (url-test) группой.

    Логика:
      proxy-groups:
        - name: Xservis        # selector — выбор юзером (или Auto)
          type: select
          proxies: [Auto, <profile-1>, <profile-2>, ...]
        - name: Auto           # url-test — авто-выбор лучшего по latency
          type: url-test
          proxies: [<profile-1>, <profile-2>, ...]
          url: https://www.gstatic.com/generate_204
          interval: 300
          tolerance: 50
    """
    if not profiles:
        return "# empty subscription\n"

    proxy_nodes = [_clash_proxy_node(p) for p in profiles]
    names = [p.name for p in profiles]
    auto_name = f"{sub_name}-Auto"

    config = {
        "mixed-port": 7890,
        "allow-lan": False,
        "mode": "rule",
        "log-level": "warning",
        "ipv6": True,
        # Hiddify / mihomo рекомендуют это
        "external-controller": "127.0.0.1:9090",
        "dns": {
            "enable": True,
            "ipv6": True,
            "default-nameserver": ["1.1.1.1", "8.8.8.8"],
            "enhanced-mode": "fake-ip",
            "fake-ip-range": "198.18.0.1/16",
            "nameserver": ["https://1.1.1.1/dns-query", "https://8.8.8.8/dns-query"],
        },
        "proxies": proxy_nodes,
        "proxy-groups": [
            {
                "name": sub_name,
                "type": "select",
                "proxies": [auto_name] + names + ["DIRECT"],
            },
            {
                "name": auto_name,
                "type": "url-test",
                "proxies": names,
                "url": "https://www.gstatic.com/generate_204",
                "interval": 300,
                "tolerance": 50,
                "lazy": False,
            },
        ],
        "rules": [
            f"MATCH,{sub_name}",
        ],
    }

    return _to_yaml(config)


# ======================================================================
# Простой YAML-сериализатор (без зависимости от PyYAML — он не во всех окружениях)
# ======================================================================
def _to_yaml(obj, indent: int = 0) -> str:
    """Минимальный YAML emitter под наши данные (dict, list, str, int, bool)."""
    sp = "  " * indent
    if isinstance(obj, dict):
        if not obj:
            return "{}\n"
        out = []
        for k, v in obj.items():
            if isinstance(v, (dict, list)) and v:
                out.append(f"{sp}{k}:")
                out.append(_to_yaml(v, indent + 1))
            elif isinstance(v, list) and not v:
                out.append(f"{sp}{k}: []")
            elif isinstance(v, dict) and not v:
                out.append(f"{sp}{k}: {{}}")
            else:
                out.append(f"{sp}{k}: {_yaml_scalar(v)}")
        return "\n".join(out) + ("\n" if indent == 0 else "")
    if isinstance(obj, list):
        if not obj:
            return f"{sp}[]"
        out = []
        for item in obj:
            if isinstance(item, dict):
                first = True
                for k, v in item.items():
                    prefix = "- " if first else "  "
                    first = False
                    if isinstance(v, (dict, list)) and v:
                        out.append(f"{sp}{prefix}{k}:")
                        out.append(_to_yaml(v, indent + 2))
                    else:
                        out.append(f"{sp}{prefix}{k}: {_yaml_scalar(v)}")
            else:
                out.append(f"{sp}- {_yaml_scalar(item)}")
        return "\n".join(out)
    return f"{sp}{_yaml_scalar(obj)}"


def _yaml_scalar(v) -> str:
    if v is True:
        return "true"
    if v is False:
        return "false"
    if v is None:
        return "null"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    # Если строка содержит спец-символы YAML — кавычим
    if any(c in s for c in (":", "#", "\"", "'", "\n", "{", "}", "[", "]", ",", "&", "*", "!", "|", ">", "%", "@", "`")) or s.strip() != s or s == "":
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


# ======================================================================
# 4. sing-box JSON (для sing-box, NekoBox, sfa)
# ======================================================================
def _singbox_outbound(p: Profile) -> dict:
    """Один outbound в sing-box формате."""
    out: dict = {
        "type": "vless",
        "tag": p.name,
        "server": p.server,
        "server_port": p.port,
        "uuid": p.uuid,
        "tls": {
            "enabled": True,
            "server_name": p.sni,
            "utls": {"enabled": True, "fingerprint": p.fingerprint},
            "reality": {
                "enabled": True,
                "public_key": p.pbk,
                "short_id": p.sid,
            },
        },
    }
    if p.transport == "tcp":
        out["flow"] = p.flow
    elif p.transport == "xhttp":
        out["transport"] = {"type": "xhttp", "path": p.xhttp_path, "mode": p.xhttp_mode}
    elif p.transport == "ws":
        out["transport"] = {"type": "ws", "path": p.xhttp_path or "/"}
    elif p.transport == "grpc":
        out["transport"] = {"type": "grpc", "service_name": p.xhttp_path or "grpc"}
    return out


def render_singbox_json(profiles: list[Profile], sub_name: str = "Xservis") -> str:
    """sing-box config с urltest auto-switch outbound."""
    if not profiles:
        return json.dumps({"outbounds": []}, ensure_ascii=False, indent=2)

    auto = f"{sub_name}-Auto"
    names = [p.name for p in profiles]
    proxy_outs = [_singbox_outbound(p) for p in profiles]

    config = {
        "log": {"level": "warn", "timestamp": True},
        "dns": {
            "servers": [
                {"tag": "remote", "address": "https://1.1.1.1/dns-query", "detour": sub_name},
                {"tag": "local", "address": "1.1.1.1", "detour": "direct"},
            ],
            "rules": [{"clash_mode": "Direct", "server": "local"}],
            "final": "remote",
            "strategy": "ipv4_only",
        },
        "inbounds": [
            {
                "type": "tun",
                "tag": "tun-in",
                "interface_name": "tun0",
                "inet4_address": "172.19.0.1/30",
                "auto_route": True,
                "strict_route": True,
                "stack": "system",
                "sniff": True,
            }
        ],
        "outbounds": [
            {
                "type": "selector",
                "tag": sub_name,
                "outbounds": [auto] + names + ["direct"],
                "default": auto,
            },
            {
                "type": "urltest",
                "tag": auto,
                "outbounds": names,
                "url": "https://www.gstatic.com/generate_204",
                "interval": "5m",
                "tolerance": 50,
            },
            *proxy_outs,
            {"type": "direct", "tag": "direct"},
            {"type": "block", "tag": "block"},
            {"type": "dns", "tag": "dns-out"},
        ],
        "route": {
            "rules": [
                {"protocol": "dns", "outbound": "dns-out"},
                {"clash_mode": "Direct", "outbound": "direct"},
                {"clash_mode": "Global", "outbound": sub_name},
            ],
            "auto_detect_interface": True,
            "final": sub_name,
        },
    }
    return json.dumps(config, ensure_ascii=False, indent=2)


# ======================================================================
# Subscription-Userinfo header
# ======================================================================
def format_userinfo(used_up: int, used_down: int, total: int, expire_ts: int) -> str:
    """SIP008-style userinfo string for the header."""
    return f"upload={used_up}; download={used_down}; total={total}; expire={expire_ts}"


# ======================================================================
# Main entry — выбор формата по UA
# ======================================================================
def render_subscription(
    profiles: list[Profile],
    user_agent: str,
    sub_name: str = "Xservis",
) -> tuple[str, str]:
    """
    Главный диспатчер. Возвращает (body, content_type).

    user_agent → формат:
      hiddify, clash → Clash YAML       → text/yaml
      singbox → sing-box JSON           → application/json
      v2raytun → base64 vless           → text/plain
      default → plain vless lines       → text/plain
    """
    fmt = parse_user_agent(user_agent)
    if fmt in ("hiddify", "clash"):
        return render_clash_yaml(profiles, sub_name), "text/yaml; charset=utf-8"
    if fmt == "singbox":
        return render_singbox_json(profiles, sub_name), "application/json; charset=utf-8"
    if fmt == "v2raytun":
        return render_base64_vless(profiles), "text/plain; charset=utf-8"
    # default
    return render_plain_vless(profiles), "text/plain; charset=utf-8"
