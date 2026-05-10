"""Render the subscription as a Clash / Mihomo / Hiddify YAML."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ...settings import ServerConfig

AUTO_GROUP_NAME = "Xservis-Auto"
SELECT_GROUP_NAME = "Xservis"
HEALTHCHECK_URL = "http://www.gstatic.com/generate_204"


def _proxy(server: ServerConfig) -> dict[str, Any]:
    return {
        "name": server.name,
        "type": "vless",
        "server": server.host,
        "port": server.port,
        "uuid": server.uuid,
        "network": "tcp",
        "tls": True,
        "udp": True,
        "flow": server.flow,
        "servername": server.sni,
        "client-fingerprint": server.fingerprint,
        "reality-opts": {
            "public-key": server.public_key,
            "short-id": server.short_id,
        },
    }


def build_clash_yaml(servers: Sequence[ServerConfig]) -> str:
    """Return a Clash YAML document.

    A ``url-test`` group named ``Xservis-Auto`` lets clients pick the
    fastest node automatically and re-test every 5 minutes; a ``select``
    group named ``Xservis`` gives the user manual override.
    """

    proxy_list = [_proxy(s) for s in servers]
    proxy_names = [s.name for s in servers]

    config: dict[str, Any] = {
        "mixed-port": 7890,
        "allow-lan": False,
        "mode": "rule",
        "log-level": "info",
        "external-controller": "127.0.0.1:9090",
        "dns": {
            "enable": True,
            "ipv6": False,
            "nameserver": [
                "https://1.1.1.1/dns-query",
                "https://8.8.8.8/dns-query",
            ],
            "fallback": ["https://dns.google/dns-query"],
        },
        "proxies": proxy_list,
        "proxy-groups": [
            {
                "name": AUTO_GROUP_NAME,
                "type": "url-test",
                "url": HEALTHCHECK_URL,
                "interval": 300,
                "tolerance": 50,
                "proxies": proxy_names or [SELECT_GROUP_NAME],
            },
            {
                "name": SELECT_GROUP_NAME,
                "type": "select",
                "proxies": [AUTO_GROUP_NAME, *proxy_names],
            },
        ],
        "rules": [
            f"MATCH,{SELECT_GROUP_NAME}",
        ],
    }

    return yaml.safe_dump(config, sort_keys=False, allow_unicode=True)


__all__ = ["AUTO_GROUP_NAME", "SELECT_GROUP_NAME", "build_clash_yaml"]
