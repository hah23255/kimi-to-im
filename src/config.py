"""Loader and validator for config.json."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    """config.json missing, malformed, or invalid."""


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


def _load_raw(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"config not found at {path}")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON in {path}: {exc}") from exc


def _parse_telegram(raw: dict) -> TelegramConfig:
    tg = raw.get("telegram") or {}
    token = tg.get("bot_token") or ""
    if not isinstance(token, str) or not token:
        raise ConfigError("telegram.bot_token must be a non-empty string")
    users = tg.get("allowed_user_ids") or []
    if not isinstance(users, list) or not users:
        raise ConfigError("telegram.allowed_user_ids must be non-empty")
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in users):
        raise ConfigError("allowed_user_ids entries must be integers")
    chats = tg.get("allowed_chat_ids") or []
    if not isinstance(chats, list) or not all(
        isinstance(x, int) and not isinstance(x, bool) for x in chats):
        raise ConfigError("allowed_chat_ids must be a list of integers")
    return TelegramConfig(bot_token=token, allowed_user_ids=list(users),
                          allowed_chat_ids=list(chats))


def _parse_kimi(raw: dict) -> KimiConfig:
    k = raw.get("kimi") or {}
    return KimiConfig(
        default_workdir=str(k.get("default_workdir") or ""),
        model=str(k.get("model") or ""),
        agent=str(k.get("agent") or "default"))


def load_config(path: Path) -> Config:
    raw = _load_raw(path)
    return Config(telegram=_parse_telegram(raw), kimi=_parse_kimi(raw))
