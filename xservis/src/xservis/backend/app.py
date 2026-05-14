"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

from ..db import init_db, make_engine, make_session_factory
from ..settings import Settings, load_settings
from ..state import NodeRegistry
from ..watchdog.main import run_watchdog
from .routes import build_router
from .viral import build_viral_router

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

log = logging.getLogger("xservis.backend")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine: AsyncEngine = app.state.engine
    settings: Settings = app.state.settings
    registry: NodeRegistry = app.state.registry

    await init_db(engine)

    watchdog_task: asyncio.Task[None] | None = None
    if settings.watchdog.enabled and settings.servers:
        watchdog_task = asyncio.create_task(
            run_watchdog(settings, registry=registry),
            name="xservis-watchdog",
        )
        app.state.watchdog_task = watchdog_task

    try:
        yield
    finally:
        if watchdog_task is not None:
            watchdog_task.cancel()
            try:
                await watchdog_task
            except asyncio.CancelledError:
                log.debug("watchdog cancelled")
            except Exception:
                log.exception("watchdog crashed during shutdown")
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI app.

    Both the dev runner (``xservis serve``) and the test suite use this.
    The watchdog runs as an asyncio task on the same loop so it shares the
    in-memory :class:`NodeRegistry` with the subscription endpoint — that
    is what lets us hide a freshly blocked node from clients within seconds.
    """

    settings = settings or load_settings()

    app = FastAPI(
        title="Xservis subscription API",
        version="0.1.0",
        lifespan=_lifespan,
    )

    engine = make_engine(settings.database.url)
    session_factory: async_sessionmaker[AsyncSession] = make_session_factory(engine)
    registry = NodeRegistry(settings.servers)

    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.registry = registry

    app.include_router(build_router(settings, registry, session_factory))
    app.include_router(build_viral_router(settings, session_factory))
    return app


__all__ = ["create_app"]
