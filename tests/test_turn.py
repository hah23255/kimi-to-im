"""Unit tests for src.turn — session management."""
from __future__ import annotations

import re

from src.state import State
from src.turn import get_or_create_session


def test_get_or_create_new_session() -> None:
    s = State()
    sid = get_or_create_session(s, 42)
    assert sid is None


def test_get_or_create_existing_session() -> None:
    s = State()
    s.chats[42] = "a" * 32
    sid1 = get_or_create_session(s, 42)
    sid2 = get_or_create_session(s, 42)
    assert sid1 == "a" * 32
    assert sid1 == sid2


def test_get_or_create_different_chats() -> None:
    s = State()
    s.chats[1] = "a" * 32
    s.chats[2] = "b" * 32
    a = get_or_create_session(s, 1)
    b = get_or_create_session(s, 2)
    assert a != b


def test_session_format_is_hex() -> None:
    s = State()
    s.chats[99] = "c" * 32
    sid = get_or_create_session(s, 99)
    assert sid is not None
    assert all(c in "0123456789abcdef" for c in sid)
