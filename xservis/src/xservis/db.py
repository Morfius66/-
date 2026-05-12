"""Async SQLAlchemy session helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .models import Base

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def make_engine(url: str) -> AsyncEngine:
    """Create an async SQLAlchemy engine for the given database URL."""

    return create_async_engine(url, echo=False, future=True)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db(engine: AsyncEngine) -> None:
    """Create all tables. Safe to call repeatedly."""

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Async generator that yields a single transactional session."""

    async with factory() as session:
        yield session
