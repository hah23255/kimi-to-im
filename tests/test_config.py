"""Tests for src.config — load_config and validation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.config import (
    Config,
    ConfigError,
    KimiConfig,
    TelegramConfig,
    load_config,
)


def test_load_valid_config_returns_typed_dataclass(config_file: Path) -> None:
    cfg = load_config(config_file)
    assert isinstance(cfg, Config)
    assert isinstance(cfg.telegram, TelegramConfig)
    assert isinstance(cfg.kimi, KimiConfig)
    assert cfg.telegram.bot_token == "1234:abcXYZ"
    assert cfg.telegram.allowed_user_ids == [99999999]
    assert cfg.telegram.allowed_chat_ids == []
    assert cfg.kimi.default_workdir == "/tmp"
    assert cfg.kimi.model == ""
    assert cfg.kimi.agent == "default"


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.json")


def test_invalid_json_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("{ not valid json")
    with pytest.raises(ConfigError, match="invalid JSON"):
        load_config(p)


def test_missing_bot_token_raises(tmp_path: Path, sample_config_dict: dict) -> None:
    sample_config_dict["telegram"]["bot_token"] = ""
    p = tmp_path / "config.json"
    p.write_text(json.dumps(sample_config_dict))
    with pytest.raises(ConfigError, match="telegram.bot_token"):
        load_config(p)


def test_empty_allowed_user_ids_raises(tmp_path: Path, sample_config_dict: dict) -> None:
    sample_config_dict["telegram"]["allowed_user_ids"] = []
    p = tmp_path / "config.json"
    p.write_text(json.dumps(sample_config_dict))
    with pytest.raises(ConfigError, match="allowed_user_ids"):
        load_config(p)


def test_non_int_allowed_user_id_raises(tmp_path: Path, sample_config_dict: dict) -> None:
    sample_config_dict["telegram"]["allowed_user_ids"] = ["not-an-int"]
    p = tmp_path / "config.json"
    p.write_text(json.dumps(sample_config_dict))
    with pytest.raises(ConfigError, match="must be integers"):
        load_config(p)


def test_kimi_defaults_applied_when_missing(tmp_path: Path, sample_config_dict: dict) -> None:
    del sample_config_dict["kimi"]
    p = tmp_path / "config.json"
    p.write_text(json.dumps(sample_config_dict))
    cfg = load_config(p)
    assert cfg.kimi.default_workdir == ""
    assert cfg.kimi.model == ""
    assert cfg.kimi.agent == "default"
