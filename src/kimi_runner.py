"""Legacy kimi CLI subprocess executor (synchronous, backward-compatible)."""
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
    """Accumulate assistant text from kimi stream-json output."""
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
                    t = part.get("text")
                    if isinstance(t, str):
                        chunks.append(t)
    return "".join(chunks)


def _run_sync(args: list[str], prompt: str, timeout: float | None = None) -> KimiResult:
    """Synchronous subprocess worker. Called via asyncio.to_thread."""
    try:
        p = subprocess.run(args, input=prompt.encode(),
                           capture_output=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        stderr = ""
        if exc.stderr is not None:
            stderr = (exc.stderr.decode("utf-8", errors="replace")
                      if isinstance(exc.stderr, (bytes, bytearray)) else str(exc.stderr))
        return KimiResult(text="", exit_code=124, stderr=f"{stderr}\ntimeout after {timeout}s".strip())
    return KimiResult(text=parse_stream_json(p.stdout.decode("utf-8", errors="replace")),
                      exit_code=p.returncode,
                      stderr=p.stderr.decode("utf-8", errors="replace"))


async def run_kimi(
    prompt: str, *, session_id: str, workdir: str,
    model: str, agent: str, kimi_path: str, timeout: float | None = None,
) -> KimiResult:
    """Run kimi CLI via thread-pooled subprocess (synchronous path)."""
    args = [kimi_path, "--print", "--output-format", "stream-json",
            "-S", session_id, "--work-dir", workdir, "--agent", agent]
    if model:
        args.extend(["--model", model])
    return await asyncio.to_thread(_run_sync, args, prompt, timeout)
