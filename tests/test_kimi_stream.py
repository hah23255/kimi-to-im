"""Unit tests for src.kimi_stream — event classifier, tool descriptions."""
from __future__ import annotations

from src.kimi_stream import (
    StreamEvent,
    StreamResult,
    _classify_event,
    _tool_desc,
    _build_args,
)


# ── _classify_event ──────────────────────────────────────────────

def test_classify_assistant_string() -> None:
    evt = _classify_event({"role": "assistant", "content": "Hello"})
    assert evt is not None
    assert evt.kind == "text"
    assert evt.data == "Hello"


def test_classify_assistant_content_blocks() -> None:
    evt = _classify_event({
        "role": "assistant",
        "content": [{"type": "text", "text": "Hello from block"}]
    })
    assert evt is not None
    assert evt.kind == "text"
    assert "Hello from block" in evt.data


def test_classify_thinking() -> None:
    evt = _classify_event({"type": "thinking", "thinking": "reasoning"})
    assert evt is not None
    assert evt.kind == "thinking"
    assert evt.data == "reasoning"


def test_classify_thinking_in_content_block() -> None:
    evt = _classify_event({
        "role": "assistant",
        "content": [{"type": "thinking", "thinking": "deep thought"}]
    })
    assert evt is not None
    assert evt.kind == "thinking"


def test_classify_tool_use_in_block() -> None:
    evt = _classify_event({
        "role": "assistant",
        "content": [{"type": "tool_use", "name": "read",
                      "input": {"path": "foo.py"}}]
    })
    assert evt is not None
    assert evt.kind == "tool_call"
    assert evt.tool_name == "read"


def test_classify_metadata() -> None:
    evt = _classify_event({"type": "model", "model": "kimi-for-coding"})
    assert evt is not None
    assert evt.kind == "metadata"


def test_classify_unknown_returns_none() -> None:
    assert _classify_event({"role": "system", "content": "..."}) is None


def test_classify_non_dict() -> None:
    assert _classify_event("not a dict") is None  # type: ignore[arg-type]
    assert _classify_event(42) is None  # type: ignore[arg-type]


def test_classify_empty_content_list() -> None:
    evt = _classify_event({"role": "assistant", "content": []})
    assert evt is None


# ── _tool_desc ───────────────────────────────────────────────────

def test_tool_desc_read() -> None:
    assert "📖" in _tool_desc("read", {"path": "foo.py"})


def test_tool_desc_exec() -> None:
    assert "⚡" in _tool_desc("exec", {"command": "ls -la"})


def test_tool_desc_unknown_fallback() -> None:
    desc = _tool_desc("unknown_tool", {"x": 1})
    assert "🔨" in desc
    assert "unknown_tool" in desc


def test_tool_desc_keyerror_fallback() -> None:
    desc = _tool_desc("read", {})  # missing 'path' key
    assert "🔨" in desc


def test_tool_desc_web_fetch() -> None:
    assert "🌐" in _tool_desc("web_fetch", {"url": "https://example.com"})


def test_tool_desc_grep() -> None:
    assert "🔍" in _tool_desc("grep", {"pattern": "TODO"})


# ── StreamEvent / StreamResult ───────────────────────────────────

def test_stream_event_defaults() -> None:
    e = StreamEvent(kind="text", data="x")
    assert e.tool_name == ""
    assert e.timestamp == 0.0


def test_stream_result_defaults() -> None:
    r = StreamResult(text="", exit_code=0, stderr="")
    assert r.events == []
    assert r.total_thinking_chars == 0
    assert r.total_tool_calls == 0


# ── _build_args ──────────────────────────────────────────────────

def test_build_args_no_model() -> None:
    args = _build_args("kimi", "sid1", "/tmp", "", "default")
    assert args[0] == "kimi"
    assert "--print" in args
    assert "-S" in args and "sid1" in args
    assert "--model" not in args


def test_build_args_with_model() -> None:
    args = _build_args("kimi", "sid1", "/tmp", "kimi-for-coding", "default")
    assert "--model" in args
    assert "kimi-for-coding" in args
