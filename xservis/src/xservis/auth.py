"""HMAC-signed subscription tokens.

Subscription URLs include a token tied to the user_id so that simply
guessing user ids does not leak working configs. The token is opaque to
the client and validated server-side.
"""

from __future__ import annotations

import hashlib
import hmac


def make_token(user_id: int, secret: str) -> str:
    """Return an HMAC-SHA256 token for ``user_id``.

    The token is hex-encoded so it survives URL paths and query strings.
    """

    digest = hmac.new(
        secret.encode("utf-8"),
        str(user_id).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest


def verify_token(user_id: int, token: str, secret: str) -> bool:
    """Constant-time check that ``token`` was produced by :func:`make_token`."""

    expected = make_token(user_id, secret)
    return hmac.compare_digest(expected, token)
