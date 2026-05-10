"""Build the response headers for the subscription endpoint.

The headers follow the SIP008 / V2Board convention used by V2RayTun,
Hiddify, Clash, sing-box, NekoBox, and friends. The most important one is
``Profile-Title: Xservis``: without it most clients use the URL or domain
as the visible profile name.
"""

from __future__ import annotations

from datetime import UTC, datetime

PROFILE_TITLE = "Xservis"
PROFILE_FILENAME = "Xservis"
DEFAULT_UPDATE_INTERVAL_HOURS = 24


def build_subscription_headers(
    *,
    used_bytes: int,
    total_bytes: int,
    expires_at: datetime,
    update_interval_hours: int = DEFAULT_UPDATE_INTERVAL_HOURS,
    profile_title: str = PROFILE_TITLE,
) -> dict[str, str]:
    """Return the subscription headers for one user."""

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    expire_ts = int(expires_at.timestamp())
    upload = 0
    download = max(0, used_bytes)
    total = max(0, total_bytes)

    return {
        "Content-Type": "text/plain; charset=utf-8",
        "Content-Disposition": f'attachment; filename="{PROFILE_FILENAME}"',
        "Profile-Title": profile_title,
        "Profile-Update-Interval": str(update_interval_hours),
        "Subscription-Userinfo": (
            f"upload={upload}; download={download}; total={total}; expire={expire_ts}"
        ),
        "Cache-Control": "no-store",
    }


__all__ = [
    "DEFAULT_UPDATE_INTERVAL_HOURS",
    "PROFILE_FILENAME",
    "PROFILE_TITLE",
    "build_subscription_headers",
]
