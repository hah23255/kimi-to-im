"""Atomic JSON-backed bridge state at ~/.kimi/bridge/state.json."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

# Session ids are uuid4().hex — exactly 32 lowercase hex characters.
# Loader discards any value that doesn't match, defending against a tampered
# state.json injecting flags into the kimi argv (e.g. "--evil") on next spawn.
_SESSION_ID_RE = re.compile(r"^[0-9a-f]{32}$")

# Model name allows alphanumeric, /, -, _, . (e.g. "kimi-code/kimi-for-coding")
_MODEL_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9/_\-.]{0,127}$")


@dataclass
class State:
    last_update_id: int = 0
    chats: dict[int, str] = field(default_factory=dict)
    # Per-chat preferences (Phase 2)
    thinking_enabled: dict[int, bool] = field(default_factory=dict)
    model_overrides: dict[int, str] = field(default_factory=dict)


def load_state(path: Path) -> State:
    if not path.exists():
        return State()
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError:
        return State()
    chats_raw = raw.get("chats") or {}
    thinking_raw = raw.get("thinking_enabled") or {}
    models_raw = raw.get("model_overrides") or {}
    return State(
        last_update_id=int(raw.get("last_update_id", 0)),
        chats={
            int(k): str(v)
            for k, v in chats_raw.items()
            if isinstance(v, str) and _SESSION_ID_RE.match(v)
        },
        thinking_enabled={
            int(k): bool(v)
            for k, v in thinking_raw.items()
            if isinstance(k, (int, str))
        },
        model_overrides={
            int(k): str(v)
            for k, v in models_raw.items()
            if isinstance(v, str) and _MODEL_RE.match(v)
        },
    )


def save_state(path: Path, state: State) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload: dict = {
        "last_update_id": state.last_update_id,
        "chats": {str(k): v for k, v in state.chats.items()},
    }
    if state.thinking_enabled:
        payload["thinking_enabled"] = {str(k): v for k, v in state.thinking_enabled.items()}
    if state.model_overrides:
        payload["model_overrides"] = {str(k): v for k, v in state.model_overrides.items()}
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, path)
