"""Shared pytest fixtures."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from xservis.backend.app import create_app
from xservis.settings import (
    BackendConfig,
    DatabaseConfig,
    ServerConfig,
    Settings,
    WatchdogConfig,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def make_test_settings(
    *, watchdog_enabled: bool = False, servers: list[ServerConfig] | None = None
) -> Settings:
    return Settings(
        backend=BackendConfig(
            host="127.0.0.1",
            port=0,
            public_url="https://test.xservis.pro",
            subscription_path="/api/sub",
            token_secret="test-secret",
        ),
        database=DatabaseConfig(url="sqlite+aiosqlite:///:memory:"),
        watchdog=WatchdogConfig(enabled=watchdog_enabled),
        servers=servers
        if servers is not None
        else [
            ServerConfig(
                name="Xservis-DE-1",
                host="de1.example.com",
                port=443,
                uuid="00000000-0000-0000-0000-000000000001",
                sni="www.cloudflare.com",
                public_key="PUBKEY1",
                short_id="abcd1234",
            ),
            ServerConfig(
                name="Xservis-NL-1",
                host="nl1.example.com",
                port=443,
                uuid="00000000-0000-0000-0000-000000000002",
                sni="www.microsoft.com",
                public_key="PUBKEY2",
                short_id="efef5678",
            ),
        ],
    )


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app(make_test_settings())
    transport = ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=transport, base_url="http://test") as ac,
    ):
        yield ac
