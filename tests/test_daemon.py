"""Tests for src.daemon — orchestration with all I/O mocked."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from src.config import Config, KimiConfig, TelegramConfig
from src.daemon import run
from src.kimi_runner import KimiResult
from src.state import load_state


pytestmark = pytest.mark.asyncio


@dataclass
class _FakeTelegram:
    updates_to_serve: list[list[dict[str, Any]]]
    sent_messages: list[tuple[int, str]]
    chat_actions: list[tuple[int, str]]

    async def __aenter__(self) -> "_FakeTelegram":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def get_updates(self, offset: int, timeout: int = 30) -> list[dict[str, Any]]:
        if self.updates_to_serve:
            return self.updates_to_serve.pop(0)
        return []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent_messages.append((chat_id, text))

    async def send_chat_action(self, chat_id: int, action: str = "typing") -> None:
        self.chat_actions.append((chat_id, action))


def _msg(text: str, *, update_id: int, user_id: int = 42, chat_id: int = 10) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": 0,
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "T"},
            "text": text,
        },
    }


def _cfg() -> Config:
    return Config(
        telegram=TelegramConfig(
            bot_token="TOKEN",
            allowed_user_ids=[42],
            allowed_chat_ids=[],
        ),
        kimi=KimiConfig(default_workdir="/tmp", model="", agent="default"),
    )


async def _run_kimi_stub(
    prompt: str,
    *,
    session_id: str,
    workdir: str,
    model: str,
    agent: str,
    kimi_path: str,
    timeout: float | None = None,
) -> KimiResult:
    return KimiResult(text=f"echo:{prompt}@{session_id}", exit_code=0, stderr="")


async def test_run_replies_to_authorized_message(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    tg = _FakeTelegram(
        updates_to_serve=[[_msg("hello", update_id=100)]],
        sent_messages=[],
        chat_actions=[],
    )
    stop = asyncio.Event()
    asyncio.get_running_loop().call_later(0.2, stop.set)

    await run(
        cfg=_cfg(),
        state_path=state_path,
        tg=tg,
        run_kimi_func=_run_kimi_stub,
        kimi_path="/usr/bin/true",
        stop_event=stop,
    )

    assert tg.chat_actions and tg.chat_actions[0] == (10, "typing")
    assert len(tg.sent_messages) == 1
    chat_id, text = tg.sent_messages[0]
    assert chat_id == 10
    assert text.startswith("echo:hello@")

    persisted = load_state(state_path)
    assert persisted.last_update_id == 100
    assert 10 in persisted.chats


async def test_run_drops_unauthorized_message(tmp_path: Path) -> None:
    tg = _FakeTelegram(
        updates_to_serve=[[_msg("hi", update_id=200, user_id=999)]],
        sent_messages=[],
        chat_actions=[],
    )
    stop = asyncio.Event()
    asyncio.get_running_loop().call_later(0.2, stop.set)

    await run(
        cfg=_cfg(),
        state_path=tmp_path / "state.json",
        tg=tg,
        run_kimi_func=_run_kimi_stub,
        kimi_path="/usr/bin/true",
        stop_event=stop,
    )
    assert tg.sent_messages == []
    assert tg.chat_actions == []


async def test_run_replies_with_error_when_kimi_fails(tmp_path: Path) -> None:
    async def failing_kimi(prompt: str, **kwargs: Any) -> KimiResult:
        return KimiResult(text="", exit_code=2, stderr="auth expired")

    tg = _FakeTelegram(
        updates_to_serve=[[_msg("hi", update_id=300)]],
        sent_messages=[],
        chat_actions=[],
    )
    stop = asyncio.Event()
    asyncio.get_running_loop().call_later(0.2, stop.set)

    await run(
        cfg=_cfg(),
        state_path=tmp_path / "state.json",
        tg=tg,
        run_kimi_func=failing_kimi,
        kimi_path="/usr/bin/true",
        stop_event=stop,
    )
    assert len(tg.sent_messages) == 1
    _, text = tg.sent_messages[0]
    assert "kimi error" in text and "auth expired" in text


async def test_run_reuses_session_id_across_messages_in_same_chat(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    seen_sessions: list[str] = []

    async def recording_kimi(prompt: str, **kwargs: Any) -> KimiResult:
        seen_sessions.append(kwargs["session_id"])
        return KimiResult(text="ok", exit_code=0, stderr="")

    tg = _FakeTelegram(
        updates_to_serve=[
            [_msg("first", update_id=400)],
            [_msg("second", update_id=401)],
        ],
        sent_messages=[],
        chat_actions=[],
    )
    stop = asyncio.Event()
    asyncio.get_running_loop().call_later(0.4, stop.set)

    await run(
        cfg=_cfg(),
        state_path=state_path,
        tg=tg,
        run_kimi_func=recording_kimi,
        kimi_path="/usr/bin/true",
        stop_event=stop,
    )
    assert len(seen_sessions) == 2
    assert seen_sessions[0] == seen_sessions[1]


async def test_run_logs_one_line_per_turn(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Each completed kimi turn should produce a single INFO log entry."""
    import logging

    tg = _FakeTelegram(
        updates_to_serve=[[_msg("ping", update_id=500)]],
        sent_messages=[],
        chat_actions=[],
    )
    stop = asyncio.Event()
    asyncio.get_running_loop().call_later(0.2, stop.set)

    with caplog.at_level(logging.INFO, logger="kimi_telegram_bridge"):
        await run(
            cfg=_cfg(),
            state_path=tmp_path / "state.json",
            tg=tg,
            run_kimi_func=_run_kimi_stub,
            kimi_path="/usr/bin/true",
            stop_event=stop,
        )

    turn_lines = [r for r in caplog.records if r.message.startswith("turn ")]
    assert len(turn_lines) == 1
    msg = turn_lines[0].message
    assert "chat=10" in msg
    assert "exit=0" in msg
    assert "ms=" in msg
    assert "reply_len=" in msg
    assert "session=" in msg
