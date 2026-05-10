from __future__ import annotations

import os
from typing import TYPE_CHECKING

from xservis.settings import load_settings

if TYPE_CHECKING:
    from pathlib import Path


def test_load_settings_from_yaml(tmp_path: Path, monkeypatch: object) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        """
backend:
  port: 9999
  token_secret: abc
servers:
  - name: Xservis-X-1
    host: x1.example.com
    uuid: 11111111-1111-1111-1111-111111111111
    sni: www.cloudflare.com
    public_key: PK
    short_id: SI
""",
        encoding="utf-8",
    )
    settings = load_settings(cfg)
    assert settings.backend.port == 9999
    assert settings.backend.token_secret == "abc"
    assert len(settings.servers) == 1
    assert settings.servers[0].name == "Xservis-X-1"


def test_env_overrides_yaml(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        """
backend:
  token_secret: from-yaml
""",
        encoding="utf-8",
    )
    os.environ["XSERVIS_BACKEND__TOKEN_SECRET"] = "from-env"
    try:
        settings = load_settings(cfg)
        assert settings.backend.token_secret == "from-env"
    finally:
        del os.environ["XSERVIS_BACKEND__TOKEN_SECRET"]


def test_missing_yaml_uses_defaults(tmp_path: Path) -> None:
    settings = load_settings(tmp_path / "does-not-exist.yaml")
    assert settings.backend.port == 8080
    assert settings.servers == []
