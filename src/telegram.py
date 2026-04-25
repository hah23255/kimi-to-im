"""Telegram glue: pure helpers (this task) + async HTTP client (Task 5)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.config import TelegramConfig


@dataclass(frozen=True)
class InboundMessage:
    update_id: int
    chat_id: int
    user_id: int
    text: str


def parse_update(update: dict[str, Any]) -> InboundMessage | None:
    """Return InboundMessage for a fresh text message, else None.

    Skips edited messages, non-text messages, and updates with no message.
    """
    msg = update.get("message")
    if not isinstance(msg, dict):
        return None
    text = msg.get("text")
    if not isinstance(text, str):
        return None
    chat = msg.get("chat") or {}
    sender = msg.get("from") or {}
    chat_id = chat.get("id")
    user_id = sender.get("id")
    update_id = update.get("update_id")
    if (
        not isinstance(chat_id, int)
        or not isinstance(user_id, int)
        or not isinstance(update_id, int)
    ):
        return None
    return InboundMessage(
        update_id=update_id, chat_id=chat_id, user_id=user_id, text=text
    )


def is_authorized(msg: InboundMessage, cfg: TelegramConfig) -> bool:
    if msg.user_id not in cfg.allowed_user_ids:
        return False
    if cfg.allowed_chat_ids and msg.chat_id not in cfg.allowed_chat_ids:
        return False
    return True


def chunk_message(text: str, max_len: int = 4096) -> list[str]:
    """Split text into Telegram-sized chunks. Prefer newline boundaries."""
    if not text:
        return []
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break
        cut = remaining.rfind("\n", 0, max_len)
        if cut == -1:
            cut = max_len  # hard split, no newline within window
        chunks.append(remaining[:cut])
        # If we cut on a newline, drop the boundary newline from the next chunk.
        if cut < len(remaining) and remaining[cut:cut + 1] == "\n":
            remaining = remaining[cut + 1:]
        else:
            remaining = remaining[cut:]
    return chunks
