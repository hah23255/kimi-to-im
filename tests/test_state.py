"""Tests for src.state — atomic JSON state file."""
from __future__ import annotations

from pathlib import Path

from src.state import State, _SESSION_ID_RE, load_state, save_state


def test_load_missing_file_returns_zero_state(tmp_path: Path) -> None:
    s = load_state(tmp_path / "state.json")
    assert s.last_update_id == 0
    assert s.chats == {}


def test_save_then_load_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    sid_a = "0123456789abcdef0123456789abcdef"
    sid_b = "fedcba9876543210fedcba9876543210"
    original = State(last_update_id=42, chats={123: sid_a, 456: sid_b})
    save_state(p, original)

    loaded = load_state(p)
    assert loaded.last_update_id == 42
    assert loaded.chats == {123: sid_a, 456: sid_b}


def test_save_creates_parent_dir(tmp_path: Path) -> None:
    p = tmp_path / "nested" / "dirs" / "state.json"
    save_state(p, State(last_update_id=1, chats={}))
    assert p.exists()


def test_save_is_atomic_no_tmp_left_behind(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    save_state(
        p, State(last_update_id=1, chats={1: "0123456789abcdef0123456789abcdef"})
    )
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
    sid = "0123456789abcdef0123456789abcdef"
    save_state(p, State(last_update_id=5, chats={123: sid}))
    loaded = load_state(p)
    assert all(isinstance(k, int) for k in loaded.chats)


def test_load_state_drops_malformed_session_ids(tmp_path: Path) -> None:
    """A tampered state.json with non-uuid4 session values should be silently
    dropped — defends the kimi subprocess against argv-flag injection."""
    p = tmp_path / "state.json"
    p.write_text(
        '{"last_update_id": 5, "chats": {'
        '"123": "abc-not-uuid",'
        '"456": "--evil-flag",'
        '"789": "0123456789abcdef0123456789abcdef"'
        '}}'
    )
    state = load_state(p)
    assert state.last_update_id == 5
    # Only the well-formed entry survives.
    assert state.chats == {789: "0123456789abcdef0123456789abcdef"}


def test_session_id_regex_matches_uuid4_hex_only() -> None:
    assert _SESSION_ID_RE.match("d6a7ee18380d444b8d48b1edf66951bb")
    assert not _SESSION_ID_RE.match("d6a7ee18380d444b8d48b1edf66951bbX")  # too long
    assert not _SESSION_ID_RE.match("d6a7ee18380d444b8d48b1edf66951b")    # too short
    assert not _SESSION_ID_RE.match("D6A7EE18380D444B8D48B1EDF66951BB")   # uppercase
    assert not _SESSION_ID_RE.match("--evil-flag-injection-attempt-x32")  # special chars
