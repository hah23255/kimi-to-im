# kimi-to-im Telegram Bridge — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Telegram→Kimi bridge: a long-running daemon that polls Telegram, spawns `kimi --print --output-format stream-json -S <session>` per inbound message, and replies with Kimi's response. Installed as a Kimi plugin (`~/.kimi/plugins/telegram-bridge/`) with the daemon supervised by `systemctl --user`.

**Architecture:** Two layers. (1) A Kimi plugin façade — `plugin.json` declares a `bridge` tool (`start | stop | status | logs | setup`) whose command is a Python control CLI that talks to systemd. (2) A separate long-running Python daemon (`python -m src.daemon`) that polls Telegram and shells out to `kimi`. Code lives at `~/.kimi/plugins/telegram-bridge/`; mutable runtime state at `~/.kimi/bridge/`. See `docs/design.md` for full spec.

**Tech Stack:** Python 3.11+ (system has 3.14), `httpx` for HTTP, `pytest` + `pytest-asyncio` + `pytest-httpx` for testing, `uv` for venv & dep management, `systemd --user` for daemon supervision. No Node, no claude-to-im npm package, no Anthropic SDKs.

**Repo:** `/home/i/.kimi/plugins/telegram-bridge/` (already initialised, branch `main`, root commit `1f47f51`).

---

## File map

Source (production):
- `pyproject.toml` — project metadata + deps (httpx + dev: pytest, pytest-asyncio, pytest-httpx)
- `plugin.json` — Kimi plugin manifest
- `config.example.json` — template config for users
- `install.sh` — one-shot installer (venv + systemd unit)
- `systemd/kimi-telegram-bridge.service.template` — systemd user unit
- `src/__init__.py` — package marker
- `src/config.py` — load/validate `config.json`
- `src/state.py` — atomic JSON state at `~/.kimi/bridge/state.json`
- `src/telegram.py` — pure helpers (`parse_update`, `is_authorized`, `chunk_message`) + async HTTP client
- `src/kimi_runner.py` — subprocess spawn + stream-json parser
- `src/daemon.py` — main async loop wiring everything together
- `src/control.py` — plugin-tool CLI (start/stop/status/logs/setup)

Tests:
- `tests/__init__.py`
- `tests/conftest.py` — shared fixtures (tmp_path, fake config)
- `tests/test_config.py`
- `tests/test_state.py`
- `tests/test_telegram_pure.py`
- `tests/test_telegram_http.py`
- `tests/test_kimi_runner.py`
- `tests/test_daemon.py`
- `tests/test_control.py`

Docs:
- `README.md` — operator-facing install + usage (already stubbed)
- `docs/design.md` — architecture spec (already committed)

---

## Conventions for every task

**Working directory:** `/home/i/.kimi/plugins/telegram-bridge/` (cd there once at start of session).

**Run tests:** `.venv/bin/pytest -v` from repo root after the venv is set up in Task 1. Each task commits with `git -C /home/i/.kimi/plugins/telegram-bridge ...` if cwd is unclear.

**Commit message style:** Conventional commits — `feat:`, `test:`, `chore:`, `docs:`, `fix:`. Keep subject ≤ 72 chars. Always include `Co-Authored-By` trailer if you are an agent.

**TDD discipline:** For every behaviour, write the failing test, run it and observe failure, then write the minimal code, run again, observe pass, commit. Do not skip the "observe failure" step — confirm the test fails for the right reason.

---

## Task 1: Project skeleton, venv, pytest infrastructure

**Files:**
- Create: `pyproject.toml`
- Create: `src/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_smoke.py`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "kimi-telegram-bridge"
version = "0.1.0"
description = "Telegram bridge for the Kimi CLI"
requires-python = ">=3.11"
dependencies = [
    "httpx>=0.27",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
    "pytest-httpx>=0.30",
]

[tool.hatch.build.targets.wheel]
packages = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create `src/__init__.py` and `tests/__init__.py` (both empty)**

```python
# src/__init__.py
```
```python
# tests/__init__.py
```

- [ ] **Step 3: Write `tests/conftest.py` with shared fixtures**

```python
"""Shared pytest fixtures."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def sample_config_dict() -> dict[str, Any]:
    """A valid config.json structure used across tests."""
    return {
        "telegram": {
            "bot_token": "1234:abcXYZ",
            "allowed_user_ids": [99999999],
            "allowed_chat_ids": [],
        },
        "kimi": {
            "default_workdir": "/tmp",
            "model": "",
            "agent": "default",
        },
    }


@pytest.fixture
def config_file(tmp_path: Path, sample_config_dict: dict[str, Any]) -> Path:
    """Write sample_config_dict to a temp config.json and return the path."""
    p = tmp_path / "config.json"
    p.write_text(json.dumps(sample_config_dict))
    return p
```

- [ ] **Step 4: Write a smoke test that proves test infra works**

```python
# tests/test_smoke.py
"""Confirms pytest discovers tests and can import the src package."""
import src


def test_package_importable() -> None:
    assert src is not None
```

- [ ] **Step 5: Set up the venv and dev install**

```bash
cd /home/i/.kimi/plugins/telegram-bridge
uv venv .venv --python 3.11
.venv/bin/pip install -e ".[dev]"
```
Expected: `.venv/` directory created; pip reports successful install of httpx + pytest + pytest-asyncio + pytest-httpx.

- [ ] **Step 6: Run the smoke test**

```bash
.venv/bin/pytest -v
```
Expected: `1 passed`.

- [ ] **Step 7: Commit**

```bash
git -C /home/i/.kimi/plugins/telegram-bridge add pyproject.toml src/__init__.py tests/__init__.py tests/conftest.py tests/test_smoke.py
git -C /home/i/.kimi/plugins/telegram-bridge commit -m "$(cat <<'EOF'
chore: scaffold project with pyproject, src package, and pytest

Establishes the Python package layout, pinned runtime dependency
on httpx, and dev-only test deps (pytest + pytest-asyncio + pytest-httpx).
A smoke test verifies the venv and import path work end-to-end.

Co-Authored-By: HH <hh@local>
EOF
)"
```

---

## Task 2: Config loader

**Files:**
- Create: `src/config.py`
- Create: `tests/test_config.py`

The loader takes a path, parses JSON, and returns a typed dataclass. Validates: `telegram.bot_token` non-empty, `telegram.allowed_user_ids` non-empty list of ints, `kimi.default_workdir` accepted as a string (no existence check; directory may be created later). Surfaces clear errors so `control.py setup` can report what is wrong.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
"""Tests for src.config — load_config and validation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.config import (
    Config,
    ConfigError,
    KimiConfig,
    TelegramConfig,
    load_config,
)


def test_load_valid_config_returns_typed_dataclass(config_file: Path) -> None:
    cfg = load_config(config_file)
    assert isinstance(cfg, Config)
    assert isinstance(cfg.telegram, TelegramConfig)
    assert isinstance(cfg.kimi, KimiConfig)
    assert cfg.telegram.bot_token == "1234:abcXYZ"
    assert cfg.telegram.allowed_user_ids == [99999999]
    assert cfg.telegram.allowed_chat_ids == []
    assert cfg.kimi.default_workdir == "/tmp"
    assert cfg.kimi.model == ""
    assert cfg.kimi.agent == "default"


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.json")


def test_invalid_json_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("{ not valid json")
    with pytest.raises(ConfigError, match="invalid JSON"):
        load_config(p)


def test_missing_bot_token_raises(tmp_path: Path, sample_config_dict: dict) -> None:
    sample_config_dict["telegram"]["bot_token"] = ""
    p = tmp_path / "config.json"
    p.write_text(json.dumps(sample_config_dict))
    with pytest.raises(ConfigError, match="telegram.bot_token"):
        load_config(p)


def test_empty_allowed_user_ids_raises(tmp_path: Path, sample_config_dict: dict) -> None:
    sample_config_dict["telegram"]["allowed_user_ids"] = []
    p = tmp_path / "config.json"
    p.write_text(json.dumps(sample_config_dict))
    with pytest.raises(ConfigError, match="allowed_user_ids"):
        load_config(p)


def test_non_int_allowed_user_id_raises(tmp_path: Path, sample_config_dict: dict) -> None:
    sample_config_dict["telegram"]["allowed_user_ids"] = ["not-an-int"]
    p = tmp_path / "config.json"
    p.write_text(json.dumps(sample_config_dict))
    with pytest.raises(ConfigError, match="must be integers"):
        load_config(p)


def test_kimi_defaults_applied_when_missing(tmp_path: Path, sample_config_dict: dict) -> None:
    del sample_config_dict["kimi"]
    p = tmp_path / "config.json"
    p.write_text(json.dumps(sample_config_dict))
    cfg = load_config(p)
    assert cfg.kimi.default_workdir == ""
    assert cfg.kimi.model == ""
    assert cfg.kimi.agent == "default"
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
cd /home/i/.kimi/plugins/telegram-bridge && .venv/bin/pytest tests/test_config.py -v
```
Expected: `ModuleNotFoundError: No module named 'src.config'`.

- [ ] **Step 3: Implement `src/config.py`**

```python
"""Loader and validator for ~/.kimi/plugins/telegram-bridge/config.json."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    """Raised when config.json is missing, malformed, or fails validation."""


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    allowed_user_ids: list[int]
    allowed_chat_ids: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class KimiConfig:
    default_workdir: str = ""
    model: str = ""
    agent: str = "default"


@dataclass(frozen=True)
class Config:
    telegram: TelegramConfig
    kimi: KimiConfig


def load_config(path: Path) -> Config:
    if not path.exists():
        raise ConfigError(f"config not found at {path}")

    try:
        raw: dict[str, Any] = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON in {path}: {exc}") from exc

    tg_raw = raw.get("telegram") or {}
    bot_token = tg_raw.get("bot_token") or ""
    if not isinstance(bot_token, str) or not bot_token:
        raise ConfigError("telegram.bot_token must be a non-empty string")

    allowed_user_ids = tg_raw.get("allowed_user_ids") or []
    if not isinstance(allowed_user_ids, list) or not allowed_user_ids:
        raise ConfigError(
            "telegram.allowed_user_ids must be a non-empty list (default-deny)"
        )
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in allowed_user_ids):
        raise ConfigError("telegram.allowed_user_ids entries must be integers")

    allowed_chat_ids = tg_raw.get("allowed_chat_ids") or []
    if not isinstance(allowed_chat_ids, list) or not all(
        isinstance(x, int) and not isinstance(x, bool) for x in allowed_chat_ids
    ):
        raise ConfigError("telegram.allowed_chat_ids must be a list of integers")

    kimi_raw = raw.get("kimi") or {}
    return Config(
        telegram=TelegramConfig(
            bot_token=bot_token,
            allowed_user_ids=list(allowed_user_ids),
            allowed_chat_ids=list(allowed_chat_ids),
        ),
        kimi=KimiConfig(
            default_workdir=str(kimi_raw.get("default_workdir") or ""),
            model=str(kimi_raw.get("model") or ""),
            agent=str(kimi_raw.get("agent") or "default"),
        ),
    )
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
.venv/bin/pytest tests/test_config.py -v
```
Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git -C /home/i/.kimi/plugins/telegram-bridge add src/config.py tests/test_config.py
git -C /home/i/.kimi/plugins/telegram-bridge commit -m "$(cat <<'EOF'
feat(config): add config loader with validation

Defines Config / TelegramConfig / KimiConfig dataclasses and
load_config() that surfaces clear errors for missing files,
malformed JSON, missing bot_token, empty allowed_user_ids
(default-deny posture), and non-integer IDs.

Co-Authored-By: HH <hh@local>
EOF
)"
```

---

## Task 3: State persistence

**Files:**
- Create: `src/state.py`
- Create: `tests/test_state.py`

`State` holds `last_update_id: int` and `chats: dict[int, str]` (chat_id → kimi session_id). Persisted at `~/.kimi/bridge/state.json`. Writes are atomic (write to `.tmp` then `os.replace`) so a crash mid-write never corrupts the file. Reads tolerate a missing file (return zeroed state) and tolerate the parent directory not existing (created on first write).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_state.py
"""Tests for src.state — atomic JSON state file."""
from __future__ import annotations

from pathlib import Path

from src.state import State, load_state, save_state


def test_load_missing_file_returns_zero_state(tmp_path: Path) -> None:
    s = load_state(tmp_path / "state.json")
    assert s.last_update_id == 0
    assert s.chats == {}


def test_save_then_load_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    original = State(last_update_id=42, chats={123: "abc-uuid", 456: "def-uuid"})
    save_state(p, original)

    loaded = load_state(p)
    assert loaded.last_update_id == 42
    assert loaded.chats == {123: "abc-uuid", 456: "def-uuid"}


def test_save_creates_parent_dir(tmp_path: Path) -> None:
    p = tmp_path / "nested" / "dirs" / "state.json"
    save_state(p, State(last_update_id=1, chats={}))
    assert p.exists()


def test_save_is_atomic_no_tmp_left_behind(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    save_state(p, State(last_update_id=1, chats={1: "u"}))
    siblings = list(p.parent.iterdir())
    assert siblings == [p], f"unexpected files: {siblings}"


def test_corrupt_state_file_returns_zero_state(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    p.write_text("{ not json")
    s = load_state(p)
    assert s.last_update_id == 0
    assert s.chats == {}


def test_chat_keys_round_trip_as_int(tmp_path: Path) -> None:
    """JSON object keys are strings; loader must coerce back to int."""
    p = tmp_path / "state.json"
    save_state(p, State(last_update_id=5, chats={123: "u"}))
    loaded = load_state(p)
    assert all(isinstance(k, int) for k in loaded.chats)
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
.venv/bin/pytest tests/test_state.py -v
```
Expected: `ModuleNotFoundError: No module named 'src.state'`.

- [ ] **Step 3: Implement `src/state.py`**

```python
"""Atomic JSON-backed bridge state at ~/.kimi/bridge/state.json."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class State:
    last_update_id: int = 0
    chats: dict[int, str] = field(default_factory=dict)


def load_state(path: Path) -> State:
    if not path.exists():
        return State()
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError:
        return State()
    chats_raw = raw.get("chats") or {}
    return State(
        last_update_id=int(raw.get("last_update_id", 0)),
        chats={int(k): str(v) for k, v in chats_raw.items()},
    )


def save_state(path: Path, state: State) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = {
        "last_update_id": state.last_update_id,
        "chats": {str(k): v for k, v in state.chats.items()},
    }
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, path)
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
.venv/bin/pytest tests/test_state.py -v
```
Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git -C /home/i/.kimi/plugins/telegram-bridge add src/state.py tests/test_state.py
git -C /home/i/.kimi/plugins/telegram-bridge commit -m "$(cat <<'EOF'
feat(state): add atomic JSON state for last_update_id and chat sessions

State is written via tmp+rename so a mid-write crash never
corrupts state.json. Missing or malformed files are tolerated
(loader returns a zeroed state). Parent directory is created
on first save so the daemon does not depend on ~/.kimi/bridge/
existing ahead of time.

Co-Authored-By: HH <hh@local>
EOF
)"
```

---

## Task 4: Pure helpers for Telegram update handling

**Files:**
- Create: `src/telegram.py` (initial pure-function shell)
- Create: `tests/test_telegram_pure.py`

This task covers ONLY the pure logic. The async HTTP client comes in Task 5 (same file). We use a single `telegram.py` because the pure helpers and HTTP client are tightly coupled (both speak the Telegram update vocabulary).

Pure functions:
- `parse_update(update: dict) -> InboundMessage | None` — returns `None` for non-text messages, edited messages, and updates without a `message` field.
- `is_authorized(msg: InboundMessage, cfg: TelegramConfig) -> bool` — user_id in allowed_user_ids; if allowed_chat_ids is non-empty, also chat_id must be in it.
- `chunk_message(text: str, max_len: int = 4096) -> list[str]` — split long replies on newline boundaries when possible.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_telegram_pure.py
"""Tests for the pure helpers in src.telegram."""
from __future__ import annotations

import pytest

from src.config import TelegramConfig
from src.telegram import InboundMessage, chunk_message, is_authorized, parse_update


# --- parse_update ----------------------------------------------------

def _msg(text: str = "hi", user_id: int = 99999999, chat_id: int = 99999999) -> dict:
    return {
        "update_id": 100,
        "message": {
            "message_id": 1,
            "date": 0,
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
            "text": text,
        },
    }


def test_parse_update_extracts_text() -> None:
    msg = parse_update(_msg(text="hello kimi"))
    assert msg == InboundMessage(
        update_id=100, chat_id=99999999, user_id=99999999, text="hello kimi"
    )


def test_parse_update_returns_none_when_no_message() -> None:
    assert parse_update({"update_id": 100}) is None


def test_parse_update_returns_none_for_non_text_message() -> None:
    upd = _msg()
    del upd["message"]["text"]
    upd["message"]["photo"] = [{"file_id": "abc"}]
    assert parse_update(upd) is None


def test_parse_update_returns_none_for_edited_message() -> None:
    upd = _msg()
    upd["edited_message"] = upd.pop("message")
    assert parse_update(upd) is None


# --- is_authorized ---------------------------------------------------

def _cfg(user_ids: list[int], chat_ids: list[int] | None = None) -> TelegramConfig:
    return TelegramConfig(
        bot_token="x",
        allowed_user_ids=user_ids,
        allowed_chat_ids=chat_ids or [],
    )


def test_is_authorized_allows_listed_user() -> None:
    msg = InboundMessage(update_id=1, chat_id=10, user_id=42, text="hi")
    assert is_authorized(msg, _cfg([42])) is True


def test_is_authorized_blocks_unlisted_user() -> None:
    msg = InboundMessage(update_id=1, chat_id=10, user_id=999, text="hi")
    assert is_authorized(msg, _cfg([42])) is False


def test_is_authorized_with_chat_whitelist_blocks_other_chats() -> None:
    msg = InboundMessage(update_id=1, chat_id=20, user_id=42, text="hi")
    assert is_authorized(msg, _cfg([42], chat_ids=[10])) is False


def test_is_authorized_with_chat_whitelist_allows_listed_chat() -> None:
    msg = InboundMessage(update_id=1, chat_id=10, user_id=42, text="hi")
    assert is_authorized(msg, _cfg([42], chat_ids=[10])) is True


# --- chunk_message ---------------------------------------------------

def test_chunk_short_message_returned_as_single_chunk() -> None:
    assert chunk_message("hello", max_len=4096) == ["hello"]


def test_chunk_empty_message_returned_as_empty_list() -> None:
    assert chunk_message("", max_len=4096) == []


def test_chunk_long_message_splits_on_newlines() -> None:
    body = ("line\n" * 1000).rstrip("\n")
    chunks = chunk_message(body, max_len=100)
    assert all(len(c) <= 100 for c in chunks)
    assert "".join(c if c.endswith("\n") else c + "\n" for c in chunks).rstrip("\n") == body


def test_chunk_long_unbroken_text_hard_splits() -> None:
    body = "a" * 9000
    chunks = chunk_message(body, max_len=4096)
    assert all(len(c) <= 4096 for c in chunks)
    assert "".join(chunks) == body


def test_chunk_default_max_is_4096() -> None:
    body = "x" * 5000
    chunks = chunk_message(body)
    assert all(len(c) <= 4096 for c in chunks)
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
.venv/bin/pytest tests/test_telegram_pure.py -v
```
Expected: `ModuleNotFoundError: No module named 'src.telegram'`.

- [ ] **Step 3: Implement the pure helpers in `src/telegram.py`**

```python
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
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
.venv/bin/pytest tests/test_telegram_pure.py -v
```
Expected: `13 passed`.

- [ ] **Step 5: Commit**

```bash
git -C /home/i/.kimi/plugins/telegram-bridge add src/telegram.py tests/test_telegram_pure.py
git -C /home/i/.kimi/plugins/telegram-bridge commit -m "$(cat <<'EOF'
feat(telegram): add pure helpers parse_update, is_authorized, chunk_message

These are the deterministic, side-effect-free parts of the
Telegram glue: turning a raw update into an InboundMessage,
applying the user/chat whitelists, and splitting long replies
to fit Telegram's 4096-character per-message limit. The HTTP
client lands in the next task.

Co-Authored-By: HH <hh@local>
EOF
)"
```

---

## Task 5: Async Telegram HTTP client

**Files:**
- Modify: `src/telegram.py` (append `TelegramClient` class)
- Create: `tests/test_telegram_http.py`

`TelegramClient` wraps `httpx.AsyncClient` with three methods we actually need:

- `get_updates(offset: int, timeout: int = 30) -> list[dict]` — long-poll Telegram.
- `send_message(chat_id: int, text: str) -> None` — splits via `chunk_message`, posts each chunk.
- `send_chat_action(chat_id: int, action: str = "typing") -> None`.

Tests use `pytest-httpx` to assert the right URLs / payloads are sent and stubbed responses are parsed correctly.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_telegram_http.py
"""Tests for the async TelegramClient HTTP wrapper."""
from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from src.telegram import TelegramClient


pytestmark = pytest.mark.asyncio


async def test_get_updates_long_polls_with_offset_and_timeout(
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        url="https://api.telegram.org/botTOKEN/getUpdates?offset=42&timeout=30&allowed_updates=%5B%22message%22%5D",
        method="GET",
        json={"ok": True, "result": [{"update_id": 50}]},
    )
    async with TelegramClient("TOKEN") as tg:
        updates = await tg.get_updates(offset=42, timeout=30)
    assert updates == [{"update_id": 50}]


async def test_get_updates_raises_on_telegram_error(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://api.telegram.org/botTOKEN/getUpdates?offset=1&timeout=30&allowed_updates=%5B%22message%22%5D",
        method="GET",
        json={"ok": False, "description": "Unauthorized"},
        status_code=401,
    )
    async with TelegramClient("TOKEN") as tg:
        with pytest.raises(RuntimeError, match="Unauthorized"):
            await tg.get_updates(offset=1)


async def test_send_message_splits_long_text(httpx_mock: HTTPXMock) -> None:
    body = "x" * 9000
    for _ in range(3):
        httpx_mock.add_response(
            url="https://api.telegram.org/botTOKEN/sendMessage",
            method="POST",
            json={"ok": True, "result": {}},
        )
    async with TelegramClient("TOKEN") as tg:
        await tg.send_message(chat_id=10, text=body)
    requests = httpx_mock.get_requests()
    assert len(requests) == 3
    for r in requests:
        assert r.method == "POST"
        assert r.url.path == "/botTOKEN/sendMessage"


async def test_send_message_skips_empty_text(httpx_mock: HTTPXMock) -> None:
    async with TelegramClient("TOKEN") as tg:
        await tg.send_message(chat_id=10, text="")
    assert httpx_mock.get_requests() == []


async def test_send_chat_action_posts_typing(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://api.telegram.org/botTOKEN/sendChatAction",
        method="POST",
        json={"ok": True, "result": True},
    )
    async with TelegramClient("TOKEN") as tg:
        await tg.send_chat_action(chat_id=10, action="typing")
    req = httpx_mock.get_requests()[0]
    assert req.method == "POST"
    body = req.read().decode()
    assert "typing" in body
    assert "10" in body
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
.venv/bin/pytest tests/test_telegram_http.py -v
```
Expected: `ImportError: cannot import name 'TelegramClient' from 'src.telegram'`.

- [ ] **Step 3: Append `TelegramClient` to `src/telegram.py`**

Append exactly this block to the existing `src/telegram.py` (preserving the pure helpers from Task 4):

```python
# --- HTTP client -----------------------------------------------------
import httpx


class TelegramClient:
    """Thin async wrapper around the Telegram bot HTTP API."""

    def __init__(
        self, bot_token: str, *, base_url: str = "https://api.telegram.org"
    ) -> None:
        self._base = f"{base_url}/bot{bot_token}"
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "TelegramClient":
        # 35s read timeout > 30s long-poll timeout to leave slack.
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(35.0))
        return self

    async def __aexit__(self, *exc: object) -> None:
        assert self._client is not None
        await self._client.aclose()
        self._client = None

    async def get_updates(
        self, offset: int, timeout: int = 30
    ) -> list[dict[str, Any]]:
        assert self._client is not None
        params = {
            "offset": offset,
            "timeout": timeout,
            "allowed_updates": '["message"]',
        }
        r = await self._client.get(f"{self._base}/getUpdates", params=params)
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(
                f"telegram getUpdates failed: {data.get('description', 'unknown error')}"
            )
        return list(data.get("result") or [])

    async def send_message(self, chat_id: int, text: str) -> None:
        assert self._client is not None
        for chunk in chunk_message(text):
            r = await self._client.post(
                f"{self._base}/sendMessage",
                json={"chat_id": chat_id, "text": chunk},
            )
            data = r.json()
            if not data.get("ok"):
                raise RuntimeError(
                    f"telegram sendMessage failed: {data.get('description', 'unknown error')}"
                )

    async def send_chat_action(
        self, chat_id: int, action: str = "typing"
    ) -> None:
        assert self._client is not None
        r = await self._client.post(
            f"{self._base}/sendChatAction",
            json={"chat_id": chat_id, "action": action},
        )
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(
                f"telegram sendChatAction failed: {data.get('description', 'unknown error')}"
            )
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
.venv/bin/pytest tests/test_telegram_http.py -v
```
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git -C /home/i/.kimi/plugins/telegram-bridge add src/telegram.py tests/test_telegram_http.py
git -C /home/i/.kimi/plugins/telegram-bridge commit -m "$(cat <<'EOF'
feat(telegram): add async TelegramClient (getUpdates / sendMessage / sendChatAction)

Wraps httpx.AsyncClient with the three methods the daemon needs.
sendMessage automatically chunks via chunk_message so 4096-char
limit handling is transparent to the caller. Telegram-side
errors raise RuntimeError so the daemon's outer loop can
surface them and back off.

Co-Authored-By: HH <hh@local>
EOF
)"
```

---

## Task 6: Kimi runner (parser + subprocess spawn)

**Files:**
- Create: `src/kimi_runner.py`
- Create: `tests/test_kimi_runner.py`

Two layers:

1. **Pure parser** — `parse_stream_json(stdout: str) -> str` accumulates assistant text from kimi's newline-delimited JSON. We TDD this with hand-crafted fixtures because the real kimi format is documented but not contractually frozen — we want a single chokepoint that's easy to update.
2. **Subprocess spawn** — `run_kimi(prompt, *, session_id, workdir, model, agent, kimi_path) -> KimiResult` shells the binary out and parses. We integration-test this against a fake `kimi` shell stub that emits a known stream.

**Subprocess strategy:** use `subprocess.run` (with `args` as a list and no shell — safe by construction) wrapped in `asyncio.to_thread` to keep the async daemon non-blocking. This avoids needing `asyncio.subprocess` and gives identical behaviour for our use case (we wait for the whole turn anyway, so streaming back to the daemon is unnecessary).

The parser accepts these event shapes (observed from kimi v1.39.0):
- `{"type": "assistant", "content": [{"type": "text", "text": "..."}]}` — accumulate text
- `{"type": "assistant", "content": [{"type": "think", "text": "..."}]}` — ignore (thinking)
- Anything else — ignore

The runner's contract: `KimiResult(text: str, exit_code: int, stderr: str)`.

- [ ] **Step 1: Write the failing parser tests**

```python
# tests/test_kimi_runner.py
"""Tests for src.kimi_runner — parser and subprocess spawn."""
from __future__ import annotations

import stat
import textwrap
from pathlib import Path

import pytest

from src.kimi_runner import KimiResult, parse_stream_json, run_kimi


# --- parser ----------------------------------------------------------

def test_parse_extracts_assistant_text() -> None:
    stream = (
        '{"type": "assistant", "content": [{"type": "text", "text": "Hello "}]}\n'
        '{"type": "assistant", "content": [{"type": "text", "text": "world"}]}\n'
    )
    assert parse_stream_json(stream) == "Hello world"


def test_parse_ignores_think_blocks() -> None:
    stream = (
        '{"type": "assistant", "content": [{"type": "think", "text": "hmm"}]}\n'
        '{"type": "assistant", "content": [{"type": "text", "text": "hi"}]}\n'
    )
    assert parse_stream_json(stream) == "hi"


def test_parse_ignores_unknown_event_types() -> None:
    stream = (
        '{"type": "turn_begin"}\n'
        '{"type": "step_begin", "id": 1}\n'
        '{"type": "assistant", "content": [{"type": "text", "text": "ok"}]}\n'
        '{"type": "turn_end"}\n'
    )
    assert parse_stream_json(stream) == "ok"


def test_parse_skips_blank_lines_and_invalid_json() -> None:
    stream = (
        "\n"
        "not-json-junk\n"
        '{"type": "assistant", "content": [{"type": "text", "text": "hi"}]}\n'
    )
    assert parse_stream_json(stream) == "hi"


def test_parse_handles_assistant_with_multiple_text_parts() -> None:
    stream = (
        '{"type": "assistant", "content": ['
        '{"type": "text", "text": "part one. "},'
        '{"type": "text", "text": "part two."}'
        ']}\n'
    )
    assert parse_stream_json(stream) == "part one. part two."


def test_parse_empty_stream_returns_empty_string() -> None:
    assert parse_stream_json("") == ""
```

- [ ] **Step 2: Add the failing subprocess test**

Append to `tests/test_kimi_runner.py`:

```python
# --- run_kimi (integration with a fake kimi binary) ------------------

@pytest.fixture
def fake_kimi(tmp_path: Path) -> Path:
    """Create an executable shell stub that emits a known stream-json reply."""
    script = tmp_path / "kimi"
    script.write_text(
        textwrap.dedent(
            """\
            #!/bin/sh
            # Read prompt from stdin to mimic real kimi --print behaviour.
            cat > /dev/null
            cat <<'EOF'
            {"type": "assistant", "content": [{"type": "text", "text": "fake reply"}]}
            EOF
            """
        )
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


pytestmark = pytest.mark.asyncio


async def test_run_kimi_returns_assistant_text(fake_kimi: Path, tmp_path: Path) -> None:
    result = await run_kimi(
        prompt="hello",
        session_id="sess-1",
        workdir=str(tmp_path),
        model="",
        agent="default",
        kimi_path=str(fake_kimi),
    )
    assert isinstance(result, KimiResult)
    assert result.exit_code == 0
    assert result.text == "fake reply"


async def test_run_kimi_surfaces_nonzero_exit(tmp_path: Path) -> None:
    """A fake binary that exits 1 should produce KimiResult with exit_code=1."""
    script = tmp_path / "kimi-fail"
    script.write_text("#!/bin/sh\necho boom 1>&2\nexit 1\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    result = await run_kimi(
        prompt="x",
        session_id="s",
        workdir=str(tmp_path),
        model="",
        agent="default",
        kimi_path=str(script),
    )
    assert result.exit_code == 1
    assert "boom" in result.stderr
    assert result.text == ""


async def test_run_kimi_passes_session_and_workdir_args(tmp_path: Path) -> None:
    """The fake binary records its argv so we can assert the runner built the
    correct command line."""
    captured = tmp_path / "argv.txt"
    script = tmp_path / "kimi-record"
    script.write_text(
        textwrap.dedent(
            f"""\
            #!/bin/sh
            cat > /dev/null
            printf '%s\\n' "$@" > "{captured}"
            cat <<'EOF'
            {{"type": "assistant", "content": [{{"type": "text", "text": "ok"}}]}}
            EOF
            """
        )
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    await run_kimi(
        prompt="hi",
        session_id="abc",
        workdir="/tmp/work",
        model="kimi-code/kimi-for-coding",
        agent="default",
        kimi_path=str(script),
    )
    args = captured.read_text().splitlines()
    assert "--print" in args
    assert "--output-format" in args
    assert "stream-json" in args
    assert "-S" in args and "abc" in args
    assert "--work-dir" in args and "/tmp/work" in args
    assert "--model" in args and "kimi-code/kimi-for-coding" in args
    assert "--agent" in args and "default" in args
```

- [ ] **Step 3: Run tests, confirm they fail**

```bash
.venv/bin/pytest tests/test_kimi_runner.py -v
```
Expected: `ModuleNotFoundError: No module named 'src.kimi_runner'`.

- [ ] **Step 4: Implement `src/kimi_runner.py`**

```python
"""Spawn the kimi CLI and parse its stream-json output."""
from __future__ import annotations

import asyncio
import json
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class KimiResult:
    text: str
    exit_code: int
    stderr: str


def parse_stream_json(stdout: str) -> str:
    """Accumulate assistant text from kimi's newline-delimited JSON stream.

    Quietly ignores blank lines, malformed JSON, non-assistant events,
    and `think` content blocks (which are model thinking, not the reply).
    """
    chunks: list[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "assistant":
            continue
        for part in event.get("content") or []:
            if isinstance(part, dict) and part.get("type") == "text":
                text = part.get("text")
                if isinstance(text, str):
                    chunks.append(text)
    return "".join(chunks)


def _run_sync(args: list[str], prompt: str) -> KimiResult:
    """Synchronous worker for subprocess invocation. Called via asyncio.to_thread."""
    completed = subprocess.run(
        args,
        input=prompt.encode(),
        capture_output=True,
        check=False,
    )
    return KimiResult(
        text=parse_stream_json(completed.stdout.decode("utf-8", errors="replace")),
        exit_code=completed.returncode,
        stderr=completed.stderr.decode("utf-8", errors="replace"),
    )


async def run_kimi(
    prompt: str,
    *,
    session_id: str,
    workdir: str,
    model: str,
    agent: str,
    kimi_path: str,
) -> KimiResult:
    """Run the kimi CLI in --print stream-json mode. Returns when the turn ends."""
    args: list[str] = [
        kimi_path,
        "--print",
        "--output-format",
        "stream-json",
        "-S",
        session_id,
        "--work-dir",
        workdir,
        "--agent",
        agent,
    ]
    if model:
        args.extend(["--model", model])
    return await asyncio.to_thread(_run_sync, args, prompt)
```

- [ ] **Step 5: Run tests, confirm they pass**

```bash
.venv/bin/pytest tests/test_kimi_runner.py -v
```
Expected: `9 passed`.

- [ ] **Step 6: Commit**

```bash
git -C /home/i/.kimi/plugins/telegram-bridge add src/kimi_runner.py tests/test_kimi_runner.py
git -C /home/i/.kimi/plugins/telegram-bridge commit -m "$(cat <<'EOF'
feat(kimi): add stream-json parser and async run_kimi subprocess wrapper

Parser is the single chokepoint that turns kimi's newline-delimited
event stream into reply text — ignores think blocks, unknown event
types, blank lines, and malformed JSON. run_kimi shells out via
subprocess.run wrapped in asyncio.to_thread (no shell injection
since args is a list) with the canonical CLI flag set. Subprocess
tests use shell stubs to assert exit-code propagation and the
exact argv built by the runner.

Co-Authored-By: HH <hh@local>
EOF
)"
```

---

## Task 7: Daemon main loop

**Files:**
- Create: `src/daemon.py`
- Create: `tests/test_daemon.py`

The daemon ties everything together. The main async function `run(...)` accepts injected `TelegramClient`-like and `run_kimi`-like callables so it's straightforwardly testable. The actual top-level entry point reads config, builds real clients, and calls `run(...)` in a loop with signal handling.

Loop sketch:

```
session_for(chat_id):
    if chat_id in state.chats: return state.chats[chat_id]
    new = uuid4().hex
    state.chats[chat_id] = new
    save_state(state_path, state)
    return new

while not stop_event.is_set():
    updates = await tg.get_updates(offset=state.last_update_id + 1, timeout=30)
    for upd in updates:
        state.last_update_id = max(state.last_update_id, upd["update_id"])
        msg = parse_update(upd)
        if msg is None: continue
        if not is_authorized(msg, cfg.telegram): continue
        await tg.send_chat_action(msg.chat_id, "typing")
        sid = session_for(msg.chat_id)
        result = await run_kimi(msg.text, session_id=sid, ...)
        reply = result.text or "(empty reply)" if result.exit_code == 0 \
                else f"⚠️ kimi error: {result.stderr[:500]}"
        await tg.send_message(msg.chat_id, reply)
    save_state(state_path, state)
```

`run` is the unit-testable surface; `main()` uses `asyncio.run` and signal handlers to call it.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_daemon.py
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
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
.venv/bin/pytest tests/test_daemon.py -v
```
Expected: `ModuleNotFoundError: No module named 'src.daemon'`.

- [ ] **Step 3: Implement `src/daemon.py`**

```python
"""Long-running daemon: poll Telegram, route through kimi, reply."""
from __future__ import annotations

import asyncio
import logging
import os
import signal
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

                result = await run_kimi_func(
                    prompt=msg.text,
                    session_id=sid,
                    workdir=cfg.kimi.default_workdir,
                    model=cfg.kimi.model,
                    agent=cfg.kimi.agent,
                    kimi_path=kimi_path,
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
    cfg_path = Path(os.environ.get("KIMI_BRIDGE_CONFIG") or DEFAULT_CONFIG_PATH)
    state_path = Path(os.environ.get("KIMI_BRIDGE_STATE") or DEFAULT_STATE_PATH)
    cfg = load_config(cfg_path)

    stop_event = asyncio.Event()

    async def _run() -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop_event.set)
        async with TelegramClient(cfg.telegram.bot_token) as tg:
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
```

**Note on double `__aenter__`:** the `_run()` wrapper enters the `TelegramClient` context, then `run()` calls `async with tg` again. The fake telegram in tests handles re-entry; the real `TelegramClient.__aenter__` would replace the inner client. To avoid double-entry, `run()` enters the context but `_run()` simply passes the **un-entered** client. Drop `async with TelegramClient(...) as tg` from `_run()` and instead pass the constructed instance:

Replace the body of `_run()` with:

```python
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
```

So `run()` owns the lifecycle.

- [ ] **Step 4: Run tests, confirm they pass**

```bash
.venv/bin/pytest tests/test_daemon.py -v
```
Expected: `4 passed`. If a test flakes on timing, raise the `call_later` deadline.

- [ ] **Step 5: Run the entire suite**

```bash
.venv/bin/pytest -v
```
Expected: full suite from Tasks 1–7 passes.

- [ ] **Step 6: Commit**

```bash
git -C /home/i/.kimi/plugins/telegram-bridge add src/daemon.py tests/test_daemon.py
git -C /home/i/.kimi/plugins/telegram-bridge commit -m "$(cat <<'EOF'
feat(daemon): add main loop wiring telegram, kimi runner, and state

run() is the test-friendly orchestration surface — accepts injected
TelegramClient-like and run_kimi callables, plus a stop_event so
tests can drive a bounded number of iterations. main() is the
production entry point that constructs the real httpx client and
installs SIGTERM/SIGINT handlers. Each chat gets a stable kimi
session id persisted in ~/.kimi/bridge/state.json so multi-turn
conversations resume.

Co-Authored-By: HH <hh@local>
EOF
)"
```

---

## Task 8: Plugin façade — plugin.json + control CLI

**Files:**
- Create: `plugin.json`
- Create: `src/control.py`
- Create: `tests/test_control.py`

The Kimi plugin runtime spawns the control CLI as a subprocess with the tool's parameters as JSON on stdin and reads JSON from stdout. We TDD `control.py` with `subprocess.run` mocked so we can assert the exact systemctl arguments passed.

`control.py` accepts `{"action": "start|stop|status|logs|setup", "lines": int?}` on stdin, prints a JSON `{"output": str, "ok": bool}` to stdout, and exits 0.

- `start` → `systemctl --user start kimi-telegram-bridge.service`.
- `stop` → `systemctl --user stop kimi-telegram-bridge.service`.
- `status` → `systemctl --user status kimi-telegram-bridge.service` (let systemd format).
- `logs` → tail `~/.kimi/bridge/logs/bridge.log` (last `lines`, default 50). Falls back to `journalctl --user -u kimi-telegram-bridge.service -n N` if the log file is absent.
- `setup` → validate config via `load_config`, run `kimi --version`, GET `https://api.telegram.org/bot<token>/getMe` to verify the token. Returns a multi-line report.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_control.py
"""Tests for src.control — plugin tool entry point."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.control import handle


def _run_handle(action: str, **extra: object) -> dict:
    payload = {"action": action, **extra}
    return handle(payload)


def test_start_invokes_systemctl_start(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="active\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = _run_handle("start")
    assert result["ok"] is True
    assert any("start" in c and "kimi-telegram-bridge.service" in c for c in calls)


def test_stop_invokes_systemctl_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = _run_handle("stop")
    assert result["ok"] is True
    assert any("stop" in c and "kimi-telegram-bridge.service" in c for c in calls)


def test_status_returns_systemctl_output(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            cmd, 0, stdout="Active: active (running)\n", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = _run_handle("status")
    assert "Active: active (running)" in result["output"]


def test_logs_tails_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log_file = tmp_path / "bridge.log"
    log_file.write_text("\n".join(f"line {i}" for i in range(100)) + "\n")
    monkeypatch.setattr("src.control.LOG_FILE", log_file)
    result = _run_handle("logs", lines=5)
    assert result["ok"] is True
    out_lines = result["output"].splitlines()
    assert len(out_lines) == 5
    assert out_lines[-1] == "line 99"


def test_logs_fallback_to_journalctl_when_file_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("src.control.LOG_FILE", tmp_path / "missing.log")
    captured: list[list[str]] = []

    def fake_run(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        captured.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="from journal\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = _run_handle("logs", lines=10)
    assert "from journal" in result["output"]
    assert any("journalctl" in c[0] for c in captured)


def test_unknown_action_returns_error() -> None:
    result = _run_handle("nuke")
    assert result["ok"] is False
    assert "unknown action" in result["output"].lower()
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
.venv/bin/pytest tests/test_control.py -v
```
Expected: `ModuleNotFoundError: No module named 'src.control'`.

- [ ] **Step 3: Implement `src/control.py`**

```python
"""Plugin-tool entry point: start | stop | status | logs | setup."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


SERVICE = "kimi-telegram-bridge.service"
LOG_FILE = Path.home() / ".kimi" / "bridge" / "logs" / "bridge.log"


def _systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["systemctl", "--user", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _action_start() -> dict[str, Any]:
    res = _systemctl("start", SERVICE)
    ok = res.returncode == 0
    return {
        "ok": ok,
        "output": (res.stdout + res.stderr).strip() or ("started" if ok else "failed"),
    }


def _action_stop() -> dict[str, Any]:
    res = _systemctl("stop", SERVICE)
    return {
        "ok": res.returncode == 0,
        "output": (res.stdout + res.stderr).strip() or "stopped",
    }


def _action_status() -> dict[str, Any]:
    res = _systemctl("status", SERVICE, "--no-pager")
    # systemctl status exits 3 when service is inactive; that's still useful info.
    return {
        "ok": res.returncode in (0, 3),
        "output": (res.stdout + res.stderr).strip(),
    }


def _action_logs(lines: int = 50) -> dict[str, Any]:
    if LOG_FILE.exists():
        text = LOG_FILE.read_text(errors="replace").splitlines()
        return {"ok": True, "output": "\n".join(text[-lines:])}
    res = subprocess.run(
        ["journalctl", "--user", "-u", SERVICE, "-n", str(lines), "--no-pager"],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "ok": res.returncode == 0,
        "output": res.stdout.strip() or res.stderr.strip(),
    }


def _action_setup() -> dict[str, Any]:
    """Validate config + tools. Returns a human-readable report."""
    try:
        from src.config import load_config
    except Exception as err:
        return {"ok": False, "output": f"could not import config loader: {err}"}

    cfg_path = Path(__file__).resolve().parent.parent / "config.json"
    report: list[str] = [f"config path: {cfg_path}"]

    try:
        cfg = load_config(cfg_path)
        report.append("✓ config.json loaded")
    except Exception as err:
        return {"ok": False, "output": "\n".join([*report, f"✗ config error: {err}"])}

    kimi = subprocess.run(
        ["kimi", "--version"], capture_output=True, text=True, check=False
    )
    if kimi.returncode == 0:
        report.append(f"✓ kimi CLI found: {kimi.stdout.strip()}")
    else:
        report.append(f"✗ kimi --version failed: {kimi.stderr.strip()}")

    try:
        import httpx

        r = httpx.get(
            f"https://api.telegram.org/bot{cfg.telegram.bot_token}/getMe",
            timeout=10,
        )
        data = r.json()
        if data.get("ok"):
            user = data["result"]
            report.append(f"✓ telegram token valid (bot @{user.get('username')})")
        else:
            report.append(f"✗ telegram token rejected: {data.get('description')}")
    except Exception as err:
        report.append(f"✗ telegram check failed: {err}")

    ok = not any(line.startswith("✗") for line in report)
    return {"ok": ok, "output": "\n".join(report)}


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action")
    if action == "start":
        return _action_start()
    if action == "stop":
        return _action_stop()
    if action == "status":
        return _action_status()
    if action == "logs":
        return _action_logs(int(payload.get("lines") or 50))
    if action == "setup":
        return _action_setup()
    return {"ok": False, "output": f"unknown action: {action!r}"}


def main() -> None:  # pragma: no cover — IO wiring only
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as err:
        print(json.dumps({"ok": False, "output": f"invalid JSON on stdin: {err}"}))
        sys.exit(1)
    print(json.dumps(handle(payload)))


if __name__ == "__main__":  # pragma: no cover
    main()
```

- [ ] **Step 4: Write `plugin.json`**

```json
{
  "name": "telegram-bridge",
  "version": "0.1.0",
  "description": "Bridge Telegram chats to Kimi sessions (long-running daemon controlled via this tool).",
  "config_file": "config.json",
  "tools": [
    {
      "name": "bridge",
      "description": "Control the kimi telegram bridge daemon (start/stop/status/logs/setup).",
      "command": [".venv/bin/python", "-m", "src.control"],
      "parameters": {
        "type": "object",
        "properties": {
          "action": {
            "type": "string",
            "enum": ["start", "stop", "status", "logs", "setup"],
            "description": "What to do with the daemon."
          },
          "lines": {
            "type": "integer",
            "default": 50,
            "description": "Number of log lines to tail (only used for action=logs)."
          }
        },
        "required": ["action"]
      }
    }
  ]
}
```

- [ ] **Step 5: Run tests, confirm they pass**

```bash
.venv/bin/pytest tests/test_control.py -v
```
Expected: `6 passed`.

- [ ] **Step 6: Commit**

```bash
git -C /home/i/.kimi/plugins/telegram-bridge add plugin.json src/control.py tests/test_control.py
git -C /home/i/.kimi/plugins/telegram-bridge commit -m "$(cat <<'EOF'
feat(plugin): add Kimi plugin manifest and control CLI

plugin.json declares one tool, "bridge", whose subcommands
(start/stop/status/logs/setup) are dispatched by src/control.py.
The control CLI shells out to systemctl --user for daemon
lifecycle, tails ~/.kimi/bridge/logs/bridge.log (with journalctl
fallback) for logs, and validates config + kimi CLI + telegram
token in setup. Tests cover each action with subprocess mocked.

Co-Authored-By: HH <hh@local>
EOF
)"
```

---

## Task 9: Installer, systemd unit, example config, README

**Files:**
- Create: `systemd/kimi-telegram-bridge.service.template`
- Create: `install.sh`
- Create: `config.example.json`
- Modify: `README.md`

This task has no unit tests — it's installer plumbing. Verified end-to-end in the manual smoke checklist below.

- [ ] **Step 1: Write the systemd unit template**

Create `systemd/kimi-telegram-bridge.service.template`. The installer substitutes `__HOME__` and `__VENV_PYTHON__`.

```ini
[Unit]
Description=Kimi Telegram Bridge
Documentation=https://github.com/.../telegram-bridge
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=__HOME__/.kimi/plugins/telegram-bridge
ExecStart=__VENV_PYTHON__ -m src.daemon
Environment=PYTHONUNBUFFERED=1
Environment=PATH=__HOME__/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
Restart=on-failure
RestartSec=5s
StandardOutput=append:__HOME__/.kimi/bridge/logs/bridge.log
StandardError=append:__HOME__/.kimi/bridge/logs/bridge.log

[Install]
WantedBy=default.target
```

- [ ] **Step 2: Write `install.sh`**

```bash
#!/usr/bin/env bash
# Install the kimi telegram bridge as a systemd --user service.
# Idempotent: safe to re-run.
set -euo pipefail

PLUGIN_DIR="${HOME}/.kimi/plugins/telegram-bridge"
RUNTIME_DIR="${HOME}/.kimi/bridge"
LOG_DIR="${RUNTIME_DIR}/logs"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
SERVICE_TEMPLATE="${PLUGIN_DIR}/systemd/kimi-telegram-bridge.service.template"
SERVICE_TARGET="${SYSTEMD_USER_DIR}/kimi-telegram-bridge.service"

if [[ "$(realpath "${PWD}")" != "$(realpath "${PLUGIN_DIR}")" ]]; then
    echo "Run this from ${PLUGIN_DIR}" >&2
    exit 2
fi

echo "==> Creating runtime directories"
mkdir -p "${LOG_DIR}" "${RUNTIME_DIR}/runtime" "${SYSTEMD_USER_DIR}"

echo "==> Building Python venv"
if ! command -v uv >/dev/null 2>&1; then
    echo "uv is required (https://github.com/astral-sh/uv)" >&2
    exit 3
fi
uv venv .venv --python 3.11
.venv/bin/pip install --quiet -e .

VENV_PYTHON="${PLUGIN_DIR}/.venv/bin/python"

echo "==> Rendering systemd unit -> ${SERVICE_TARGET}"
sed \
    -e "s|__HOME__|${HOME}|g" \
    -e "s|__VENV_PYTHON__|${VENV_PYTHON}|g" \
    "${SERVICE_TEMPLATE}" > "${SERVICE_TARGET}"

echo "==> Reloading systemd --user and enabling unit"
systemctl --user daemon-reload
systemctl --user enable kimi-telegram-bridge.service

if [[ ! -f "${PLUGIN_DIR}/config.json" ]]; then
    cat <<EOF

==> Next steps:
  1. Copy and edit the config:
       cp ${PLUGIN_DIR}/config.example.json ${PLUGIN_DIR}/config.json
       \$EDITOR ${PLUGIN_DIR}/config.json

  2. Start the bridge:
       systemctl --user start kimi-telegram-bridge.service

  3. Or, from inside Kimi:
       kimi -p "use the bridge tool to start"

EOF
else
    echo "==> Existing config.json detected. Start with:"
    echo "    systemctl --user start kimi-telegram-bridge.service"
fi
```

Make it executable:

```bash
chmod +x install.sh
```

- [ ] **Step 3: Write `config.example.json`**

```json
{
  "telegram": {
    "bot_token": "REPLACE_WITH_BOT_TOKEN_FROM_BOTFATHER",
    "allowed_user_ids": [123456789],
    "allowed_chat_ids": []
  },
  "kimi": {
    "default_workdir": "/home/YOUR_USER",
    "model": "",
    "agent": "default"
  }
}
```

- [ ] **Step 4: Update `README.md`**

```markdown
# kimi-to-im

Telegram bridge for the [Kimi CLI](https://github.com/MoonshotAI/kimi-cli) — chat with Kimi from Telegram.

Architecture: a Python daemon polls Telegram, spawns `kimi --print --output-format stream-json -S <session>` per inbound message, and replies. The daemon is supervised by `systemctl --user`. A Kimi plugin manifest exposes the daemon's lifecycle (start/stop/status/logs/setup) as a callable tool inside Kimi sessions.

See [`docs/design.md`](docs/design.md) for the architecture spec.

## Install

```sh
cd ~/.kimi/plugins/telegram-bridge
bash install.sh
cp config.example.json config.json
$EDITOR config.json   # set telegram.bot_token and telegram.allowed_user_ids
systemctl --user start kimi-telegram-bridge.service
```

## Usage from inside Kimi

```sh
kimi -p "use the bridge tool with action=status"
kimi -p "use the bridge tool with action=logs and lines=100"
kimi -p "use the bridge tool with action=setup"
```

## Configuration

Edit `config.json`. The minimum:

| Field | Required? | Notes |
|---|---|---|
| `telegram.bot_token` | yes | from `@BotFather` |
| `telegram.allowed_user_ids` | yes | non-empty (default-deny) |
| `telegram.allowed_chat_ids` | optional | empty = allow any chat from an allowed user |
| `kimi.default_workdir` | optional | working dir kimi runs in |
| `kimi.model` | optional | empty = kimi's default |
| `kimi.agent` | optional | defaults to `default` |

`config.json` is gitignored — never commit your bot token.

## Operating

- **Start**: `systemctl --user start kimi-telegram-bridge.service`
- **Stop**: `systemctl --user stop kimi-telegram-bridge.service`
- **Status**: `systemctl --user status kimi-telegram-bridge.service`
- **Logs**: `tail -f ~/.kimi/bridge/logs/bridge.log` (or `journalctl --user -u kimi-telegram-bridge.service -f`)

The daemon keeps a `chat_id → kimi session_id` map at `~/.kimi/bridge/state.json` so each Telegram chat resumes the same Kimi session across messages.

## Development

```sh
uv venv .venv --python 3.11
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -v
```
```

- [ ] **Step 5: Verify tests still pass and commit**

```bash
.venv/bin/pytest -v
```
Expected: full suite (smoke + config + state + telegram_pure + telegram_http + kimi_runner + daemon + control) passes.

```bash
git -C /home/i/.kimi/plugins/telegram-bridge add install.sh systemd/kimi-telegram-bridge.service.template config.example.json README.md
git -C /home/i/.kimi/plugins/telegram-bridge commit -m "$(cat <<'EOF'
feat(install): add install.sh, systemd user unit, example config, README

install.sh is idempotent: builds the venv, renders the unit
template with the user's HOME and venv-python paths, and enables
the service. config.example.json is the safe-to-commit template;
the real config.json is gitignored. README documents install,
plugin-tool usage from inside kimi, configuration knobs, and the
ops commands.

Co-Authored-By: HH <hh@local>
EOF
)"
```

---

## Manual end-to-end smoke (post-implementation)

These cannot be unit-tested. Run after Task 9 commits.

- [ ] **1. Install runs cleanly**

```bash
cd /home/i/.kimi/plugins/telegram-bridge && bash install.sh
```
Expect: venv created, deps installed, systemd unit installed and enabled. No errors.

- [ ] **2. Config validation works**

```bash
cp config.example.json config.json
# Edit config.json with a real bot token and your Telegram user_id.
.venv/bin/python -c "import json; from src.control import handle; print(json.dumps(handle({'action': 'setup'}), indent=2))"
```
Expect: report with ✓ for config / kimi / telegram; `ok: true`.

- [ ] **3. Daemon starts**

```bash
systemctl --user start kimi-telegram-bridge.service
systemctl --user is-active kimi-telegram-bridge.service
```
Expect: `active`.

- [ ] **4. Send a Telegram message from the allowed account**

Reach the bot from your phone, send "hello kimi". Within ~10s expect:
- typing indicator appears
- a reply lands in the chat (the actual Kimi response)
- `~/.kimi/bridge/logs/bridge.log` shows the message handled

- [ ] **5. Multi-turn session continuity**

Send a follow-up. The reply should reference the prior message (proving session resume). Verify:

```bash
cat ~/.kimi/bridge/state.json
ls ~/.kimi/sessions/
```
Expect: the chat's session_id appears in state.json and as a directory under `~/.kimi/sessions/`.

- [ ] **6. Authorization rejects strangers**

From a different (non-allowed) Telegram account, message the bot. Expect: no reply; `bridge.log` shows "dropping unauthorized message".

- [ ] **7. Plugin façade works from inside Kimi**

```bash
kimi -p "use the bridge tool with action=status"
```
Expect: Kimi calls the tool, response includes `Active: active (running)`.

- [ ] **8. claude-to-im keeps working in parallel**

```bash
bash ~/.claude/skills/claude-to-im/scripts/daemon.sh status
```
Expect: still running, no port/pid conflict with kimi-to-im.

- [ ] **9. Stop cleanly**

```bash
systemctl --user stop kimi-telegram-bridge.service
```
Expect: stops within seconds; sending another Telegram message produces no reply.

---

## Self-review notes

**Spec coverage:**
- Layer 1 plugin façade → Task 8 (`plugin.json` + `src/control.py`).
- Layer 2 daemon → Task 7 (`src/daemon.py`).
- Inbound message loop (steps 1–8 in spec) → all covered in Task 7's `run()`.
- File layout → matches spec exactly. Runtime data lives at `~/.kimi/bridge/`, code at `~/.kimi/plugins/telegram-bridge/`.
- Config schema → Task 2 + spec Telegram/Kimi sections; defaults match.
- Install flow (uv venv + systemd) → Task 9.
- "What's NOT in v1" — no Discord/Feishu/QQ, no streaming preview, no permission UI, no image input — none introduced; respected.

**Type consistency check:**
- `Config`, `TelegramConfig`, `KimiConfig` shapes match across config.py, daemon.py, control.py imports.
- `InboundMessage` defined once in telegram.py, consumed by daemon.py.
- `KimiResult` defined in kimi_runner.py, consumed by daemon.py.
- `State` defined in state.py, mutated only by daemon.py.

**Placeholder scan:** No TBDs / TODOs / "implement later" / "similar to". All steps contain runnable code or exact commands.

**Open implementation-time verification:** the parser in Task 6 expects events with `type: "assistant"`. If real kimi v1.39.0 emits a different envelope, the parser tests still pass (they use hand-crafted fixtures) but smoke step 4 will return `(empty reply)`. Mitigation: in step 4, if reply is empty, run `echo "say hi" | kimi --print --output-format stream-json --quiet` manually, inspect the JSON, and adjust `parse_stream_json`'s recognised event types accordingly.
