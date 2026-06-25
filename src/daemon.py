"""Long-running daemon: poll Telegram, route through kimi, reply."""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol

from src.config import Config, load_config
from src.kimi_runner import (
    KimiResult,
    StreamEvent,
    StreamResult,
    run_kimi,
    run_kimi_stream,
)
from src.state import State, load_state, save_state
from src.telegram import (
    InboundMessage,
    TelegramClient,
    is_authorized,
    parse_update,
)

LOG = logging.getLogger("kimi_telegram_bridge")

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"
DEFAULT_STATE_PATH = Path.home() / ".kimi" / "bridge" / "state.json"
DEFAULT_KIMI_BIN = "kimi"
LONG_POLL_TIMEOUT = 30
KIMI_TIMEOUT_S = 900.0  # bound a hung kimi process; surfaces as exit_code=124
TYPING_REFRESH_S = 4.0  # Telegram typing indicator lasts ~5s; refresh below that
EVENT_FLUSH_INTERVAL = 3.0  # seconds between event batch sends
PROGRESS_NOTICES = (  # (after_seconds, message) — sent during long turns
    (250.0, "🤔 Still thinking… (over 4 min so far; timeout at 15 min)"),
    (600.0, "🤔 Still thinking… (over 10 min so far; timeout at 15 min)"),
)
# Caps to prevent flooding a Telegram chat
MAX_THINKING_CHARS_PER_TURN = 8_000
MAX_TOOL_CHARS_PER_TURN = 4_000


class _TelegramLike(Protocol):
    async def __aenter__(self) -> "_TelegramLike": ...
    async def __aexit__(self, *exc: object) -> None: ...
    async def get_updates(self, offset: int, timeout: int = 30) -> list[dict[str, Any]]: ...
    async def send_message(self, chat_id: int, text: str) -> None: ...
    async def send_chat_action(self, chat_id: int, action: str = "typing") -> None: ...


RunKimiFunc = Callable[..., Awaitable[KimiResult]]


# ── Event buffer (T1.2) ──────────────────────────────────────────

@dataclass
class _EventBuffer:
    """Aggregate streaming events to avoid flooding Telegram.

    Thinking blocks are accumulated into one message per flush interval.
    Tool calls are batched and sent together.  Text events passthrough
    immediately (they're the actual reply content).
    """
    thinking_lines: list[str] = field(default_factory=list)
    tool_lines: list[str] = field(default_factory=list)
    last_flush: float = 0.0
    total_thinking_sent: int = 0
    total_tools_sent: int = 0

    def should_flush(self) -> bool:
        return (time.monotonic() - self.last_flush) >= EVENT_FLUSH_INTERVAL

    def add_thinking(self, text: str) -> None:
        self.thinking_lines.append(text)

    def add_tool(self, description: str) -> None:
        self.tool_lines.append(description)

    def build_thinking_message(self) -> str | None:
        if not self.thinking_lines:
            return None
        joined = "".join(self.thinking_lines)
        self.thinking_lines.clear()
        self.total_thinking_sent += len(joined)
        if self.total_thinking_sent > MAX_THINKING_CHARS_PER_TURN:
            return None  # already sent enough
        # Truncate if too long
        if len(joined) > 3000:
            joined = joined[:3000] + "\n… (truncated)"
        return f"💭 *Thinking…*\n\n{joined}"

    def build_tool_message(self) -> str | None:
        if not self.tool_lines:
            return None
        deduped = list(dict.fromkeys(self.tool_lines))  # preserve order, drop dups
        self.tool_lines.clear()
        self.total_tools_sent += len(deduped)
        if self.total_tools_sent > MAX_TOOL_CHARS_PER_TURN:
            return None
        return "\n".join(deduped[:10])  # max 10 tools per message

    def mark_flushed(self) -> None:
        self.last_flush = time.monotonic()


# ── Heartbeat (typing indicator + progress notices) ─────────────

async def _heartbeat(
    tg: "_TelegramLike",
    chat_id: int,
    stop_event: asyncio.Event,
) -> None:
    """Keep the Telegram 'typing' indicator alive and post progress notices.

    Runs concurrently with the kimi subprocess. Cancelled when the turn
    completes or fails.
    """
    start = time.perf_counter()
    notices_sent: set[float] = set()
    try:
        while not stop_event.is_set():
            try:
                await tg.send_chat_action(chat_id, "typing")
            except Exception as err:
                LOG.debug("heartbeat sendChatAction failed: %s", err)

            elapsed = time.perf_counter() - start
            for after_s, msg in PROGRESS_NOTICES:
                if elapsed >= after_s and after_s not in notices_sent:
                    notices_sent.add(after_s)
                    try:
                        await tg.send_message(chat_id, msg)
                    except Exception as err:
                        LOG.debug("heartbeat sendMessage failed: %s", err)

            try:
                await asyncio.wait_for(
                    stop_event.wait(), timeout=TYPING_REFRESH_S
                )
            except asyncio.TimeoutError:
                pass
    except asyncio.CancelledError:
        return


# ── Streaming event dispatcher (T1.3, T1.4) ─────────────────────

async def _dispatch_stream_events(
    tg: "_TelegramLike",
    chat_id: int,
    events: list[StreamEvent],
    buffer: _EventBuffer,
) -> int:
    """Dispatch StreamEvents to Telegram, respecting flush intervals and caps.

    Returns the number of messages sent.
    """
    sent = 0
    for evt in events:
        if evt.kind == "thinking":
            buffer.add_thinking(evt.data)
        elif evt.kind == "tool_call":
            buffer.add_tool(evt.data)

    # Flush if interval elapsed
    if buffer.should_flush() or len(events) == 0:  # 0 = explicit flush
        thinking_msg = buffer.build_thinking_message()
        if thinking_msg:
            try:
                await tg.send_message(chat_id, thinking_msg)
                sent += 1
            except Exception as err:
                LOG.debug("dispatch thinking failed: %s", err)

        tool_msg = buffer.build_tool_message()
        if tool_msg:
            try:
                await tg.send_message(chat_id, tool_msg)
                sent += 1
            except Exception as err:
                LOG.debug("dispatch tools failed: %s", err)

        buffer.mark_flushed()

    return sent


async def _run_streaming_turn(
    tg: "_TelegramLike",
    chat_id: int,
    msg: InboundMessage,
    sid: str,
    cfg: Config,
    kimi_path: str,
) -> tuple[StreamResult, float]:
    """Execute one turn using the streaming kimi executor with real-time event dispatch.

    Runs the kimi subprocess, reading StreamEvents as they arrive, batching
    thinking and tool events to Telegram every EVENT_FLUSH_INTERVAL seconds.

    Returns (result, elapsed_ms).
    """
    buffer = _EventBuffer()
    heartbeat_stop = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        _heartbeat(tg, chat_id, heartbeat_stop)
    )

    turn_start = time.perf_counter()
    try:
        result = await run_kimi_stream(
            prompt=msg.text,
            session_id=sid,
            workdir=cfg.kimi.default_workdir,
            model=cfg.kimi.model,
            agent=cfg.kimi.agent,
            kimi_path=kimi_path,
            timeout=KIMI_TIMEOUT_S,
        )
        # Dispatch all accumulated events
        await _dispatch_stream_events(tg, chat_id, result.events, buffer)
        # Final flush
        await _dispatch_stream_events(tg, chat_id, [], buffer)
    finally:
        heartbeat_stop.set()
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except (asyncio.CancelledError, Exception):
            pass

    elapsed_ms = int((time.perf_counter() - turn_start) * 1000)
    LOG.info(
        "turn chat=%d session=%s exit=%d ms=%d reply_len=%d thinking=%d tools=%d",
        chat_id,
        sid[:8],
        result.exit_code,
        elapsed_ms,
        len(result.text or ""),
        result.total_thinking_chars,
        result.total_tool_calls,
    )
    return result, elapsed_ms


# ── Bridge commands ──────────────────────────────────────────────

def _session_for(state: State, chat_id: int) -> str:
    sid = state.chats.get(chat_id)
    if sid:
        return sid
    sid = uuid.uuid4().hex
    state.chats[chat_id] = sid
    return sid


async def _handle_bridge_command(
    msg: InboundMessage, tg: "_TelegramLike"
) -> bool:
    """Handle built-in bridge commands. Returns True if a command was handled."""
    stripped = msg.text.strip()
    if stripped == "/start":
        await tg.send_message(
            msg.chat_id,
            "👋 Welcome! I'm your Kimi bridge bot.\n\n"
            "Send me any message and I'll forward it to Kimi. "
            "Your conversation history is preserved per chat.\n\n"
            "Commands:\n"
            "/start – this message\n"
            "/help – usage help\n"
            "/reset – clear context (Kimi CLI native)\n"
            "/clear – clear context (Kimi CLI native)",
        )
        return True
    if stripped == "/help":
        await tg.send_message(
            msg.chat_id,
            "📖 Kimi Bridge Help\n\n"
            "Send any text message to chat with Kimi. Replies may take a few "
            "seconds up to several minutes depending on the task.\n\n"
            "Native Kimi slash commands also work (e.g. /clear, /reset).\n\n"
            "Tips:\n"
            "• Session history is preserved automatically\n"
            "• Long replies are split into multiple messages\n"
            "• Timeout is 15 minutes per turn",
        )
        return True
    return False


# ── Main loop ────────────────────────────────────────────────────

async def run(
    *,
    cfg: Config,
    state_path: Path,
    tg: _TelegramLike,
    run_kimi_func: RunKimiFunc,
    kimi_path: str,
    stop_event: asyncio.Event,
    use_streaming: bool = False,
) -> None:
    """Main loop. Returns when stop_event is set.

    When ``use_streaming`` is True (default), turns are executed via
    ``run_kimi_stream()`` for real-time event visibility.  When False
    (or for test injectors), the legacy ``run_kimi_func`` path is used.
    """
    state = load_state(state_path)
    async with tg:
        while not stop_event.is_set():
            try:
                updates = await asyncio.wait_for(
                    tg.get_updates(
                        offset=state.last_update_id + 1, timeout=LONG_POLL_TIMEOUT
                    ),
                    timeout=LONG_POLL_TIMEOUT + 5,
                )
            except asyncio.TimeoutError:
                continue
            except Exception as err:
                LOG.warning("getUpdates failed: %s", err)
                await asyncio.sleep(2)
                continue

            for upd in updates:
                state.last_update_id = max(
                    state.last_update_id, int(upd.get("update_id", 0))
                )
                msg: InboundMessage | None = parse_update(upd)
                if msg is None:
                    continue
                if not is_authorized(msg, cfg.telegram):
                    LOG.info(
                        "dropping unauthorized message from user_id=%s",
                        msg.user_id,
                    )
                    continue

                # ── bridge-level commands ──
                if await _handle_bridge_command(msg, tg):
                    continue

                # ── kimi turn ──
                try:
                    await tg.send_chat_action(msg.chat_id, "typing")
                except Exception as err:
                    LOG.debug("sendChatAction failed (non-fatal): %s", err)

                sid = _session_for(state, msg.chat_id)
                save_state(state_path, state)

                if use_streaming:
                    result, elapsed_ms = await _run_streaming_turn(
                        tg, msg.chat_id, msg, sid, cfg, kimi_path
                    )
                    exit_code = result.exit_code
                    reply = result.text
                else:
                    # Legacy path (tests, fallback)
                    turn_start = time.perf_counter()
                    heartbeat_stop = asyncio.Event()
                    heartbeat_task = asyncio.create_task(
                        _heartbeat(tg, msg.chat_id, heartbeat_stop)
                    )
                    try:
                        result = await run_kimi_func(
                            prompt=msg.text,
                            session_id=sid,
                            workdir=cfg.kimi.default_workdir,
                            model=cfg.kimi.model,
                            agent=cfg.kimi.agent,
                            kimi_path=kimi_path,
                            timeout=KIMI_TIMEOUT_S,
                        )
                    finally:
                        heartbeat_stop.set()
                        heartbeat_task.cancel()
                        try:
                            await heartbeat_task
                        except (asyncio.CancelledError, Exception):
                            pass
                    elapsed_ms = int((time.perf_counter() - turn_start) * 1000)
                    LOG.info(
                        "turn chat=%d session=%s exit=%d ms=%d reply_len=%d",
                        msg.chat_id,
                        sid[:8],
                        result.exit_code,
                        elapsed_ms,
                        len(result.text or ""),
                    )
                    exit_code = result.exit_code
                    reply = result.text

                # ── assemble response ──
                if exit_code == 124:
                    minutes = KIMI_TIMEOUT_S / 60
                    reply = (
                        f"⏱️ Kimi is still thinking — your turn was cut off at "
                        f"{minutes:.0f} min.\n\n"
                        "Suggestions:\n"
                        "• Send a shorter follow-up to continue\n"
                        "• Split the task into smaller steps\n"
                        "• Run /reset and start fresh"
                    )
                elif exit_code != 0:
                    snippet = (result.stderr or "")[:500].strip() or "no stderr"
                    reply = f"⚠️ kimi error (exit {exit_code}): {snippet}"
                else:
                    reply = reply or "(empty reply)"

                try:
                    await tg.send_message(msg.chat_id, reply)
                except Exception as err:
                    LOG.error("sendMessage failed for chat=%s: %s", msg.chat_id, err)

            if not updates:
                await asyncio.sleep(0)

            save_state(state_path, state)


def _resolve_kimi_path() -> str:
    return os.environ.get("KIMI_BIN") or DEFAULT_KIMI_BIN


def main() -> None:  # pragma: no cover — wiring only
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    cfg_path = Path(os.environ.get("KIMI_BRIDGE_CONFIG") or DEFAULT_CONFIG_PATH)
    state_path = Path(os.environ.get("KIMI_BRIDGE_STATE") or DEFAULT_STATE_PATH)
    cfg = load_config(cfg_path)

    stop_event = asyncio.Event()

    async def _run() -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop_event.set)
        tg = TelegramClient(cfg.telegram.bot_token)
        await run(
            cfg=cfg,
            state_path=state_path,
            tg=tg,
            run_kimi_func=run_kimi,
            kimi_path=_resolve_kimi_path(),
            stop_event=stop_event,
            use_streaming=True,
        )

    asyncio.run(_run())


if __name__ == "__main__":  # pragma: no cover
    main()
