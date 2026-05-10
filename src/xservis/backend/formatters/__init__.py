"""Format VLESS server lists for the various subscription clients."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base64_vless import build_base64_vless
from .clash import build_clash_yaml
from .singbox import build_singbox_json

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ...settings import ServerConfig


class Format:
    """Enumeration of supported output formats."""

    BASE64 = "base64"
    CLASH = "clash"
    SINGBOX = "singbox"


def detect_format(user_agent: str) -> str:
    """Return the format to serve based on the client's User-Agent.

    The mapping follows the spec in the Xservis subscription knowledge note.
    Unknown User-Agents fall back to base64 VLESS, which the broadest set
    of clients accept.
    """

    ua = (user_agent or "").lower()
    if any(token in ua for token in ("clash", "stash", "mihomo")):
        return Format.CLASH
    if any(token in ua for token in ("sing-box", "sfa", "sfi", "nekobox", "nekoray")):
        return Format.SINGBOX
    if "hiddify" in ua:
        return Format.CLASH
    if any(
        token in ua
        for token in (
            "v2raytun",
            "v2rayng",
            "v2rayn",
            "v2box",
            "shadowrocket",
            "streisand",
        )
    ):
        return Format.BASE64
    return Format.BASE64


def render(format_: str, servers: Sequence[ServerConfig]) -> str:
    """Render ``servers`` in the requested format."""

    if format_ == Format.CLASH:
        return build_clash_yaml(servers)
    if format_ == Format.SINGBOX:
        return build_singbox_json(servers)
    return build_base64_vless(servers)


__all__ = [
    "Format",
    "build_base64_vless",
    "build_clash_yaml",
    "build_singbox_json",
    "detect_format",
    "render",
]
