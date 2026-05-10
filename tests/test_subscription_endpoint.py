from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING

import yaml

from xservis.auth import make_token

if TYPE_CHECKING:
    from httpx import AsyncClient


async def test_subscription_rejects_missing_token(client: AsyncClient) -> None:
    resp = await client.get("/api/sub/123")
    assert resp.status_code == 403


async def test_subscription_rejects_wrong_token(client: AsyncClient) -> None:
    resp = await client.get("/api/sub/123?token=garbage")
    assert resp.status_code == 403


async def test_subscription_serves_base64_for_v2raytun(client: AsyncClient) -> None:
    token = make_token(123, "test-secret")
    resp = await client.get(
        "/api/sub/123",
        params={"token": token},
        headers={"User-Agent": "V2RayTun/2.7.0"},
    )
    assert resp.status_code == 200
    assert resp.headers["Profile-Title"] == "Xservis"
    assert resp.headers["Profile-Update-Interval"] == "24"
    assert "Subscription-Userinfo" in resp.headers
    assert resp.headers["Content-Disposition"] == 'attachment; filename="Xservis"'

    decoded = base64.b64decode(resp.text).decode("utf-8")
    assert "vless://" in decoded
    assert "#Xservis-DE-1" in decoded
    assert "#Xservis-NL-1" in decoded


async def test_subscription_serves_clash_for_hiddify(client: AsyncClient) -> None:
    token = make_token(456, "test-secret")
    resp = await client.get(
        "/api/sub/456",
        params={"token": token},
        headers={"User-Agent": "Hiddify/2.0"},
    )
    assert resp.status_code == 200
    cfg = yaml.safe_load(resp.text)
    assert any(g["type"] == "url-test" for g in cfg["proxy-groups"])
    assert cfg["proxies"][0]["type"] == "vless"


async def test_subscription_serves_singbox_for_sing_box(client: AsyncClient) -> None:
    token = make_token(789, "test-secret")
    resp = await client.get(
        "/api/sub/789",
        params={"token": token},
        headers={"User-Agent": "sing-box/1.8.0"},
    )
    assert resp.status_code == 200
    cfg = json.loads(resp.text)
    selectors = [ob for ob in cfg["outbounds"] if ob.get("tag") == "Xservis"]
    assert selectors and selectors[0]["type"] == "selector"


async def test_subscription_creates_user_on_first_request(client: AsyncClient) -> None:
    token = make_token(10001, "test-secret")
    resp = await client.get("/api/sub/10001", params={"token": token})
    assert resp.status_code == 200
    info = resp.headers["Subscription-Userinfo"]
    assert "download=0" in info
    assert "total=" in info


async def test_healthz(client: AsyncClient) -> None:
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    names = {n["name"] for n in body["nodes"]}
    assert names == {"Xservis-DE-1", "Xservis-NL-1"}
    assert all(n["alive"] for n in body["nodes"])
