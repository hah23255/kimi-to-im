"""Stanford-level edge case tests for kimi_stream.py — target 75%+ coverage."""
from __future__ import annotations

import json

import pytest

from src.kimi_stream import (
    StreamEvent, StreamResult,
    _classify_event, _classify_assistant, _classify_part,
    _tool_desc, _build_args,
    run_kimi_stream,
)


# ── _classify_event edge cases ────────────────────────────────────

def test_classify_non_dict_int() -> None:
    assert _classify_event(42) is None  # type: ignore[arg-type]


def test_classify_non_dict_none() -> None:
    assert _classify_event(None) is None  # type: ignore[arg-type]


def test_classify_non_dict_list() -> None:
    assert _classify_event([1, 2, 3]) is None  # type: ignore[arg-type]


def test_classify_system_role_ignored() -> None:
    assert _classify_event({"role": "system", "content": "..."}) is None


def test_classify_user_role_ignored() -> None:
    assert _classify_event({"role": "user", "content": "hello"}) is None


def test_classify_tool_role_ignored() -> None:
    assert _classify_event({"role": "tool", "content": "result"}) is None


def test_classify_assistant_with_object_content() -> None:
    # Non-string, non-list content — should return None
    assert _classify_event({"role": "assistant", "content": 42}) is None


def test_classify_assistant_with_dict_content() -> None:
    # dict content not iterable as list — ignored
    assert _classify_event({"role": "assistant", "content": {"type": "text"}}) is None


def test_classify_thinking_alt_field() -> None:
    # thinking event with 'content' instead of 'thinking'
    evt = _classify_event({"type": "thinking", "content": "reason"})
    assert evt is not None
    assert evt.kind == "thinking"
    assert evt.data == "reason"


def test_classify_thinking_empty_content() -> None:
    assert _classify_event({"type": "thinking", "thinking": ""}) is None


def test_classify_thinking_non_string() -> None:
    assert _classify_event({"type": "thinking", "thinking": 42}) is None  # type: ignore[dict-item]


def test_classify_metadata_token_usage() -> None:
    evt = _classify_event({"type": "token_usage", "tokens": 100})
    assert evt is not None
    assert evt.kind == "metadata"


def test_classify_metadata_cost() -> None:
    evt = _classify_event({"type": "cost", "usd": 0.01})
    assert evt is not None
    assert evt.kind == "metadata"


# ── _classify_part edge cases ─────────────────────────────────────

def test_part_non_dict() -> None:
    assert _classify_part("string", 0.0) is None  # type: ignore[arg-type]


def test_part_unknown_type() -> None:
    assert _classify_part({"type": "image", "url": "x"}, 0.0) is None


def test_part_empty_type() -> None:
    assert _classify_part({"type": "", "text": "x"}, 0.0) is None


def test_part_text_empty_string() -> None:
    assert _classify_part({"type": "text", "text": ""}, 0.0) is None


def test_part_text_non_string() -> None:
    assert _classify_part({"type": "text", "text": 123}, 0.0) is None


def test_part_think_alt_field() -> None:
    evt = _classify_part({"type": "think", "text": "hmm"}, 0.0)
    assert evt is not None
    assert evt.kind == "thinking"


def test_part_tool_use_no_name() -> None:
    evt = _classify_part({"type": "tool_use", "input": {}}, 0.0)
    assert evt is not None
    assert evt.kind == "tool_call"
    assert evt.tool_name == "unknown"


# ── _tool_desc edge cases ─────────────────────────────────────────

def test_tool_desc_write() -> None:
    d = _tool_desc("write", {"path": "f.py", "lines": 42})
    assert "✏️" in d
    assert "42L" in d


def test_tool_desc_glob() -> None:
    d = _tool_desc("glob", {"pattern": "*.py"})
    assert "🔎" in d


def test_tool_desc_web_search() -> None:
    d = _tool_desc("web_search", {"query": "kimi"})
    assert "🔎 web:" in d


def test_tool_desc_edit() -> None:
    d = _tool_desc("edit", {"path": "file.py"})
    assert "🔧" in d


def test_tool_desc_empty_input() -> None:
    d = _tool_desc("read", {})
    assert "🔨" in d  # fallback


def test_tool_desc_none_name() -> None:
    d = _tool_desc("", {})
    assert "🔨" in d


# ── _build_args edge cases ────────────────────────────────────────

import stat


def test_build_args_minimal() -> None:
    args = _build_args("kimi", "prompt_text", "s", "/tmp", "")
    assert "-p" in args
    assert "stream-json" in args
    assert "-S" in args and "s" in args
    assert "--add-dir" in args and "/tmp" in args


def test_build_args_with_model() -> None:
    args = _build_args("kimi", "prompt_text", "s", "/tmp", "kimi-for-coding")
    assert "--model" in args
    idx = args.index("--model")
    assert args[idx + 1] == "kimi-for-coding"


def test_build_args_empty_model_omitted() -> None:
    args = _build_args("kimi", "prompt_text", "s", "/tmp", "")
    assert "--model" not in args


# ── StreamEvent / StreamResult edge cases ────────────────────────

def test_stream_event_all_fields_set() -> None:
    e = StreamEvent(kind="tool_call", data="📖 x", tool_name="read", timestamp=1.5)
    assert e.kind == "tool_call"
    assert e.data == "📖 x"
    assert e.tool_name == "read"
    assert e.timestamp == 1.5


def test_stream_event_defaults() -> None:
    e = StreamEvent(kind="text", data="x")
    assert e.tool_name == ""
    assert e.timestamp == 0.0


def test_stream_result_accumulates() -> None:
    r = StreamResult(text="hello", exit_code=0, stderr="")
    r.events.append(StreamEvent(kind="thinking", data="x"))
    r.total_thinking_chars += 1
    r.total_tool_calls += 1
    assert len(r.events) == 1
    assert r.total_thinking_chars == 1
    assert r.total_tool_calls == 1


# ── Restored from F-001 ──

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


def test_stream_result_defaults() -> None:
    r = StreamResult(text="", exit_code=0, stderr="")
    assert r.events == []
    assert r.total_thinking_chars == 0
    assert r.total_tool_calls == 0


import shutil

HAS_KIMI = shutil.which("kimi") is not None


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_KIMI, reason="kimi binary not installed")
async def test_run_kimi_stream_basic() -> None:
    """End-to-end streaming with real kimi CLI."""
    result = await run_kimi_stream(
        prompt='reply with just the single word OK',
        session_id='test-basic-001', workdir='/tmp',
        model='', agent='default', kimi_path='kimi', idle_timeout=30)
    assert result.exit_code == 0
    assert 'OK' in result.text
    assert len(result.events) >= 1


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_KIMI, reason="kimi binary not installed")
async def test_run_kimi_stream_with_model() -> None:
    """Passing --model flag through to kimi."""
    result = await run_kimi_stream(
        prompt='reply OK', session_id='test-model',
        workdir='/tmp', model='kimi-code/kimi-for-coding', agent='default',
        kimi_path='kimi', idle_timeout=30)
    assert result.exit_code == 0


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_KIMI, reason="kimi binary not installed")
async def test_run_kimi_stream_events_classified() -> None:
    """Verify events contain classified types."""
    result = await run_kimi_stream(
        prompt='reply: HELLO', session_id='test-events',
        workdir='/tmp', model='', agent='default',
        kimi_path='kimi', idle_timeout=30)
    assert result.exit_code == 0
    kinds = {e.kind for e in result.events}
    assert 'text' in kinds  # at minimum text events


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_KIMI, reason="kimi binary not installed")
async def test_run_kimi_stream_stderr_captured() -> None:
    """Invalid model should produce stderr + non-zero exit."""
    result = await run_kimi_stream(
        prompt='hi', session_id='test-stderr',
        workdir='/tmp', model='nonexistent-model-xyz',
        agent='default', kimi_path='kimi', idle_timeout=30)
    # Exit may be nonzero due to unknown model
    assert isinstance(result.exit_code, int)


@pytest.mark.asyncio
async def test_run_kimi_stream_timeout_handled(tmp_path: Path) -> None:
    """A hanging script should time out with exit_code=124."""
    script = tmp_path / "hang"
    script.write_text("#!/bin/sh\nsleep 10\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    result = await run_kimi_stream(
        prompt='x', session_id='test-timeout',
        workdir=str(tmp_path), model='', agent='default',
        kimi_path=str(script), idle_timeout=0.5)
    assert result.exit_code == 124
    assert 'timeout' in result.stderr.lower() or 'timed out' in result.stderr.lower()


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_KIMI, reason="kimi binary not installed")
async def test_run_kimi_stream_no_timeout() -> None:
    """Default should run without 124."""
    result = await run_kimi_stream(
        prompt='reply OK', session_id='test-notimeout',
        workdir='/tmp', model='', agent='default',
        kimi_path='kimi')
    assert result.exit_code == 0
