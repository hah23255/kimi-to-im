"""Long-running daemon: poll Telegram, route through kimi, reply."""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import time
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol

from src.config import Config, load_config
from src.kimi_runner import KimiResult, run_kimi
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
KIMI_TIMEOUT_S = 300.0  # bound a hung kimi process; surfaces as exit_code=124


class _TelegramLike(Protocol):
    async def __aenter__(self) -> "_TelegramLike": ...
    async def __aexit__(self, *exc: object) -> None: ...
    async def get_updates(self, offset: int, timeout: int = 30) -> list[dict[str, Any]]: ...
    async def send_message(self, chat_id: int, text: str) -> None: ...
    async def send_chat_action(self, chat_id: int, action: str = "typing") -> None: ...


RunKimiFunc = Callable[..., Awaitable[KimiResult]]


def _session_for(state: State, chat_id: int) -> str:
    sid = state.chats.get(chat_id)
    if sid:
        return sid
    sid = uuid.uuid4().hex
    state.chats[chat_id] = sid
    return sid


async def run(
    *,
    cfg: Config,
    state_path: Path,
    tg: _TelegramLike,
    run_kimi_func: RunKimiFunc,
    kimi_path: str,
    stop_event: asyncio.Event,
) -> None:
    """Main loop. Returns when stop_event is set."""
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

                try:
                    await tg.send_chat_action(msg.chat_id, "typing")
                except Exception as err:
                    LOG.debug("sendChatAction failed (non-fatal): %s", err)

                sid = _session_for(state, msg.chat_id)
                save_state(state_path, state)  # persist new session id before running

                turn_start = time.perf_counter()
                result = await run_kimi_func(
                    prompt=msg.text,
                    session_id=sid,
                    workdir=cfg.kimi.default_workdir,
                    model=cfg.kimi.model,
                    agent=cfg.kimi.agent,
                    kimi_path=kimi_path,
                    timeout=KIMI_TIMEOUT_S,
                )
                elapsed_ms = int((time.perf_counter() - turn_start) * 1000)
                LOG.info(
                    "turn chat=%d session=%s exit=%d ms=%d reply_len=%d",
                    msg.chat_id,
                    sid[:8],
                    result.exit_code,
                    elapsed_ms,
                    len(result.text or ""),
                )

                if result.exit_code != 0:
                    snippet = result.stderr[:500].strip() or "no stderr"
                    reply = f"⚠️ kimi error: {snippet}"
                else:
                    reply = result.text or "(empty reply)"

                try:
                    await tg.send_message(msg.chat_id, reply)
                except Exception as err:
                    LOG.error(
                        "sendMessage failed for chat=%s: %s", msg.chat_id, err
                    )

            save_state(state_path, state)


def _resolve_kimi_path() -> str:
    return os.environ.get("KIMI_BIN") or DEFAULT_KIMI_BIN


def main() -> None:  # pragma: no cover — wiring only
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # httpx logs every request URL at INFO; the URL contains the bot token in
    # the path. Suppress to WARNING so the token never lands in bridge.log.
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
        )

    asyncio.run(_run())


if __name__ == "__main__":  # pragma: no cover
    main()
