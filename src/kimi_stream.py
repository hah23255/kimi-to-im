"""Streaming kimi subprocess executor — async pipe with event classification."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field


@dataclass
class StreamEvent:
    """One event from kimi streaming JSON output."""
    kind: str  # "text", "thinking", "tool_call", "tool_result", "metadata"
    data: str
    tool_name: str = ""
    timestamp: float = 0.0


@dataclass
class StreamResult:
    """Aggregated streaming run result."""
    text: str
    exit_code: int
    stderr: str
    events: list[StreamEvent] = field(default_factory=list)
    total_thinking_chars: int = 0
    total_tool_calls: int = 0
    session_id_discovered: str = ""  # kimi-code native session ID from session.resume_hint


def _tool_desc(name: str, inp: dict) -> str:
    """Human-readable one-line tool call description."""
    tpl: dict[str, str] = {
        "read": "📖 {path}", "write": "✏️ {path} ({lines}L)",
        "edit": "🔧 {path}", "grep": "🔍 `{pattern}`",
        "glob": "🔎 {pattern}", "web_fetch": "🌐 {url}",
        "web_search": "🔎 web: {query}", "exec": "⚡ `{command}`",
        "bash": "💻 `{command}`", "run_shell": "💻 `{command}`",
    }
    t = tpl.get(name, "🔨 {name}")
    try:
        return t.format(name=name, **(inp or {}))
    except (KeyError, ValueError):
        return f"🔨 {name}"


def _classify_event(raw: dict) -> StreamEvent | None:
    """Classify a raw kimi JSON line into a StreamEvent or None."""
    import time as _t
    ts = _t.monotonic()
    if isinstance(raw, dict) and raw.get("role") == "assistant":
        return _classify_assistant(raw, ts)
    # kimi-code emits this after every turn — capture the native session ID
    if (isinstance(raw, dict) and raw.get("role") == "meta"
            and raw.get("type") == "session.resume_hint"):
        sid = raw.get("session_id", "")
        if isinstance(sid, str) and sid:
            return StreamEvent(kind="session_id", data=sid, timestamp=ts)
    if isinstance(raw, dict) and raw.get("type") == "thinking":
        t = raw.get("thinking") or raw.get("content") or ""
        if isinstance(t, str) and t:
            return StreamEvent(kind="thinking", data=t, timestamp=ts)
    if isinstance(raw, dict) and raw.get("type") in (
        "model", "token_usage", "cost", "metadata"):
        return StreamEvent(kind="metadata", data=json.dumps(raw), timestamp=ts)
    return None


def _classify_assistant(raw: dict, ts: float) -> StreamEvent | None:
    content = raw.get("content")
    if isinstance(content, str):
        return StreamEvent(kind="text", data=content, timestamp=ts)
    if isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                continue
            evt = _classify_part(part, ts)
            if evt:
                return evt
    return None


def _classify_part(part: dict, ts: float) -> StreamEvent | None:
    if not isinstance(part, dict):
        return None
    ptype = part.get("type", "")
    if ptype == "text":
        t = part.get("text", "")
        if isinstance(t, str) and t:
            return StreamEvent(kind="text", data=t, timestamp=ts)
    elif ptype in ("thinking", "think"):
        t = part.get("thinking") or part.get("text", "")
        if isinstance(t, str) and t:
            return StreamEvent(kind="thinking", data=t, timestamp=ts)
    elif ptype == "tool_use":
        name = part.get("name", "unknown")
        return StreamEvent(kind="tool_call", data=_tool_desc(name, part.get("input", {})),
                           tool_name=name, timestamp=ts)
    return None


def _kill_proc(proc: asyncio.subprocess.Process) -> None:
    try:
        proc.terminate()
    except ProcessLookupError:
        return


async def _drain_stdout(
    proc: asyncio.subprocess.Process,
    result: StreamResult,
    idle_timeout: float = 300.0,
    max_timeout: float = 3600.0,
) -> None:
    """Read stdout line-by-line with activity-resetting idle timeout and total max timeout."""
    assert proc.stdout is not None
    text_parts: list[str] = []
    start_time = asyncio.get_event_loop().time()

    while True:
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed > max_timeout:
            _kill_proc(proc)
            result.exit_code = 124
            result.stderr = f"{result.stderr}\nkimi reached {max_timeout}s maximum runtime ceiling".strip()
            return

        remaining_max = max_timeout - elapsed
        current_timeout = min(idle_timeout, remaining_max)

        try:
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=current_timeout)
        except asyncio.TimeoutError:
            _kill_proc(proc)
            result.exit_code = 124
            result.stderr = f"{result.stderr}\nkimi timed out after {idle_timeout}s of inactivity".strip()
            return

        if not line:
            break

        line_str = line.decode("utf-8", errors="replace").strip()
        if not line_str:
            continue
        try:
            raw = json.loads(line_str)
        except json.JSONDecodeError:
            continue
        evt = _classify_event(raw)
        if evt is None:
            continue
        result.events.append(evt)
        if evt.kind == "text":
            text_parts.append(evt.data)
        elif evt.kind == "thinking":
            result.total_thinking_chars += len(evt.data)
        elif evt.kind == "tool_call":
            result.total_tool_calls += 1
        elif evt.kind == "session_id":
            result.session_id_discovered = evt.data

    result.text = "".join(text_parts)
    assert proc.stderr is not None
    result.stderr = (await proc.stderr.read()).decode("utf-8", errors="replace")


async def run_kimi_stream(
    prompt: str, *, session_id: str | None = None, workdir: str,
    model: str, agent: str, kimi_path: str,
    idle_timeout: float = 300.0, max_timeout: float = 3600.0,
) -> StreamResult:
    """Run kimi-code CLI with async stdout streaming and activity-based timeouts."""
    args = _build_args(kimi_path, prompt, session_id, workdir, model)
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        result = StreamResult(text="", exit_code=-1, stderr="")
        await _drain_stdout(proc, result, idle_timeout=idle_timeout, max_timeout=max_timeout)
        if result.exit_code == -1:
            result.exit_code = await proc.wait()
        return result
    except Exception:
        _kill_proc(proc)
        raise


def _build_args(kimi_path: str, prompt: str, session_id: str | None,
                workdir: str, model: str) -> list[str]:
    """Build kimi-code (≥0.22) args. Omit -S when session_id is None (fresh session)."""
    args = [kimi_path, "-p", prompt, "--output-format", "stream-json",
            "--add-dir", workdir]
    if session_id:
        args.extend(["-S", session_id])
    if model:
        args.extend(["--model", model])
    return args
