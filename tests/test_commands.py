"""Unit tests for src.commands — bridge command handlers."""
from __future__ import annotations

import pytest

from src.commands import handle
from src.config import Config, KimiConfig, TelegramConfig
from src.state import State


def _cfg() -> Config:
    return Config(telegram=TelegramConfig(bot_token="t", allowed_user_ids=[42]),
                  kimi=KimiConfig(model="", agent="default"))

def _state() -> State:
    return State()

class _FakeTG:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))


class _FakeMsg:
    def __init__(self, text: str, chat_id: int = 42, user_id: int = 42) -> None:
        self.text = text
        self.chat_id = chat_id
        self.user_id = user_id


@pytest.mark.asyncio
async def test_start_command() -> None:
    tg = _FakeTG()
    msg = _FakeMsg("/start")
    ok = await handle(msg, tg, _state(), _cfg())
    assert ok is True
    assert len(tg.sent) == 1
    assert "Welcome" in tg.sent[0][1]


@pytest.mark.asyncio
async def test_help_command() -> None:
    tg = _FakeTG()
    ok = await handle(_FakeMsg("/help"), tg, _state(), _cfg())
    assert ok is True
    assert len(tg.sent) == 1
    assert "Commands" in tg.sent[0][1]


@pytest.mark.asyncio
async def test_info_shows_model() -> None:
    tg = _FakeTG()
    ok = await handle(_FakeMsg("/info"), tg, _state(), _cfg())
    assert ok is True
    assert "kimi-for-coding" in tg.sent[0][1]


@pytest.mark.asyncio
async def test_info_no_session() -> None:
    tg = _FakeTG()
    ok = await handle(_FakeMsg("/info"), tg, _state(), _cfg())
    assert ok is True
    assert "none" in tg.sent[0][1]


@pytest.mark.asyncio
async def test_thinking_on() -> None:
    tg = _FakeTG()
    s = _state()
    ok = await handle(_FakeMsg("/thinking on"), tg, s, _cfg())
    assert ok is True
    assert s.thinking_enabled.get(42) is True
    assert "ON" in tg.sent[0][1]


@pytest.mark.asyncio
async def test_thinking_off() -> None:
    tg = _FakeTG()
    s = _state()
    ok = await handle(_FakeMsg("/thinking off"), tg, s, _cfg())
    assert ok is True
    assert s.thinking_enabled.get(42) is False


@pytest.mark.asyncio
async def test_thinking_status() -> None:
    tg = _FakeTG()
    ok = await handle(_FakeMsg("/thinking"), tg, _state(), _cfg())
    assert ok is True
    assert "ON" in tg.sent[0][1]  # default


@pytest.mark.asyncio
async def test_model_set() -> None:
    tg = _FakeTG()
    s = _state()
    ok = await handle(_FakeMsg("/model gpt-5.5"), tg, s, _cfg())
    assert ok is True
    assert s.model_overrides.get(42) == "gpt-5.5"


@pytest.mark.asyncio
async def test_model_get() -> None:
    tg = _FakeTG()
    s = _state()
    s.model_overrides[42] = "opus-4-6"
    ok = await handle(_FakeMsg("/model"), tg, s, _cfg())
    assert ok is True
    assert "opus-4-6" in tg.sent[0][1]


@pytest.mark.asyncio
async def test_reset_clears_session() -> None:
    tg = _FakeTG()
    s = _state()
    s.chats[42] = "abc123def456abc123def456abc12345"
    ok = await handle(_FakeMsg("/reset"), tg, s, _cfg())
    assert ok is True
    assert 42 not in s.chats


@pytest.mark.asyncio
async def test_reset_no_session() -> None:
    tg = _FakeTG()
    ok = await handle(_FakeMsg("/reset"), tg, _state(), _cfg())
    assert ok is True
    assert "No active" in tg.sent[0][1]


@pytest.mark.asyncio
async def test_unknown_returns_false() -> None:
    tg = _FakeTG()
    ok = await handle(_FakeMsg("hello world"), tg, _state(), _cfg())
    assert ok is False
    assert len(tg.sent) == 0
