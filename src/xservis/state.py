"""In-memory registry tracking the live health of each configured node.

The watchdog mutates this registry; the FastAPI subscription handler reads
it. A single instance lives on the FastAPI app state and on the watchdog
task so that the subscription endpoint and the watchdog share their view of
the world.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import NodeHealth

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .settings import ServerConfig


class NodeRegistry:
    """Thread-safe-enough registry of node health.

    The Python GIL makes simple dict mutations safe between asyncio tasks
    in the same loop; we don't need a lock because the only mutation
    pattern is a watchdog task replacing fields on a single ``NodeHealth``.
    """

    def __init__(self, servers: Iterable[ServerConfig]) -> None:
        self._health: dict[str, NodeHealth] = {
            server.name: NodeHealth(name=server.name) for server in servers
        }

    def get(self, name: str) -> NodeHealth:
        return self._health[name]

    def all(self) -> list[NodeHealth]:
        return list(self._health.values())

    def alive_names(self) -> set[str]:
        return {name for name, health in self._health.items() if health.alive}

    def alive_servers(self, servers: Iterable[ServerConfig]) -> list[ServerConfig]:
        """Filter ``servers`` to only those currently marked alive.

        If every server is currently down (e.g. fresh boot before the first
        watchdog tick, or a global outage), we return all servers anyway —
        better to give the client a chance to connect than to hand back an
        empty subscription.
        """

        alive = self.alive_names()
        kept = [s for s in servers if s.name in alive]
        return kept or list(servers)


__all__ = ["NodeRegistry"]
