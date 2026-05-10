import pytest

from xservis.backend.formatters import Format, detect_format


@pytest.mark.parametrize(
    ("ua", "expected"),
    [
        ("ClashforAndroid/2.5.12", Format.CLASH),
        ("Stash/2.5", Format.CLASH),
        ("mihomo/1.18", Format.CLASH),
        ("Hiddify/2.0.0", Format.CLASH),
        ("sing-box/1.8.0", Format.SINGBOX),
        ("SFA/1.8 (Android)", Format.SINGBOX),
        ("sfi/1.8 (iOS)", Format.SINGBOX),
        ("NekoBox/1.2.7", Format.SINGBOX),
        ("V2RayTun/2.7.0", Format.BASE64),
        ("V2RayNG/1.8", Format.BASE64),
        ("V2Box/1.0", Format.BASE64),
        ("Shadowrocket/2.2", Format.BASE64),
        ("Streisand/1.0", Format.BASE64),
        ("", Format.BASE64),
        ("curl/8.0.1", Format.BASE64),
    ],
)
def test_detect_format(ua: str, expected: str) -> None:
    assert detect_format(ua) == expected
