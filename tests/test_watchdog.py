from __future__ import annotations

import pytest

from xservis.settings import ServerConfig, Settings, WatchdogConfig
from xservis.state import NodeRegistry
from xservis.watchdog.checker import ProbeResult
from xservis.watchdog.main import run_watchdog


def _settings(servers: list[ServerConfig]) -> Settings:
    return Settings(
        servers=servers,
        watchdog=WatchdogConfig(
            enabled=True,
            interval_seconds=0,
            tcp_timeout=0.1,
            failure_threshold=2,
            recovery_threshold=2,
        ),
    )


def _srv(name: str) -> ServerConfig:
    return ServerConfig(
        name=name,
        host=f"{name.lower()}.example.com",
        uuid="00000000-0000-0000-0000-000000000000",
        sni="www.example.com",
        public_key="PK",
        short_id="SI",
    )


@pytest.mark.asyncio
async def test_watchdog_marks_node_blocked_after_threshold() -> None:
    a = _srv("A")
    b = _srv("B")
    settings = _settings([a, b])
    registry = NodeRegistry([a, b])

    async def probe(host: str, _port: int, _timeout: float) -> ProbeResult:
        if host.startswith("a."):
            return ProbeResult(ok=True, latency_ms=10.0)
        return ProbeResult(ok=False, latency_ms=100.0, error="conn refused")

    notifications: list[str] = []

    async def notify(msg: str) -> None:
        notifications.append(msg)

    await run_watchdog(settings, registry=registry, probe=probe, notify=notify, iterations=2)

    assert registry.get("A").alive
    assert not registry.get("B").alive
    assert any("node blocked: B" in m for m in notifications)


@pytest.mark.asyncio
async def test_watchdog_recovers_node() -> None:
    a = _srv("A")
    settings = _settings([a])
    registry = NodeRegistry([a])

    state = {"calls": 0}

    async def probe(_host: str, _port: int, _timeout: float) -> ProbeResult:
        state["calls"] += 1
        # First two calls fail, then it recovers.
        if state["calls"] <= 2:
            return ProbeResult(ok=False, latency_ms=10.0, error="x")
        return ProbeResult(ok=True, latency_ms=12.0)

    notifications: list[str] = []

    async def notify(msg: str) -> None:
        notifications.append(msg)

    await run_watchdog(settings, registry=registry, probe=probe, notify=notify, iterations=4)

    assert registry.get("A").alive
    assert any("node blocked: A" in m for m in notifications)
    assert any("node restored: A" in m for m in notifications)


@pytest.mark.asyncio
async def test_watchdog_disabled_returns_immediately() -> None:
    a = _srv("A")
    settings = Settings(servers=[a], watchdog=WatchdogConfig(enabled=False))
    registry = NodeRegistry([a])

    calls = 0

    async def probe(_host: str, _port: int, _timeout: float) -> ProbeResult:
        nonlocal calls
        calls += 1
        return ProbeResult(ok=True, latency_ms=1.0)

    await run_watchdog(settings, registry=registry, probe=probe, iterations=5)
    assert calls == 0
