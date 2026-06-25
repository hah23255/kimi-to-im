"""Long-running daemon: poll Telegram, route through kimi, reply."""
from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol

from src.config import Config, load_config
from src.commands import handle as handle_command
from src.health import record_turn, record_error, start_server
from src.kimi_runner import KimiResult
from src.media import build_media_prompt
from src.queue import TurnQueue
from src.state import State, load_state, save_state
from src.telegram import InboundMessage, TelegramClient, is_authorized, parse_update
from src.turn import execute_streaming, execute_legacy, get_or_create_session

LOG = logging.getLogger("kimi_telegram_bridge")
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.json"
DEFAULT_STATE_PATH = Path.home() / ".kimi" / "bridge" / "state.json"
LONG_POLL_TIMEOUT = 30
KIMI_TIMEOUT_S = 900.0
_QUEUE = TurnQueue()


class _TelegramLike(Protocol):
    async def __aenter__(self) -> "_TelegramLike": ...
    async def __aexit__(self, *exc: object) -> None: ...
    async def get_updates(self, offset: int, timeout: int = 30) -> list[dict[str, Any]]: ...
    async def send_message(self, chat_id: int, text: str) -> None: ...
    async def send_chat_action(self, chat_id: int, action: str = "typing") -> None: ...


RunKimiFunc = Callable[..., Awaitable[KimiResult]]


def _timeout_reply() -> str:
    m = KIMI_TIMEOUT_S / 60
    return (f"⏱️ Turn cut off at {m:.0f} min.\n\n"
            "• Send shorter follow-up\n• Split into smaller steps\n• /reset to start fresh")


def _error_reply(code: int) -> str:
    return f"⚠️ kimi error (exit {code})"


def _format_reply(text: str, code: int) -> str:
    if code == 124:
        record_error()
        return _timeout_reply()
    if code != 0:
        record_error()
        return _error_reply(code)
    record_turn()
    return text


async def _do_turn(msg: InboundMessage, tg: _TelegramLike, state: State,
                   cfg: Config, kimi_path: str,
                   run_kimi_func: RunKimiFunc, streaming: bool) -> None:
    prompt = await build_media_prompt(msg, tg, state, cfg)
    if prompt is None:
        return
    try:
        await tg.send_chat_action(msg.chat_id, "typing")
    except Exception:
        pass
    sid = get_or_create_session(state, msg.chat_id)
    save_state(DEFAULT_STATE_PATH, state)
    text, code = await _exec_turn(tg, msg, sid, cfg, kimi_path, state,
                                   run_kimi_func, streaming, prompt)
    reply = _format_reply(text, code)
    try:
        await tg.send_message(msg.chat_id, reply or "(empty reply)")
    except Exception as err:
        LOG.error("sendMessage failed chat=%s: %s", msg.chat_id, err)


async def _exec_turn(tg: _TelegramLike, msg: InboundMessage, sid: str,
                     cfg: Config, kimi_path: str, state: State,
                     run_kimi_func: RunKimiFunc, streaming: bool,
                     prompt: str) -> tuple[str, int]:
    if streaming:
        orig = msg.text
        try:
            object.__setattr__(msg, 'text', prompt)
            return await execute_streaming(tg, msg.chat_id, msg, sid, cfg, kimi_path, state)
        finally:
            object.__setattr__(msg, 'text', orig)
    text, code, _ = await execute_legacy(
        tg, msg.chat_id, msg, sid, cfg, kimi_path, run_kimi_func, state)
    return text, code


async def _process_one(msg: InboundMessage, tg: _TelegramLike, state: State,
                       cfg: Config, kimi_path: str,
                       run_kimi_func: RunKimiFunc, streaming: bool) -> None:
    if msg.text.strip().lower() == "/queue":
        lines = _QUEUE.status()
        await tg.send_message(msg.chat_id, "📋 " + "\n".join(lines))
        return
    if await handle_command(msg, tg, state, cfg):
        return
    status = await _QUEUE.submit(msg)
    if status is not None:
        await tg.send_message(msg.chat_id, status)
        return
    await _do_turn(msg, tg, state, cfg, kimi_path, run_kimi_func, streaming)
    _QUEUE.complete()
    # Drain pending
    while True:
        next_item = _QUEUE.next()
        if next_item is None:
            break
        nxt_msg, nxt_fut = next_item
        await _do_turn(nxt_msg, tg, state, cfg, kimi_path, run_kimi_func, streaming)
        _QUEUE.complete()
        nxt_fut.set_result(None)


async def _fetch_updates(tg: _TelegramLike, offset: int) -> list[dict[str, Any]]:
    try:
        return await asyncio.wait_for(
            tg.get_updates(offset=offset, timeout=LONG_POLL_TIMEOUT),
            timeout=LONG_POLL_TIMEOUT + 5)
    except asyncio.TimeoutError:
        return []
    except Exception as err:
        LOG.warning("getUpdates failed: %s", err)
        await asyncio.sleep(2)
        return []


async def run(*, cfg: Config, state_path: Path, tg: _TelegramLike,
              run_kimi_func: RunKimiFunc, kimi_path: str,
              stop_event: asyncio.Event, use_streaming: bool = False) -> None:
    _QUEUE.owner_chat_id = cfg.telegram.allowed_user_ids[0] if cfg.telegram.allowed_user_ids else 0
    state = load_state(state_path)
    async with tg:
        while not stop_event.is_set():
            updates = await _fetch_updates(tg, state.last_update_id + 1)
            for upd in updates:
                state.last_update_id = max(state.last_update_id, int(upd.get("update_id", 0)))
                m = parse_update(upd)
                if m is None:
                    continue
                if not is_authorized(m, cfg.telegram):
                    LOG.info("drop unauth user=%s", m.user_id)
                    continue
                await _process_one(m, tg, state, cfg, kimi_path,
                                    run_kimi_func, use_streaming)
            if not updates:
                await asyncio.sleep(0)
            save_state(state_path, state)


def main() -> None:
    from src.kimi_runner import run_kimi

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    cfg = load_config(Path(os.environ.get("KIMI_BRIDGE_CONFIG", str(DEFAULT_CONFIG_PATH))))
    sp = Path(os.environ.get("KIMI_BRIDGE_STATE", str(DEFAULT_STATE_PATH)))
    kp = os.environ.get("KIMI_BIN", "kimi")
    stop = asyncio.Event()

    async def _go() -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
        health_srv = await start_server()
        tg = TelegramClient(cfg.telegram.bot_token)
        try:
            await run(cfg=cfg, state_path=sp, tg=tg, run_kimi_func=run_kimi,
                      kimi_path=kp, stop_event=stop, use_streaming=True)
        finally:
            health_srv.close()
            await health_srv.wait_closed()

    asyncio.run(_go())


if __name__ == "__main__":
    main()
