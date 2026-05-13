"""aiogram handlers for the Xservis bot."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)

from ..auth import make_token
from ..models import User
from . import deeplinks

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from ..settings import Settings

log = logging.getLogger("xservis.bot")

WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://xservis.pro:9443/app/")


def _connect_keyboard(subscription_url: str) -> InlineKeyboardMarkup:
    """Build the inline keyboard with one button per supported client."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="V2RayTun (iOS / Android)",
                    url=deeplinks.v2raytun_import(subscription_url),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Hiddify",
                    url=deeplinks.hiddify_import(subscription_url),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="V2RayNG (Android)",
                    url=deeplinks.v2rayng_import(subscription_url),
                ),
                InlineKeyboardButton(
                    text="Streisand (iOS)",
                    url=deeplinks.streisand_import(subscription_url),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Скопировать ссылку",
                    callback_data="copy_sub",
                ),
            ],
        ]
    )


def _webapp_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Открыть приложение",
                    web_app=WebAppInfo(url=WEBAPP_URL),
                ),
            ],
        ]
    )


def build_subscription_url(user_id: int, settings: Settings) -> str:
    """Return the public subscription URL with a signed token."""

    token = make_token(user_id, settings.backend.token_secret)
    base = settings.backend.public_url.rstrip("/")
    path = settings.backend.subscription_path.rstrip("/")
    return f"{base}{path}/{user_id}?token={token}"


async def _upsert_user(
    session_factory: async_sessionmaker[AsyncSession],
    message: Message,
    start_payload: str | None,
) -> None:
    """Upsert the Telegram user into PostgreSQL on /start."""
    user = message.from_user
    if user is None:
        return

    ref_code: str | None = None
    referred_by: int | None = None
    if start_payload and start_payload.startswith("ref_"):
        ref_code = start_payload
        try:
            referred_by = int(start_payload.removeprefix("ref_"))
        except ValueError:
            referred_by = None

    # self-referral protection
    if referred_by == user.id:
        referred_by = None
        ref_code = None

    now = datetime.now(tz=UTC)
    async with session_factory() as session:
        existing = await session.get(User, user.id)
        if existing is None:
            db_user = User(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                language_code=user.language_code,
                is_premium=bool(user.is_premium),
                chat_id=message.chat.id,
                source="telegram_start",
                start_payload=start_payload,
                ref_code=ref_code,
                referred_by=referred_by,
                last_login_at=now,
                last_active_at=now,
            )
            session.add(db_user)

            # credit referrer — milestone-based rewards
            if referred_by is not None:
                referrer = await session.get(User, referred_by)
                if referrer is not None:
                    old_count = referrer.referral_count
                    referrer.referral_count = old_count + 1
                    new_count = referrer.referral_count
                    _MILESTONES = [
                        {"target": 1, "days": 1},
                        {"target": 3, "days": 3},
                        {"target": 5, "days": 7},
                    ]
                    for m in _MILESTONES:
                        if old_count < m["target"] <= new_count:
                            referrer.referral_bonus_days += m["days"]

            await session.commit()
            log.info("New user saved: id=%d username=%s", user.id, user.username)
        else:
            existing.username = user.username
            existing.first_name = user.first_name
            existing.last_name = user.last_name
            existing.language_code = user.language_code
            existing.is_premium = bool(user.is_premium)
            existing.chat_id = message.chat.id
            existing.last_login_at = now
            existing.last_active_at = now
            if start_payload and not existing.start_payload:
                existing.start_payload = start_payload
            await session.commit()
            log.info("User updated: id=%d", user.id)


def build_router(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> Router:
    """Wire bot handlers against the active settings."""

    router = Router(name="xservis")

    @router.message(CommandStart())
    async def on_start(message: Message, command: CommandObject) -> None:
        if message.from_user is None:
            return

        start_payload = command.args if command.args else None

        # Upsert user in DB
        if session_factory is not None:
            try:
                await _upsert_user(session_factory, message, start_payload)
            except Exception:
                log.exception("Failed to upsert user on /start")

        # Set WebApp menu button
        try:
            await message.bot.set_chat_menu_button(
                chat_id=message.chat.id,
                menu_button=MenuButtonWebApp(
                    text="Xservis",
                    web_app=WebAppInfo(url=WEBAPP_URL),
                ),
            )
        except Exception:
            log.debug("Could not set menu button", exc_info=True)

        text = (
            "Привет! Это <b>Xservis</b> — VPN, который не падает.\n\n"
            "Нажми кнопку ниже, чтобы открыть приложение. "
            "Сервер выберется автоматически — если один заблокируют, "
            "приложение само переключится на самый быстрый рабочий."
        )
        await message.answer(text, parse_mode="HTML", reply_markup=_webapp_keyboard())

    @router.message(Command("connect"))
    async def on_connect(message: Message) -> None:
        if message.from_user is None:
            return
        sub_url = build_subscription_url(message.from_user.id, settings)
        await message.answer("Выбери клиент:", reply_markup=_connect_keyboard(sub_url))

    @router.message(Command("status"))
    async def on_status(message: Message) -> None:
        if message.from_user is None:
            return
        sub_url = build_subscription_url(message.from_user.id, settings)
        await message.answer(
            f"Подписка:\n<code>{sub_url}</code>\n\nИмя профиля в клиенте: <b>Xservis</b>",
            parse_mode="HTML",
        )

    @router.callback_query(F.data == "copy_sub")
    async def on_copy_sub(call: object) -> None:
        from aiogram.types import CallbackQuery

        if not isinstance(call, CallbackQuery) or call.from_user is None:
            return
        sub_url = build_subscription_url(call.from_user.id, settings)
        await call.answer("Ссылка отправлена в чат")
        if call.message is not None:
            await call.message.answer(f"<code>{sub_url}</code>", parse_mode="HTML")

    return router


__all__ = ["build_router", "build_subscription_url"]
