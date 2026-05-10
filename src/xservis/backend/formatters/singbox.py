"""Render the subscription as a sing-box / SFA / NekoBox JSON config."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ...settings import ServerConfig

AUTO_TAG = "Xservis-Auto"
SELECT_TAG = "Xservis"
HEALTHCHECK_URL = "http://www.gstatic.com/generate_204"


def _outbound(server: ServerConfig) -> dict[str, Any]:
    return {
        "type": "vless",
        "tag": server.name,
        "server": server.host,
        "server_port": server.port,
        "uuid": server.uuid,
        "flow": server.flow,
        "packet_encoding": "xudp",
        "tls": {
            "enabled": True,
            "server_name": server.sni,
            "utls": {"enabled": True, "fingerprint": server.fingerprint},
            "reality": {
                "enabled": True,
                "public_key": server.public_key,
                "short_id": server.short_id,
            },
        },
    }


def build_singbox_json(servers: Sequence[ServerConfig]) -> str:
    """Return a sing-box JSON document with auto-switch by latency.

    The default outbound is a ``selector`` tagged ``Xservis`` whose
    default is ``Xservis-Auto``, a ``urltest`` group that probes
    ``http://www.gstatic.com/generate_204`` every 5 minutes.
    """

    outbounds: list[dict[str, Any]] = [_outbound(s) for s in servers]
    node_tags = [s.name for s in servers]

    auto: dict[str, Any] = {
        "type": "urltest",
        "tag": AUTO_TAG,
        "outbounds": node_tags or [SELECT_TAG],
        "url": HEALTHCHECK_URL,
        "interval": "5m",
        "tolerance": 50,
    }

    select: dict[str, Any] = {
        "type": "selector",
        "tag": SELECT_TAG,
        "outbounds": [AUTO_TAG, *node_tags],
        "default": AUTO_TAG,
    }

    direct: dict[str, Any] = {"type": "direct", "tag": "direct"}
    block: dict[str, Any] = {"type": "block", "tag": "block"}
    dns_out: dict[str, Any] = {"type": "dns", "tag": "dns-out"}

    config: dict[str, Any] = {
        "log": {"level": "info", "timestamp": True},
        "dns": {
            "servers": [
                {"tag": "google", "address": "tls://8.8.8.8", "detour": SELECT_TAG},
                {"tag": "local", "address": "local", "detour": "direct"},
            ],
            "rules": [
                {"outbound": ["any"], "server": "local"},
            ],
            "strategy": "prefer_ipv4",
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
            },
        ],
        "outbounds": [select, auto, *outbounds, direct, block, dns_out],
        "route": {
            "auto_detect_interface": True,
            "rules": [
                {"protocol": "dns", "outbound": "dns-out"},
                {"network": "udp", "port": 443, "outbound": "block"},
            ],
            "final": SELECT_TAG,
        },
        "experimental": {
            "clash_api": {"external_controller": "127.0.0.1:9090"},
        },
    }

    return json.dumps(config, indent=2, ensure_ascii=False)


__all__ = ["AUTO_TAG", "SELECT_TAG", "build_singbox_json"]
