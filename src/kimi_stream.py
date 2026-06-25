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


async def _drain_stdout(proc: asyncio.subprocess.Process, result: StreamResult) -> None:
    """Read stdout line-by-line, classify events into result."""
    assert proc.stdout is not None
    text_parts: list[str] = []
    async for line in proc.stdout:
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
    result.text = "".join(text_parts)
    assert proc.stderr is not None
    result.stderr = (await proc.stderr.read()).decode("utf-8", errors="replace")


async def _run_with_timeout(proc: asyncio.subprocess.Process, result: StreamResult,
                            timeout: float) -> None:
    """Run drain with timeout; on expiry terminate then kill."""
    try:
        await asyncio.wait_for(_drain_stdout(proc, result), timeout=timeout)
        result.exit_code = await proc.wait()
    except asyncio.TimeoutError:
        _kill_proc(proc)
        result.exit_code = 124
        result.stderr = f"{result.stderr}\nkimi timed out after {timeout}s".strip()


def _kill_proc(proc: asyncio.subprocess.Process) -> None:
    try:
        proc.terminate()
    except ProcessLookupError:
        return


async def run_kimi_stream(
    prompt: str, *, session_id: str, workdir: str,
    model: str, agent: str, kimi_path: str, timeout: float | None = None,
) -> StreamResult:
    """Run kimi CLI with async stdout streaming."""
    args = _build_args(kimi_path, session_id, workdir, model, agent)
    proc = await asyncio.create_subprocess_exec(
        *args, stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        assert proc.stdin is not None
        proc.stdin.write(prompt.encode())
        await proc.stdin.drain()
        proc.stdin.close()
        result = StreamResult(text="", exit_code=-1, stderr="")
        if timeout:
            await _run_with_timeout(proc, result, timeout)
        else:
            await _drain_stdout(proc, result)
            result.exit_code = await proc.wait()
        return result
    except Exception:
        _kill_proc(proc)
        raise


def _build_args(kimi_path: str, session_id: str, workdir: str,
                model: str, agent: str) -> list[str]:
    args = [kimi_path, "--print", "--output-format", "stream-json",
            "-S", session_id, "--work-dir", workdir, "--agent", agent]
    if model:
        args.extend(["--model", model])
    return args
