"""Build 1-tap deep-link URLs for the popular VLESS / Reality clients.

Each function returns a URL that, when opened on a device with the right
client installed, imports the subscription with a single tap.
"""

from __future__ import annotations

import base64
from urllib.parse import quote


def _url_safe_b64(value: str) -> str:
    """Return a URL-safe base64 encoding (no padding) suitable for path segments."""

    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def v2raytun_import(subscription_url: str) -> str:
    """Deep-link for V2RayTun (Android + iOS)."""

    return f"v2raytun://import/{_url_safe_b64(subscription_url)}"


def v2rayng_import(subscription_url: str) -> str:
    """Deep-link for V2RayNG (Android)."""

    return f"v2rayng://install-sub?url={quote(subscription_url, safe='')}"


def hiddify_import(subscription_url: str) -> str:
    """Universal Hiddify deep-link (Android, iOS, desktop)."""

    return f"hiddify://import/{quote(subscription_url, safe='')}"


def streisand_import(subscription_url: str) -> str:
    """Deep-link for Streisand (iOS)."""

    return f"streisand://import/{quote(subscription_url, safe='')}"


def clash_import(subscription_url: str) -> str:
    """Deep-link for Clash for Android / Stash / Mihomo flavors."""

    return f"clash://install-config?url={quote(subscription_url, safe='')}"


__all__ = [
    "clash_import",
    "hiddify_import",
    "streisand_import",
    "v2rayng_import",
    "v2raytun_import",
]
