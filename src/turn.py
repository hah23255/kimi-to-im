"""Turn execution — streaming kimi invocation with event dispatch."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from src.kimi_stream import run_kimi_stream
from src.events import EventBuffer, dispatch_events, heartbeat

if TYPE_CHECKING:
    from src.config import Config
    from src.daemon import _TelegramLike
    from src.state import State
    from src.telegram import InboundMessage

LOG = logging.getLogger("kimi_telegram_bridge")
IDLE_TIMEOUT_S = 300.0   # 5 min inactivity limit (resets on stdout/stderr/tool activity)
MAX_TIMEOUT_S = 3600.0   # 60 min maximum runtime ceiling
KIMI_TIMEOUT_S = IDLE_TIMEOUT_S


async def execute_streaming(
    tg: "_TelegramLike", chat_id: int, msg: "InboundMessage",
    sid: str | None, cfg: "Config", kimi_path: str, state: "State",
) -> tuple[str, int]:
    """Run kimi turn with real-time event dispatch."""
    buf = EventBuffer()
    hb_stop = asyncio.Event()
    hb_task = asyncio.create_task(heartbeat(tg, chat_id, hb_stop))
    turn_start = time.perf_counter()
    try:
        result = await _invoke_kimi(msg, sid, cfg, kimi_path, state)
        # Persist the kimi-code native session ID on first turn (or if it changes)
        if result.session_id_discovered and result.session_id_discovered != state.chats.get(chat_id):
            state.chats[chat_id] = result.session_id_discovered
            LOG.info("session stored chat=%d → %s", chat_id, result.session_id_discovered[:24])
        te = state.thinking_enabled.get(chat_id, True)
        await dispatch_events(tg, chat_id, result.events, buf, te)
        await dispatch_events(tg, chat_id, [], buf, te)
    finally:
        _cancel_heartbeat(hb_stop, hb_task)
    elapsed = int((time.perf_counter() - turn_start) * 1000)
    effective_sid = state.chats.get(chat_id) or sid or "none"
    LOG.info("turn chat=%d session=%s exit=%d ms=%d reply=%d thinking=%d tools=%d",
             chat_id, effective_sid[:8], result.exit_code, elapsed,
             len(result.text or ""), result.total_thinking_chars, result.total_tool_calls)
    return result.text or "", result.exit_code


async def _invoke_kimi(
    msg: "InboundMessage", sid: str | None, cfg: "Config",
    kimi_path: str, state: "State",
) -> StreamResult:
    model = state.model_overrides.get(msg.chat_id) or cfg.kimi.model
    return await run_kimi_stream(
        prompt=msg.text, session_id=sid,
        workdir=cfg.kimi.default_workdir,
        model=model, agent=cfg.kimi.agent,
        kimi_path=kimi_path,
        idle_timeout=IDLE_TIMEOUT_S,
        max_timeout=MAX_TIMEOUT_S)


def _cancel_heartbeat(hb_stop: asyncio.Event, hb_task: asyncio.Task) -> None:
    hb_stop.set()
    hb_task.cancel()


async def execute_legacy(
    tg: "_TelegramLike", chat_id: int, msg: "InboundMessage",
    sid: str | None, cfg: "Config", kimi_path: str,
    run_kimi_func, state: "State",
) -> tuple[str, int, str]:
    """Run one turn via legacy synchronous kimi. For tests and fallback."""
    if not sid:
        import uuid
        sid = uuid.uuid4().hex
        state.chats[chat_id] = sid
    hb_stop = asyncio.Event()
    hb_task = asyncio.create_task(heartbeat(tg, chat_id, hb_stop))
    turn_start = time.perf_counter()
    try:
        result = await run_kimi_func(
            prompt=msg.text, session_id=sid,
            workdir=cfg.kimi.default_workdir,
            model=cfg.kimi.model, agent=cfg.kimi.agent,
            kimi_path=kimi_path, timeout=KIMI_TIMEOUT_S)
    finally:
        hb_stop.set()
        hb_task.cancel()
        try:
            await hb_task
        except (asyncio.CancelledError, Exception):
            pass
    elapsed = int((time.perf_counter() - turn_start) * 1000)
    effective_sid = (sid or "none")[:8]
    LOG.info("turn chat=%d session=%s exit=%d ms=%d reply=%d",
             chat_id, effective_sid, result.exit_code, elapsed, len(result.text or ""))
    return result.text or "", result.exit_code, result.stderr or ""


def get_or_create_session(state: "State", chat_id: int) -> str | None:
    """Return existing kimi-code session ID, or None to let kimi create one."""
    return state.chats.get(chat_id)
