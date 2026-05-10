from xservis.settings import ServerConfig
from xservis.state import NodeRegistry


def _server(name: str) -> ServerConfig:
    return ServerConfig(
        name=name,
        host=f"{name.lower()}.example.com",
        uuid="00000000-0000-0000-0000-000000000000",
        sni="www.example.com",
        public_key="PK",
        short_id="SI",
    )


def test_all_alive_initially() -> None:
    reg = NodeRegistry([_server("A"), _server("B")])
    assert reg.alive_names() == {"A", "B"}


def test_alive_servers_filters_blocked() -> None:
    a = _server("A")
    b = _server("B")
    reg = NodeRegistry([a, b])

    health_b = reg.get("B")
    for _ in range(3):
        health_b.record_failure("blocked", failure_threshold=3)

    alive = reg.alive_servers([a, b])
    assert [s.name for s in alive] == ["A"]


def test_alive_servers_falls_back_to_all_when_none_alive() -> None:
    a = _server("A")
    b = _server("B")
    reg = NodeRegistry([a, b])

    for name in ("A", "B"):
        health = reg.get(name)
        for _ in range(3):
            health.record_failure("blocked", failure_threshold=3)

    alive = reg.alive_servers([a, b])
    # Better to give clients a chance to connect than to hand back nothing.
    assert [s.name for s in alive] == ["A", "B"]


def test_recovery_threshold_required_to_revive() -> None:
    a = _server("A")
    reg = NodeRegistry([a])
    health = reg.get("A")

    for _ in range(3):
        health.record_failure("blocked", failure_threshold=3)
    assert not health.alive

    # Single success isn't enough.
    health.record_success(latency_ms=10.0, recovery_threshold=2)
    assert not health.alive

    health.record_success(latency_ms=11.0, recovery_threshold=2)
    assert health.alive
