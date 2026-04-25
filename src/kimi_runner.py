"""Spawn the kimi CLI and parse its stream-json output."""
from __future__ import annotations

import asyncio
import json
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class KimiResult:
    text: str
    exit_code: int
    stderr: str


def parse_stream_json(stdout: str) -> str:
    """Accumulate assistant text from kimi's newline-delimited JSON stream.

    Quietly ignores blank lines, malformed JSON, non-assistant events,
    and `think` content blocks (which are model thinking, not the reply).
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
        if not isinstance(event, dict) or event.get("type") != "assistant":
            continue
        for part in event.get("content") or []:
            if isinstance(part, dict) and part.get("type") == "text":
                text = part.get("text")
                if isinstance(text, str):
                    chunks.append(text)
    return "".join(chunks)


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
    """Run the kimi CLI in --print stream-json mode. Returns when the turn ends."""
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
