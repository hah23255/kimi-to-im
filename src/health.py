"""Optional HTTP health/metrics endpoint."""
from __future__ import annotations

import asyncio
import json
import time

HEALTH_HOST = "127.0.0.1"
HEALTH_PORT = 9099
_started = time.time()
_turns_total = 0
_errors_total = 0


def record_turn() -> None:
    global _turns_total
    _turns_total += 1


def record_error() -> None:
    global _errors_total
    _errors_total += 1


async def _handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    import os
    try:
        import psutil
        mem = psutil.Process().memory_info().rss
    except ImportError:
        mem = 0
    body = json.dumps({
        "status": "ok",
        "uptime_seconds": time.time() - _started,
        "turns_total": _turns_total,
        "errors_total": _errors_total,
        "memory_bytes": mem,
    })
    response = (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "\r\n"
        f"{body}"
    )
    writer.write(response.encode())
    await writer.drain()
    writer.close()


async def start_server(host: str = HEALTH_HOST, port: int = HEALTH_PORT) -> asyncio.AbstractServer:
    return await asyncio.start_server(_handler, host, port)
