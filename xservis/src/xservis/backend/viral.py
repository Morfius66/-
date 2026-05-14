"""Viral features API routes (Goal #5).

Five features added as backend hooks, hidden or placed inside
secondary tabs (Profile / Stats), not on the main screen.

1. 7-day Referral Sprint — progress 0/1/3/5 invites with milestones
2. Share link with auto-substitution — generates start=ref_<user_id>
3. Instant config after payment/trial — returns Hiddify/V2RayTun deep-links
4. Aima Fix My VPN — diagnostic collection + 3-step resolution
5. Speed Badge / Streak — daily status badge in Stats tab
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..models import DiagnosticReport, User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from ..settings import Settings


# ── Request / Response schemas ───────────────────────────────────

class DiagnosticInput(BaseModel):
    client_type: str | None = None
    platform: str | None = None
    subscription_status: str | None = None
    last_error: str | None = None


class DiagnosticResponse(BaseModel):
    steps: list[str]
    report_id: int


class ReferralSprintResponse(BaseModel):
    invited: int
    milestones: list[dict[str, object]]
    bonus_days_earned: int


class ShareLinkResponse(BaseModel):
    link: str
    ref_code: str


class SpeedBadgeResponse(BaseModel):
    streak_days: int
    status: str
    active_until: str | None
    badge: str


class InstantConfigResponse(BaseModel):
    hiddify_url: str
    v2raytun_url: str
    copy_url: str


# ── Diagnosis logic ──────────────────────────────────────────────

_FIX_STEPS: dict[str, list[str]] = {
    "connection_timeout": [
        "1. Переключите сервер: Настройки → Выбор сервера → другой регион",
        "2. Смените SNI: попробуйте www.google.com или www.microsoft.com",
        "3. Если не помогло — напишите в @xservis_support с описанием провайдера",
    ],
    "subscription_expired": [
        "1. Откройте приложение и проверьте статус подписки",
        "2. Если истекла — продлите через оплату Stars/Crypto/Карта",
        "3. После оплаты нажмите «Обновить подписку» в VPN-клиенте",
    ],
    "default": [
        "1. Перезапустите VPN-клиент (выключите и включите VPN)",
        "2. Обновите подписку: Настройки → Подписки → Обновить",
        "3. Если не помогло — удалите профиль и импортируйте заново через бота",
    ],
}

MILESTONES = [
    {"target": 1, "reward": "1 день бонуса", "days": 1},
    {"target": 3, "reward": "3 дня бонуса", "days": 3},
    {"target": 5, "reward": "7 дней бонуса", "days": 7},
]

BADGES = {
    0: "🆕 Новичок",
    3: "⚡ Активный",
    7: "🔥 Неделя",
    14: "💎 Две недели",
    30: "🏆 Месяц",
}


def _diagnose(report: DiagnosticInput) -> list[str]:
    if report.last_error and "timeout" in report.last_error.lower():
        return _FIX_STEPS["connection_timeout"]
    if report.subscription_status and "expired" in report.subscription_status.lower():
        return _FIX_STEPS["subscription_expired"]
    return _FIX_STEPS["default"]


def _badge_for_streak(days: int) -> str:
    result = BADGES[0]
    for threshold, badge in sorted(BADGES.items()):
        if days >= threshold:
            result = badge
    return result


# ── Router ───────────────────────────────────────────────────────

def build_viral_router(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> APIRouter:
    router = APIRouter(prefix="/api/viral", tags=["viral"])

    async def _get_user(request: Request) -> User:
        user_id = request.state.user_id  # set by initData middleware
        async with session_factory() as session:
            user = await session.get(User, user_id)
            if user is None:
                raise HTTPException(status_code=404, detail="user not found")
            return user

    # 1. Referral Sprint
    @router.get("/referral-sprint", response_model=ReferralSprintResponse)
    async def referral_sprint(request: Request) -> ReferralSprintResponse:
        user = await _get_user(request)
        milestone_status = []
        for m in MILESTONES:
            milestone_status.append({
                "target": m["target"],
                "reward": m["reward"],
                "achieved": user.referral_count >= m["target"],
            })
        return ReferralSprintResponse(
            invited=user.referral_count,
            milestones=milestone_status,
            bonus_days_earned=user.referral_bonus_days,
        )

    # 2. Share link
    @router.get("/share-link", response_model=ShareLinkResponse)
    async def share_link(request: Request) -> ShareLinkResponse:
        user = await _get_user(request)
        ref_code = f"ref_{user.user_id}"
        link = f"https://t.me/XsradminBot?start={ref_code}"
        return ShareLinkResponse(link=link, ref_code=ref_code)

    # 3. Instant config after payment
    @router.get("/instant-config", response_model=InstantConfigResponse)
    async def instant_config(request: Request) -> InstantConfigResponse:
        from ..auth import make_token

        user = await _get_user(request)
        token = make_token(user.user_id, settings.backend.token_secret)
        base = settings.backend.public_url.rstrip("/")
        path = settings.backend.subscription_path.rstrip("/")
        sub_url = f"{base}{path}/{user.user_id}?token={token}"

        return InstantConfigResponse(
            hiddify_url=f"hiddify://import/{sub_url}",
            v2raytun_url=f"v2raytun://import/{sub_url}",
            copy_url=sub_url,
        )

    # 4. Aima Fix My VPN
    @router.post("/diagnose", response_model=DiagnosticResponse)
    async def diagnose(request: Request, data: DiagnosticInput) -> DiagnosticResponse:
        user = await _get_user(request)
        steps = _diagnose(data)

        async with session_factory() as session:
            report = DiagnosticReport(
                user_id=user.user_id,
                client_type=data.client_type,
                platform=data.platform,
                subscription_status=data.subscription_status,
                last_error=data.last_error,
                diagnosis="\n".join(steps),
            )
            session.add(report)
            await session.commit()
            await session.refresh(report)

        return DiagnosticResponse(steps=steps, report_id=report.id)

    # 5. Speed Badge / Streak
    @router.get("/speed-badge", response_model=SpeedBadgeResponse)
    async def speed_badge(request: Request) -> SpeedBadgeResponse:
        user = await _get_user(request)
        badge = _badge_for_streak(user.streak_days)
        active_until = user.expires_at.isoformat() if user.expires_at else None
        status = "active" if user.expires_at and user.expires_at > datetime.now(tz=UTC) else "expired"
        return SpeedBadgeResponse(
            streak_days=user.streak_days,
            status=status,
            active_until=active_until,
            badge=badge,
        )

    return router


__all__ = ["build_viral_router"]
