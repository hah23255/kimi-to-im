"""Telegram glue: pure helpers + async HTTP client with media support."""
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
    photo: list[dict[str, Any]] | None = None
    document: dict[str, Any] | None = None


def parse_update(update: dict[str, Any]) -> InboundMessage | None:
    """Return InboundMessage for text, photo, or document message."""
    msg = update.get("message")
    if not isinstance(msg, dict):
        return None
    text = msg.get("text") or msg.get("caption") or ""
    photo = msg.get("photo")
    doc = msg.get("document")
    if not text and photo is None and doc is None:
        return None
    chat = msg.get("chat") or {}
    sender = msg.get("from") or {}
    cid = chat.get("id")
    uid = sender.get("id")
    uid_n = update.get("update_id")
    if not isinstance(cid, int) or not isinstance(uid, int) or not isinstance(uid_n, int):
        return None
    return InboundMessage(
        update_id=uid_n, chat_id=cid, user_id=uid, text=text,
        photo=list(photo) if isinstance(photo, list) else None,
        document=doc if isinstance(doc, dict) else None)


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
            cut = max_len
        chunks.append(remaining[:cut])
        if cut < len(remaining) and remaining[cut:cut + 1] == "\n":
            remaining = remaining[cut + 1:]
        else:
            remaining = remaining[cut:]
    return chunks


# --- HTTP client -----------------------------------------------------
import httpx


class TelegramClient:
    """Thin async wrapper around the Telegram bot HTTP API."""

    def __init__(self, bot_token: str, *, base_url: str = "https://api.telegram.org") -> None:
        self._base = f"{base_url}/bot{bot_token}"
        self._bot_token = bot_token
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "TelegramClient":
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(35.0))
        return self

    async def __aexit__(self, *exc: object) -> None:
        assert self._client is not None
        await self._client.aclose()
        self._client = None

    async def get_updates(self, offset: int, timeout: int = 30) -> list[dict[str, Any]]:
        assert self._client is not None
        r = await self._client.get(f"{self._base}/getUpdates", params={
            "offset": offset, "timeout": timeout, "allowed_updates": '["message"]'})
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"telegram getUpdates failed: {data.get('description')}")
        return list(data.get("result") or [])

    async def send_message(self, chat_id: int, text: str) -> None:
        assert self._client is not None
        for chunk in chunk_message(text):
            r = await self._client.post(f"{self._base}/sendMessage",
                                         json={"chat_id": chat_id, "text": chunk})
            data = r.json()
            if not data.get("ok"):
                raise RuntimeError(f"sendMessage failed: {data.get('description')}")

    async def send_chat_action(self, chat_id: int, action: str = "typing") -> None:
        assert self._client is not None
        r = await self._client.post(f"{self._base}/sendChatAction",
                                     json={"chat_id": chat_id, "action": action})
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"sendChatAction failed: {data.get('description')}")

    async def get_file(self, file_id: str) -> bytes:
        """Download a file from Telegram by file_id."""
        assert self._client is not None
        r = await self._client.get(f"{self._base}/getFile",
                                    params={"file_id": file_id})
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"getFile failed: {data.get('description')}")
        file_path = data["result"]["file_path"]
        r2 = await self._client.get(
            f"https://api.telegram.org/file/bot{self._bot_token}/{file_path}")
        return r2.content
