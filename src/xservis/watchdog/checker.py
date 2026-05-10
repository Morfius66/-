"""Async network probe used by the watchdog."""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass


@dataclass(slots=True)
class ProbeResult:
    ok: bool
    latency_ms: float
    error: str | None = None


async def probe_tcp(host: str, port: int, timeout: float) -> ProbeResult:
    """Open a TCP connection to ``host:port`` and report success + latency.

    A successful TCP handshake is enough to consider the node reachable
    from this machine. Deeper protocol probes (TLS / Reality handshake)
    require state we don't have here; if a Reality handshake fails the
    client itself will fall through ``url-test`` to the next node.
    """

    start = time.monotonic()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
    except TimeoutError as exc:
        return ProbeResult(ok=False, latency_ms=timeout * 1000, error=f"timeout: {exc}")
    except OSError as exc:
        elapsed_ms = (time.monotonic() - start) * 1000
        return ProbeResult(ok=False, latency_ms=elapsed_ms, error=str(exc))

    elapsed_ms = (time.monotonic() - start) * 1000
    writer.close()
    with contextlib.suppress(OSError):
        # Some peers RST instead of FIN-ACK; that's fine for a probe.
        await writer.wait_closed()
    # Touch reader so static type-checkers don't whine about an unused name.
    _ = reader
    return ProbeResult(ok=True, latency_ms=elapsed_ms)


__all__ = ["ProbeResult", "probe_tcp"]
