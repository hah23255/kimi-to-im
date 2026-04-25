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
