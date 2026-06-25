"""Event buffer, dispatch, and heartbeat for streaming visibility."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.kimi_stream import StreamEvent

if TYPE_CHECKING:
    from src.daemon import _TelegramLike

LOG = logging.getLogger("kimi_telegram_bridge")
EVENT_FLUSH_INTERVAL = 3.0
MAX_THINKING_CHARS_PER_TURN = 8_000
MAX_TOOL_CHARS_PER_TURN = 4_000
TYPING_REFRESH_S = 4.0
THINKING_NOTICE_SHORT = (250.0, "🤔 Still thinking… (over 4 min; timeout at 15 min)")
THINKING_NOTICE_LONG = (600.0, "🤔 Still thinking… (over 10 min; timeout at 15 min)")
PROGRESS_NOTICES = (THINKING_NOTICE_SHORT, THINKING_NOTICE_LONG)


@dataclass
class EventBuffer:
    """Aggregate streaming events to avoid flooding Telegram."""
    thinking_lines: list[str] = field(default_factory=list)
    tool_lines: list[str] = field(default_factory=list)
    last_flush: float = 0.0
    total_thinking_sent: int = 0
    total_tools_sent: int = 0

    def should_flush(self) -> bool:
        return (time.monotonic() - self.last_flush) >= EVENT_FLUSH_INTERVAL

    def add_thinking(self, text: str) -> None:
        self.thinking_lines.append(text)

    def add_tool(self, desc: str) -> None:
        self.tool_lines.append(desc)

    def build_thinking_message(self) -> str | None:
        if not self.thinking_lines:
            return None
        joined = "".join(self.thinking_lines)
        self.thinking_lines.clear()
        self.total_thinking_sent += len(joined)
        if self.total_thinking_sent > MAX_THINKING_CHARS_PER_TURN:
            return None
        if len(joined) > 3000:
            joined = joined[:3000] + "\n… (truncated)"
        return f"💭 *Thinking…*\n\n{joined}"

    def build_tool_message(self) -> str | None:
        if not self.tool_lines:
            return None
        deduped = list(dict.fromkeys(self.tool_lines))
        self.tool_lines.clear()
        self.total_tools_sent += len(deduped)
        if self.total_tools_sent > MAX_TOOL_CHARS_PER_TURN:
            return None
        return "\n".join(deduped[:10])

    def mark_flushed(self) -> None:
        self.last_flush = time.monotonic()


async def dispatch_events(
    tg: "_TelegramLike", chat_id: int,
    events: list[StreamEvent], buf: EventBuffer,
    thinking_enabled: bool = True,
) -> int:
    """Dispatch StreamEvents to Telegram. Returns messages sent."""
    for evt in events:
        if evt.kind == "thinking" and thinking_enabled:
            buf.add_thinking(evt.data)
        elif evt.kind == "tool_call":
            buf.add_tool(evt.data)

    if not buf.should_flush() and events:
        return 0

    sent = 0
    for msg in (buf.build_thinking_message(), buf.build_tool_message()):
        if msg:
            try:
                await tg.send_message(chat_id, msg)
                sent += 1
            except Exception:
                LOG.debug("dispatch send failed")

    buf.mark_flushed()
    return sent


async def heartbeat(
    tg: "_TelegramLike", chat_id: int, stop_event: asyncio.Event,
) -> None:
    """Typing indicator + progress notices. Cancelled when turn ends."""
    start = time.perf_counter()
    notices_sent: set[float] = set()
    try:
        while not stop_event.is_set():
            try:
                await tg.send_chat_action(chat_id, "typing")
            except Exception:
                LOG.debug("heartbeat sendChatAction failed")
            elapsed = time.perf_counter() - start
            for after_s, msg in PROGRESS_NOTICES:
                if elapsed >= after_s and after_s not in notices_sent:
                    notices_sent.add(after_s)
                    try:
                        await tg.send_message(chat_id, msg)
                    except Exception:
                        LOG.debug("heartbeat sendMessage failed")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=TYPING_REFRESH_S)
            except asyncio.TimeoutError:
                pass
    except asyncio.CancelledError:
        return
