"""Watchdog loop.

Runs periodic TCP probes against every configured node, updates the
shared :class:`NodeRegistry`, and notifies the admin chat when a node
flips between alive and blocked.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from ..settings import ServerConfig, Settings, load_settings
from ..state import NodeRegistry
from .checker import ProbeResult, probe_tcp

log = logging.getLogger("xservis.watchdog")

ProbeFn = Callable[[str, int, float], Awaitable[ProbeResult]]
NotifyFn = Callable[[str], Awaitable[None]]


async def run_watchdog(
    settings: Settings | None = None,
    *,
    registry: NodeRegistry | None = None,
    probe: ProbeFn | None = None,
    notify: NotifyFn | None = None,
    iterations: int | None = None,
) -> None:
    """Run the watchdog loop.

    Parameters
    ----------
    settings:
        Pre-loaded :class:`Settings`. If omitted, loaded from disk.
    registry:
        Optional pre-existing registry. If omitted, a new one is created.
    probe:
        Injection point for tests; defaults to a real TCP probe.
    notify:
        Coroutine called with a human-readable message every time a node
        flips state. Defaults to a no-op.
    iterations:
        Limit the number of polling rounds (used by tests). ``None`` means
        run forever.
    """

    settings = settings or load_settings()
    registry = registry or NodeRegistry(settings.servers)
    probe_fn: ProbeFn = probe or probe_tcp
    notify_fn: NotifyFn = notify or _noop

    if not settings.watchdog.enabled:
        log.info("watchdog disabled in config")
        return

    round_idx = 0
    while iterations is None or round_idx < iterations:
        await _run_round(settings, registry, probe_fn, notify_fn)
        round_idx += 1
        if iterations is not None and round_idx >= iterations:
            return
        await asyncio.sleep(settings.watchdog.interval_seconds)


async def _run_round(
    settings: Settings,
    registry: NodeRegistry,
    probe: ProbeFn,
    notify: NotifyFn,
) -> None:
    """Probe every node concurrently and update the registry."""

    timeout = settings.watchdog.tcp_timeout
    failure_threshold = settings.watchdog.failure_threshold
    recovery_threshold = settings.watchdog.recovery_threshold

    async def probe_one(server: ServerConfig) -> tuple[ServerConfig, ProbeResult]:
        return server, await probe(server.host, server.port, timeout)

    results = await asyncio.gather(
        *(probe_one(s) for s in settings.servers), return_exceptions=False
    )

    for server, result in results:
        health = registry.get(server.name)
        if result.ok:
            transitioned = health.record_success(
                result.latency_ms, recovery_threshold=recovery_threshold
            )
            if transitioned:
                msg = f"[Xservis] node restored: {server.name}"
                log.info(msg)
                await notify(msg)
        else:
            transitioned = health.record_failure(
                result.error or "unknown error",
                failure_threshold=failure_threshold,
            )
            if transitioned:
                msg = (
                    f"[Xservis] node blocked: {server.name} "
                    f"({server.host}:{server.port}) — {result.error}"
                )
                log.warning(msg)
                await notify(msg)


async def _noop(_: str) -> None:
    return None


def main() -> None:
    import asyncio
    import logging

    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_watchdog())


if __name__ == "__main__":
    main()


__all__ = ["NotifyFn", "ProbeFn", "run_watchdog"]
