"""Spawn the kimi CLI and parse its stream-json output."""
from __future__ import annotations

import asyncio
import json
import subprocess
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass(frozen=True)
class KimiResult:
    text: str
    exit_code: int
    stderr: str


@dataclass
class StreamEvent:
    """One event from the kimi streaming JSON output."""
    kind: str  # "text", "thinking", "tool_call", "tool_result", "metadata"
    data: str
    tool_name: str = ""
    timestamp: float = 0.0


@dataclass
class StreamResult:
    """Aggregated result of a streaming kimi run."""
    text: str
    exit_code: int
    stderr: str
    events: list[StreamEvent] = field(default_factory=list)
    total_thinking_chars: int = 0
    total_tool_calls: int = 0


def parse_stream_json(stdout: str) -> str:
    """Accumulate assistant text from kimi's newline-delimited JSON stream.

    Handles two real-kimi shapes:
      {"role":"assistant","content":"plain text"}   (when --no-thinking)
      {"role":"assistant","content":[{"type":"text","text":"..."}, ...]}

    Quietly ignores blank lines, malformed JSON, non-assistant events,
    ``think`` content parts, and the trailing "To resume this session: ..." line.
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
        if not isinstance(event, dict) or event.get("role") != "assistant":
            continue
        content = event.get("content")
        if isinstance(content, str):
            chunks.append(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text = part.get("text")
                    if isinstance(text, str):
                        chunks.append(text)
    return "".join(chunks)


def _classify_event(raw: dict) -> StreamEvent | None:
    """Classify a raw kimi JSON line into a StreamEvent.

    Handles:
      - assistant text (plain string or content-block array)
      - thinking blocks (``type: "thinking"`` content parts)
      - tool_use blocks (``type: "tool_use"``)
      - metadata events (model, token counts)
      - resume-session trailer (ignored)

    Returns None for events that should be skipped entirely.
    """
    import time as _time
    ts = _time.monotonic()

    # --- assistant content ---
    if isinstance(event, dict) and event.get("role") == "assistant":
        content = event.get("content")
        # Plain string
        if isinstance(content, str):
            return StreamEvent(kind="text", data=content, timestamp=ts)
        # Content-block array
        if isinstance(content, list):
            text_parts: list[str] = []
            thinking_parts: list[str] = []
            tool_calls: list[str] = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                ptype = part.get("type", "")
                if ptype == "text":
                    t = part.get("text", "")
                    if isinstance(t, str) and t:
                        text_parts.append(t)
                elif ptype in ("thinking", "think"):
                    t = part.get("thinking") or part.get("text", "")
                    if isinstance(t, str) and t:
                        thinking_parts.append(t)
                        return StreamEvent(kind="thinking", data=t, timestamp=ts)
                elif ptype == "tool_use":
                    name = part.get("name", "unknown")
                    inp = part.get("input", {})
                    desc = _tool_description(name, inp)
                    tool_calls.append(desc)
                    return StreamEvent(
                        kind="tool_call", data=desc, tool_name=name, timestamp=ts
                    )
            if text_parts:
                return StreamEvent(kind="text", data="".join(text_parts), timestamp=ts)
            return None

    # --- standalone thinking event ---
    if isinstance(event, dict) and event.get("type") == "thinking":
        t = event.get("thinking") or event.get("content") or ""
        if isinstance(t, str) and t:
            return StreamEvent(kind="thinking", data=t, timestamp=ts)

    # --- metadata ---
    if isinstance(event, dict) and event.get("type") in (
        "model", "token_usage", "cost", "metadata"
    ):
        return StreamEvent(kind="metadata", data=json.dumps(event), timestamp=ts)

    return None


def _tool_description(name: str, inp: dict) -> str:
    """Human-readable one-line description of a tool call."""
    templates: dict[str, str] = {
        "read":        "📖 {path}",
        "write":       "✏️ {path} ({lines}L)",
        "edit":        "🔧 {path}",
        "grep":        "🔍 `{pattern}`",
        "glob":        "🔎 {pattern}",
        "web_fetch":   "🌐 {url}",
        "web_search":  "🔎 web: {query}",
        "exec":        "⚡ `{command}`",
        "bash":        "💻 `{command}`",
        "run_shell":   "💻 `{command}`",
    }
    template = templates.get(name, "🔨 {name}")
    try:
        return template.format(name=name, **(inp or {}))
    except (KeyError, ValueError):
        return f"🔨 {name}"


async def _read_stream_events(
    proc: asyncio.subprocess.Process,
    timeout: float | None = None,
) -> StreamResult:
    """Read lines from kimi's stdout asynchronously, classifying each into StreamEvents.

    Accumulates assistant text, counts thinking/tool events, and handles the
    subprocess lifecycle.  Timeout is enforced via asyncio.wait_for on the
    communicate()-equivalent drain; on expiry the process is sent SIGTERM then
    SIGKILL after a 5-second grace period.
    """
    result = StreamResult(text="", exit_code=-1, stderr="")

    async def _drain() -> None:
        text_chunks: list[str] = []
        # Read stdout line-by-line
        assert proc.stdout is not None
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
                text_chunks.append(evt.data)
            elif evt.kind == "thinking":
                result.total_thinking_chars += len(evt.data)
            elif evt.kind == "tool_call":
                result.total_tool_calls += 1
        result.text = "".join(text_chunks)
        # Read stderr
        assert proc.stderr is not None
        stderr_bytes = await proc.stderr.read()
        result.stderr = stderr_bytes.decode("utf-8", errors="replace")

    try:
        if timeout:
            await asyncio.wait_for(_drain(), timeout=timeout)
            # Normal exit — wait for the process to finish
            result.exit_code = await proc.wait()
        else:
            await _drain()
            result.exit_code = await proc.wait()
    except asyncio.TimeoutError:
        try:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
        except ProcessLookupError:
            pass
        result.exit_code = 124
        msg = f"kimi timed out after {timeout}s"
        result.stderr = f"{result.stderr}\n{msg}".strip()

    return result


async def run_kimi_stream(
    prompt: str,
    *,
    session_id: str,
    workdir: str,
    model: str,
    agent: str,
    kimi_path: str,
    timeout: float | None = None,
) -> StreamResult:
    """Run kimi CLI with async stdout streaming.

    Returns a StreamResult containing the final text, all intermediate
    StreamEvents (text, thinking, tool_calls), and metadata counters.
    """
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

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        # Write prompt to stdin and close
        assert proc.stdin is not None
        proc.stdin.write(prompt.encode())
        await proc.stdin.drain()
        proc.stdin.close()
        return await _read_stream_events(proc, timeout=timeout)
    except Exception:
        try:
            proc.kill()
            await proc.wait()
        except (ProcessLookupError, OSError):
            pass
        raise


# ── Backward-compatible synchronous API ──────────────────────────

def _run_sync(
    args: list[str],
    prompt: str,
    timeout: float | None = None,
) -> KimiResult:
    """Synchronous worker for subprocess invocation. Called via asyncio.to_thread."""
    try:
        completed = subprocess.run(
            args,
            input=prompt.encode(),
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        partial_stderr = ""
        if exc.stderr is not None:
            partial_stderr = (
                exc.stderr.decode("utf-8", errors="replace")
                if isinstance(exc.stderr, (bytes, bytearray))
                else str(exc.stderr)
            )
        message = f"kimi timed out after {timeout}s"
        stderr = f"{partial_stderr}\n{message}".strip() if partial_stderr else message
        return KimiResult(text="", exit_code=124, stderr=stderr)
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
    timeout: float | None = None,
) -> KimiResult:
    """Run the kimi CLI in --print stream-json mode. Returns when the turn ends.

    Uses thread-pooled subprocess (backward-compatible).  For streaming events
    use ``run_kimi_stream()`` instead.
    """
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
    return await asyncio.to_thread(_run_sync, args, prompt, timeout)
