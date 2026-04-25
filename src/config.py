"""Loader and validator for ~/.kimi/plugins/telegram-bridge/config.json."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    """Raised when config.json is missing, malformed, or fails validation."""


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    allowed_user_ids: list[int]
    allowed_chat_ids: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class KimiConfig:
    default_workdir: str = ""
    model: str = ""
    agent: str = "default"


@dataclass(frozen=True)
class Config:
    telegram: TelegramConfig
    kimi: KimiConfig


def load_config(path: Path) -> Config:
    if not path.exists():
        raise ConfigError(f"config not found at {path}")

    try:
        raw: dict[str, Any] = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON in {path}: {exc}") from exc

    tg_raw = raw.get("telegram") or {}
    bot_token = tg_raw.get("bot_token") or ""
    if not isinstance(bot_token, str) or not bot_token:
        raise ConfigError("telegram.bot_token must be a non-empty string")

    allowed_user_ids = tg_raw.get("allowed_user_ids") or []
    if not isinstance(allowed_user_ids, list) or not allowed_user_ids:
        raise ConfigError(
            "telegram.allowed_user_ids must be a non-empty list (default-deny)"
        )
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in allowed_user_ids):
        raise ConfigError("telegram.allowed_user_ids entries must be integers")

    allowed_chat_ids = tg_raw.get("allowed_chat_ids") or []
    if not isinstance(allowed_chat_ids, list) or not all(
        isinstance(x, int) and not isinstance(x, bool) for x in allowed_chat_ids
    ):
        raise ConfigError("telegram.allowed_chat_ids must be a list of integers")

    kimi_raw = raw.get("kimi") or {}
    return Config(
        telegram=TelegramConfig(
            bot_token=bot_token,
            allowed_user_ids=list(allowed_user_ids),
            allowed_chat_ids=list(allowed_chat_ids),
        ),
        kimi=KimiConfig(
            default_workdir=str(kimi_raw.get("default_workdir") or ""),
            model=str(kimi_raw.get("model") or ""),
            agent=str(kimi_raw.get("agent") or "default"),
        ),
    )
