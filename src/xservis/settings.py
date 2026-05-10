"""Configuration loading.

Settings come from (in order of precedence):

  1. Environment variables prefixed with ``XSERVIS_`` using ``__`` as nesting
     (e.g. ``XSERVIS_BACKEND__PORT``).
  2. A YAML file at ``$XSERVIS_CONFIG_FILE`` (default: ``./config.yaml``).
  3. Defaults defined on the Pydantic models below.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)


class BackendConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080
    public_url: str = "https://xservis.pro"
    subscription_path: str = "/api/sub"
    token_secret: str = "change-me-please"


class DatabaseConfig(BaseModel):
    url: str = "sqlite+aiosqlite:///./xservis.db"


class BotConfig(BaseModel):
    token: str = ""
    admin_chat_id: int = 0


class WatchdogConfig(BaseModel):
    enabled: bool = True
    interval_seconds: float = 30.0
    tcp_timeout: float = 3.0
    failure_threshold: int = 3
    recovery_threshold: int = 2


class ServerConfig(BaseModel):
    """A single VLESS+Reality node served from the subscription."""

    name: str
    host: str
    port: int = 443
    uuid: str
    sni: str
    public_key: str
    short_id: str
    fingerprint: str = "chrome"
    flow: str = "xtls-rprx-vision"


class Settings(BaseSettings):
    backend: BackendConfig = Field(default_factory=BackendConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    bot: BotConfig = Field(default_factory=BotConfig)
    watchdog: WatchdogConfig = Field(default_factory=WatchdogConfig)
    servers: list[ServerConfig] = Field(default_factory=list)

    model_config = SettingsConfigDict(
        env_prefix="XSERVIS_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        yaml_path = Path(os.environ.get("XSERVIS_CONFIG_FILE", "config.yaml"))
        # Highest-priority source comes first; env overrides yaml overrides defaults.
        sources: tuple[PydanticBaseSettingsSource, ...] = (
            init_settings,
            env_settings,
            dotenv_settings,
        )
        if yaml_path.exists():
            sources = (
                *sources,
                YamlConfigSettingsSource(settings_cls, yaml_file=yaml_path),
            )
        sources = (*sources, file_secret_settings)
        return sources


def load_settings(path: str | os.PathLike[str] | None = None) -> Settings:
    """Load settings, optionally pointing at a specific YAML file."""

    if path is not None:
        os.environ["XSERVIS_CONFIG_FILE"] = str(path)
    return Settings()
