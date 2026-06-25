"""Bridge command handlers — /start /help /info /thinking /model /compact /reset."""
from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

DEFAULT_MODEL = "kimi-for-coding"

if TYPE_CHECKING:
    from src.config import Config
    from src.daemon import _TelegramLike
    from src.state import State
    from src.telegram import InboundMessage


async def handle(
    msg: "InboundMessage", tg: "_TelegramLike",
    state: "State", cfg: "Config",
) -> bool:
    """Route bridge commands. Returns True if handled."""
    stripped = msg.text.strip()
    parts = stripped.split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    cid = msg.chat_id

    handlers = {
        "/start":    _cmd_start,
        "/help":     _cmd_help,
        "/info":     _cmd_info,
        "/thinking": _cmd_thinking,
        "/model":    _cmd_model,
        "/compact":  _cmd_compact,
        "/reset":    _cmd_reset,
    }
    handler = handlers.get(cmd)
    if handler:
        await handler(tg, cid, args, state, cfg)
        return True
    return False


async def _cmd_start(tg: "_TelegramLike", cid: int, _a: str, _s: "State", _c: "Config") -> None:
    await tg.send_message(cid,
        "👋 Welcome! Kimi bridge bot.\n\n"
        "Send any message to chat with Kimi. History preserved per chat.\n\n"
        "Commands: /help /info /thinking /model /compact /reset")


async def _cmd_help(tg: "_TelegramLike", cid: int, _a: str, _s: "State", _c: "Config") -> None:
    await tg.send_message(cid,
        "📖 **Kimi Bridge Commands**\n\n"
        "/start – welcome\n/help – this list\n"
        "/info – session stats\n"
        "/thinking on|off – toggle reasoning visibility\n"
        "/model <name> – switch LLM model\n"
        "/compact – compress context\n"
        "/reset – start fresh\n\n"
        "K2.7 Code • streaming • 15min timeout")


async def _cmd_info(tg: "_TelegramLike", cid: int, _a: str, s: "State", c: "Config") -> None:
    sid = s.chats.get(cid)
    model = s.model_overrides.get(cid) or c.kimi.model or DEFAULT_MODEL
    thinking = "ON" if s.thinking_enabled.get(cid, True) else "OFF"
    await tg.send_message(cid,
        f"📊 **Session**\nModel: `{model}`\nThinking: {thinking}\n"
        f"Session: `{sid[:12] if sid else 'none'}`{'…' if sid else ''}")


async def _cmd_thinking(tg: "_TelegramLike", cid: int, args: str, s: "State", _c: "Config") -> None:
    mode = args.strip().lower()
    if mode in ("on", "true", "1"):
        s.thinking_enabled[cid] = True
        await tg.send_message(cid, "💭 Thinking: ON")
    elif mode in ("off", "false", "0"):
        s.thinking_enabled[cid] = False
        await tg.send_message(cid, "💭 Thinking: OFF")
    else:
        cur = "ON" if s.thinking_enabled.get(cid, True) else "OFF"
        await tg.send_message(cid, f"💭 Thinking: {cur}\n/thinking on|off")


async def _cmd_model(tg: "_TelegramLike", cid: int, args: str, s: "State", c: "Config") -> None:
    if not args.strip():
        m = s.model_overrides.get(cid) or c.kimi.model or DEFAULT_MODEL
        await tg.send_message(cid, f"Model: `{m}`\n/model <name>")
        return
    s.model_overrides[cid] = args.strip()
    await tg.send_message(cid, f"✅ Model → `{args.strip()}`")


async def _cmd_compact(tg: "_TelegramLike", cid: int, _a: str, s: "State", _c: "Config") -> None:
    sid = s.chats.get(cid)
    if not sid:
        await tg.send_message(cid, "No active session.")
        return
    kp = os.environ.get("KIMI_BIN", "kimi")
    try:
        proc = await asyncio.create_subprocess_exec(
            kp, "compact", "-S", sid,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode == 0:
            await tg.send_message(cid, f"🗜️ {stdout.decode(errors='replace').strip() or 'Done.'}")
        else:
            await tg.send_message(cid, f"⚠️ {stderr.decode(errors='replace')[:300]}")
    except asyncio.TimeoutError:
        await tg.send_message(cid, "⏱️ Compact timed out.")
    except Exception as exc:
        await tg.send_message(cid, f"⚠️ {exc}")


async def _cmd_reset(tg: "_TelegramLike", cid: int, _a: str, s: "State", _c: "Config") -> None:
    if cid in s.chats:
        del s.chats[cid]
        await tg.send_message(cid, "♻️ Session cleared.")
    else:
        await tg.send_message(cid, "No active session.")
