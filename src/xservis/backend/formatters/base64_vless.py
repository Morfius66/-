"""Render the subscription as a base64-encoded list of VLESS URIs."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING
from urllib.parse import quote

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ...settings import ServerConfig


def build_vless_uri(server: ServerConfig) -> str:
    """Return one ``vless://...`` URI for ``server``.

    Reality parameters (``security=reality``, ``pbk``, ``sid``, ``sni``,
    ``fp``) are encoded as query parameters; the visible remark after
    ``#`` becomes the per-node label inside the client.
    """

    params = [
        ("encryption", "none"),
        ("security", "reality"),
        ("sni", server.sni),
        ("fp", server.fingerprint),
        ("pbk", server.public_key),
        ("sid", server.short_id),
        ("type", "tcp"),
        ("flow", server.flow),
    ]
    query = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params)
    remark = quote(server.name, safe="")
    return f"vless://{server.uuid}@{server.host}:{server.port}?{query}#{remark}"


def build_base64_vless(servers: Sequence[ServerConfig]) -> str:
    """Return the full base64-encoded subscription body."""

    body = "\n".join(build_vless_uri(s) for s in servers) + "\n"
    return base64.b64encode(body.encode("utf-8")).decode("ascii")


__all__ = ["build_base64_vless", "build_vless_uri"]
