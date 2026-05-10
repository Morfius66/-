from datetime import UTC, datetime

from xservis.backend.headers import (
    PROFILE_FILENAME,
    PROFILE_TITLE,
    build_subscription_headers,
)


def test_required_headers_present() -> None:
    headers = build_subscription_headers(
        used_bytes=1234,
        total_bytes=10_000,
        expires_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
    assert headers["Profile-Title"] == PROFILE_TITLE == "Xservis"
    assert headers["Profile-Update-Interval"] == "24"
    assert headers["Content-Type"] == "text/plain; charset=utf-8"
    assert headers["Content-Disposition"] == f'attachment; filename="{PROFILE_FILENAME}"'


def test_subscription_userinfo_format() -> None:
    expires = datetime(2030, 1, 1, tzinfo=UTC)
    headers = build_subscription_headers(
        used_bytes=512,
        total_bytes=2048,
        expires_at=expires,
    )
    info = headers["Subscription-Userinfo"]
    assert "upload=0" in info
    assert "download=512" in info
    assert "total=2048" in info
    assert f"expire={int(expires.timestamp())}" in info


def test_naive_datetime_treated_as_utc() -> None:
    naive = datetime(2030, 1, 1)
    headers = build_subscription_headers(
        used_bytes=0,
        total_bytes=0,
        expires_at=naive,
    )
    aware = naive.replace(tzinfo=UTC)
    assert f"expire={int(aware.timestamp())}" in headers["Subscription-Userinfo"]
