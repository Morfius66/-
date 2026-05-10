"""CLI entry points for the Xservis components."""

from __future__ import annotations

import asyncio
import logging

import typer
import uvicorn

from .auth import make_token
from .settings import load_settings

app = typer.Typer(add_completion=False, help="Xservis service control")


@app.command()
def serve(
    host: str | None = None,
    port: int | None = None,
    config: str | None = None,
) -> None:
    """Run the FastAPI subscription backend (with embedded watchdog)."""

    settings = load_settings(config)
    uvicorn.run(
        "xservis.backend.app:create_app",
        host=host or settings.backend.host,
        port=port or settings.backend.port,
        factory=True,
        log_level="info",
    )


@app.command()
def bot(config: str | None = None) -> None:
    """Run the Telegram bot polling loop."""

    from .bot.main import run_bot

    logging.basicConfig(level=logging.INFO)
    settings = load_settings(config)
    asyncio.run(run_bot(settings))


@app.command()
def watchdog(config: str | None = None) -> None:
    """Run the watchdog as a standalone process (no FastAPI / no bot).

    This is mostly useful for debugging — in production the watchdog runs
    inside the FastAPI process so it shares the in-memory registry with
    the subscription endpoint.
    """

    from .state import NodeRegistry
    from .watchdog.main import run_watchdog

    logging.basicConfig(level=logging.INFO)
    settings = load_settings(config)
    registry = NodeRegistry(settings.servers)
    asyncio.run(run_watchdog(settings, registry=registry))


@app.command("token")
def token(user_id: int, config: str | None = None) -> None:
    """Print the signed subscription URL for ``user_id``."""

    settings = load_settings(config)
    token_value = make_token(user_id, settings.backend.token_secret)
    base = settings.backend.public_url.rstrip("/")
    path = settings.backend.subscription_path.rstrip("/")
    typer.echo(f"{base}{path}/{user_id}?token={token_value}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
