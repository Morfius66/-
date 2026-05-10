"""ORM models and shared dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for ORM models."""


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


class User(Base):
    """A subscriber to the Xservis service.

    ``user_id`` is the Telegram user id and the path component used in
    the subscription URL.
    """

    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    language_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    start_payload: Mapped[str | None] = mapped_column(String(256), nullable=True)
    ref_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    referred_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    referral_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    referral_bonus_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    streak_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bytes_used: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    bytes_total: Mapped[int] = mapped_column(BigInteger, default=100 * 1024**3, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    last_login_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class DiagnosticReport(Base):
    """User-submitted VPN diagnostic report for Aima Fix My VPN."""

    __tablename__ = "diagnostic_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    client_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subscription_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    diagnosis: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


@dataclass(slots=True)
class NodeHealth:
    """Mutable runtime health state for one configured server.

    The watchdog updates these fields; the subscription endpoint reads them
    when deciding which nodes to expose to the client.
    """

    name: str
    alive: bool = True
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_checked_at: datetime | None = None
    last_latency_ms: float | None = None
    last_error: str | None = None
    history: list[bool] = field(default_factory=list)

    def record_success(self, latency_ms: float, recovery_threshold: int) -> bool:
        """Record a successful check. Returns True if the node transitioned to alive."""

        previously_alive = self.alive
        self.consecutive_failures = 0
        self.consecutive_successes += 1
        self.last_checked_at = _utcnow()
        self.last_latency_ms = latency_ms
        self.last_error = None
        self.history.append(True)
        del self.history[:-50]
        if not previously_alive and self.consecutive_successes >= recovery_threshold:
            self.alive = True
        return self.alive and not previously_alive

    def record_failure(self, error: str, failure_threshold: int) -> bool:
        """Record a failed check. Returns True if the node transitioned to blocked."""

        previously_alive = self.alive
        self.consecutive_successes = 0
        self.consecutive_failures += 1
        self.last_checked_at = _utcnow()
        self.last_error = error
        self.history.append(False)
        del self.history[:-50]
        if previously_alive and self.consecutive_failures >= failure_threshold:
            self.alive = False
        return previously_alive and not self.alive


__all__ = ["Base", "DiagnosticReport", "NodeHealth", "User"]
