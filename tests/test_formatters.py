from __future__ import annotations

import base64
import json

import yaml

from xservis.backend.formatters import (
    build_base64_vless,
    build_clash_yaml,
    build_singbox_json,
)
from xservis.backend.formatters.base64_vless import build_vless_uri
from xservis.backend.formatters.clash import AUTO_GROUP_NAME, SELECT_GROUP_NAME
from xservis.backend.formatters.singbox import AUTO_TAG, SELECT_TAG
from xservis.settings import ServerConfig


def _servers() -> list[ServerConfig]:
    return [
        ServerConfig(
            name="Xservis-DE-1",
            host="de1.xservis.pro",
            port=443,
            uuid="11111111-1111-1111-1111-111111111111",
            sni="www.cloudflare.com",
            public_key="PUBKEY1",
            short_id="abcd1234",
        ),
        ServerConfig(
            name="Xservis-NL-1",
            host="nl1.xservis.pro",
            port=443,
            uuid="22222222-2222-2222-2222-222222222222",
            sni="www.microsoft.com",
            public_key="PUBKEY2",
            short_id="efef5678",
        ),
    ]


def test_vless_uri_shape() -> None:
    server = _servers()[0]
    uri = build_vless_uri(server)
    assert uri.startswith("vless://11111111-1111-1111-1111-111111111111@de1.xservis.pro:443?")
    assert "security=reality" in uri
    assert "sni=www.cloudflare.com" in uri
    assert "pbk=PUBKEY1" in uri
    assert "sid=abcd1234" in uri
    assert "flow=xtls-rprx-vision" in uri
    assert "fp=chrome" in uri
    assert uri.endswith("#Xservis-DE-1")


def test_base64_vless_decodes_to_one_line_per_server() -> None:
    encoded = build_base64_vless(_servers())
    decoded = base64.b64decode(encoded).decode("utf-8")
    lines = [line for line in decoded.splitlines() if line.strip()]
    assert len(lines) == 2
    assert all(line.startswith("vless://") for line in lines)
    assert lines[0].endswith("#Xservis-DE-1")
    assert lines[1].endswith("#Xservis-NL-1")


def test_clash_yaml_has_url_test_group_with_all_proxies() -> None:
    text = build_clash_yaml(_servers())
    cfg = yaml.safe_load(text)
    assert isinstance(cfg, dict)

    proxies = cfg["proxies"]
    assert [p["name"] for p in proxies] == ["Xservis-DE-1", "Xservis-NL-1"]
    assert all(p["type"] == "vless" for p in proxies)
    assert all(p["tls"] is True for p in proxies)
    assert proxies[0]["reality-opts"]["public-key"] == "PUBKEY1"
    assert proxies[0]["servername"] == "www.cloudflare.com"
    assert proxies[0]["flow"] == "xtls-rprx-vision"

    groups = {g["name"]: g for g in cfg["proxy-groups"]}
    auto = groups[AUTO_GROUP_NAME]
    assert auto["type"] == "url-test"
    assert auto["proxies"] == ["Xservis-DE-1", "Xservis-NL-1"]
    select = groups[SELECT_GROUP_NAME]
    assert select["type"] == "select"
    assert AUTO_GROUP_NAME in select["proxies"]


def test_singbox_json_has_urltest_default() -> None:
    text = build_singbox_json(_servers())
    cfg = json.loads(text)

    outbounds = {ob["tag"]: ob for ob in cfg["outbounds"]}
    select = outbounds[SELECT_TAG]
    auto = outbounds[AUTO_TAG]

    assert select["type"] == "selector"
    assert select["default"] == AUTO_TAG
    assert AUTO_TAG in select["outbounds"]

    assert auto["type"] == "urltest"
    assert auto["outbounds"] == ["Xservis-DE-1", "Xservis-NL-1"]
    assert auto["url"].startswith("http")

    de = outbounds["Xservis-DE-1"]
    assert de["type"] == "vless"
    assert de["tls"]["enabled"] is True
    assert de["tls"]["reality"]["enabled"] is True
    assert de["tls"]["reality"]["public_key"] == "PUBKEY1"
    assert de["tls"]["utls"]["fingerprint"] == "chrome"

    assert cfg["route"]["final"] == SELECT_TAG
    assert cfg["route"]["auto_detect_interface"] is True
