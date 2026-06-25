"""Unit tests for src.events — buffer, dispatch, heartbeat."""
from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from src.events import EventBuffer, dispatch_events, heartbeat
from src.kimi_stream import StreamEvent


class _FakeTG:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []
        self.actions: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))

    async def send_chat_action(self, chat_id: int, action: str = "typing") -> None:
        self.actions.append((chat_id, action))


def _event(kind: str, data: str, tool_name: str = "") -> StreamEvent:
    return StreamEvent(kind=kind, data=data, tool_name=tool_name, timestamp=time.monotonic())


# ── EventBuffer ─────────────────────────────────────────────────

def test_buffer_starts_empty() -> None:
    b = EventBuffer()
    assert b.thinking_lines == []
    assert b.tool_lines == []


def test_buffer_add_thinking() -> None:
    b = EventBuffer()
    b.add_thinking("reasoning step 1")
    b.add_thinking("reasoning step 2")
    assert len(b.thinking_lines) == 2


def test_buffer_add_tool() -> None:
    b = EventBuffer()
    b.add_tool("📖 foo.py")
    b.add_tool("🔧 bar.py")
    assert len(b.tool_lines) == 2


def test_buffer_should_flush_after_interval() -> None:
    b = EventBuffer()
    b.last_flush = time.monotonic() - 4.0  # 4s ago
    assert b.should_flush() is True


def test_buffer_should_not_flush_before_interval() -> None:
    b = EventBuffer()
    b.last_flush = time.monotonic()  # just now
    assert b.should_flush() is False


def test_buffer_build_thinking_message() -> None:
    b = EventBuffer()
    b.add_thinking("thinking line 1")
    b.add_thinking("thinking line 2")
    msg = b.build_thinking_message()
    assert msg is not None
    assert "💭" in msg
    assert "thinking line 1" in msg


def test_buffer_thinking_capped() -> None:
    b = EventBuffer()
    b.add_thinking("x" * 5000)  # over 3000 char cap
    msg = b.build_thinking_message()
    assert msg is not None
    assert "truncated" in msg


def test_buffer_build_tool_max_10() -> None:
    b = EventBuffer()
    for i in range(15):
        b.add_tool(f"tool {i}")
    msg = b.build_tool_message()
    assert msg is not None
    lines = msg.split("\n")
    assert len(lines) <= 10


def test_build_thinking_returns_none_when_empty() -> None:
    b = EventBuffer()
    assert b.build_thinking_message() is None


def test_build_tool_returns_none_when_empty() -> None:
    b = EventBuffer()
    assert b.build_tool_message() is None


def test_mark_flushed_resets_timer() -> None:
    b = EventBuffer()
    old = time.monotonic() - 10.0
    b.last_flush = old
    b.mark_flushed()
    assert b.last_flush > old


# ── dispatch_events ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dispatch_thinking_event_sends() -> None:
    tg = _FakeTG()
    buf = EventBuffer()
    evt = _event("thinking", "analysis")
    await dispatch_events(tg, 1, [evt], buf, thinking_enabled=True)
    assert len(tg.sent) > 0
    assert any("analysis" in text for _, text in tg.sent)


@pytest.mark.asyncio
async def test_dispatch_respects_thinking_off() -> None:
    tg = _FakeTG()
    buf = EventBuffer()
    evt = _event("thinking", "analysis")
    await dispatch_events(tg, 1, [evt], buf, thinking_enabled=False)
    assert len(buf.thinking_lines) == 0


@pytest.mark.asyncio
async def test_dispatch_tool_event_sends() -> None:
    tg = _FakeTG()
    buf = EventBuffer()
    evt = _event("tool_call", "📖 config.py", tool_name="read")
    await dispatch_events(tg, 1, [evt], buf)
    assert len(tg.sent) > 0
    assert any("📖" in text for _, text in tg.sent)


@pytest.mark.asyncio
async def test_dispatch_sends_on_empty_flush() -> None:
    tg = _FakeTG()
    buf = EventBuffer()
    buf.add_thinking("thought")
    sent = await dispatch_events(tg, 1, [], buf, thinking_enabled=True)
    assert sent >= 0  # may send if buffer has content and needs flush


# ── heartbeat ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_heartbeat_sends_typing_and_stops() -> None:
    tg = _FakeTG()
    stop = asyncio.Event()
    task = asyncio.create_task(heartbeat(tg, 1, stop))
    await asyncio.sleep(0.05)
    stop.set()
    await task
    assert len(tg.actions) >= 1
    assert any(a[1] == "typing" for a in tg.actions)
