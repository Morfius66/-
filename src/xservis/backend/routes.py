"""HTTP routes for the subscription backend."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from fastapi import APIRouter, Header, HTTPException, Request, Response

from ..auth import verify_token
from ..models import User
from .formatters import detect_format, render
from .headers import build_subscription_headers

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from ..settings import Settings
    from ..state import NodeRegistry


def build_router(
    settings: Settings,
    registry: NodeRegistry,
    session_factory: async_sessionmaker[AsyncSession],
) -> APIRouter:
    """Wire up the routes against concrete dependencies."""

    router = APIRouter()

    @router.get("/healthz")
    async def healthz() -> dict[str, object]:
        nodes = registry.all()
        return {
            "status": "ok",
            "nodes": [
                {
                    "name": n.name,
                    "alive": n.alive,
                    "last_latency_ms": n.last_latency_ms,
                    "last_error": n.last_error,
                }
                for n in nodes
            ],
        }

    @router.get("/api/sub/{user_id}")
    async def subscription(
        user_id: int,
        request: Request,
        token: str = "",
        user_agent: str = Header(default=""),
    ) -> Response:
        if not token or not verify_token(user_id, token, settings.backend.token_secret):
            raise HTTPException(status_code=403, detail="invalid token")

        async with session_factory() as session:
            existing = await session.get(User, user_id)
            if existing is None:
                user = User(
                    user_id=user_id,
                    expires_at=datetime.now(tz=UTC) + timedelta(days=30),
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
            else:
                user = existing

        alive_servers = registry.alive_servers(settings.servers)
        format_ = detect_format(user_agent)
        body = render(format_, alive_servers)

        headers = build_subscription_headers(
            used_bytes=user.bytes_used,
            total_bytes=user.bytes_total,
            expires_at=user.expires_at,
        )
        # Hint to caches/CDNs not to break per-UA branching.
        headers["Vary"] = "User-Agent"
        # Echo the requested host for debuggability.
        headers["X-Subscription-Source"] = str(request.url.path)

        return Response(content=body, headers=headers)

    return router


__all__ = ["build_router"]
