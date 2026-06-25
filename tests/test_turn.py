"""Unit tests for src.turn — session management."""
from __future__ import annotations

import re

from src.state import State
from src.turn import get_or_create_session


def test_get_or_create_new_session() -> None:
    s = State()
    sid = get_or_create_session(s, 42)
    assert len(sid) == 32
    assert re.match(r"^[0-9a-f]{32}$", sid)


def test_get_or_create_existing_session() -> None:
    s = State()
    sid1 = get_or_create_session(s, 42)
    sid2 = get_or_create_session(s, 42)
    assert sid1 == sid2


def test_get_or_create_different_chats() -> None:
    s = State()
    a = get_or_create_session(s, 1)
    b = get_or_create_session(s, 2)
    assert a != b


def test_session_format_is_hex() -> None:
    s = State()
    sid = get_or_create_session(s, 99)
    assert all(c in "0123456789abcdef" for c in sid)
