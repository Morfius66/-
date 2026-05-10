import base64

from xservis.bot.deeplinks import (
    clash_import,
    hiddify_import,
    streisand_import,
    v2rayng_import,
    v2raytun_import,
)

SUB = "https://xservis.pro/api/sub/123?token=abc"


def test_v2raytun_uses_url_safe_base64() -> None:
    link = v2raytun_import(SUB)
    assert link.startswith("v2raytun://import/")
    payload = link.removeprefix("v2raytun://import/")
    # add padding back for decode
    padding = "=" * (-len(payload) % 4)
    decoded = base64.urlsafe_b64decode(payload + padding).decode("utf-8")
    assert decoded == SUB


def test_other_deeplinks_have_correct_scheme() -> None:
    assert v2rayng_import(SUB).startswith("v2rayng://install-sub?url=")
    assert hiddify_import(SUB).startswith("hiddify://import/")
    assert streisand_import(SUB).startswith("streisand://import/")
    assert clash_import(SUB).startswith("clash://install-config?url=")


def test_v2rayng_deeplink_has_encoded_url() -> None:
    link = v2rayng_import(SUB)
    assert "https%3A%2F%2Fxservis.pro" in link


def test_token_param_is_encoded() -> None:
    sub_with_special = "https://xservis.pro/api/sub/1?token=a/b+c=d&extra"
    link = v2rayng_import(sub_with_special)
    assert "%2F" in link  # the / from a/b
    assert "%2B" in link  # the + from b+c
    assert "%3D" in link  # the = from c=d
