"""Plugin-tool entry point: start | stop | status | logs | setup."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


SERVICE = "kimi-telegram-bridge.service"
LOG_FILE = Path.home() / ".kimi" / "bridge" / "logs" / "bridge.log"


def _systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["systemctl", "--user", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _action_start() -> dict[str, Any]:
    res = _systemctl("start", SERVICE)
    ok = res.returncode == 0
    return {
        "ok": ok,
        "output": (res.stdout + res.stderr).strip() or ("started" if ok else "failed"),
    }


def _action_stop() -> dict[str, Any]:
    res = _systemctl("stop", SERVICE)
    return {
        "ok": res.returncode == 0,
        "output": (res.stdout + res.stderr).strip() or "stopped",
    }


def _action_status() -> dict[str, Any]:
    res = _systemctl("status", SERVICE, "--no-pager")
    # systemctl status exits 3 when service is inactive; that's still useful info.
    return {
        "ok": res.returncode in (0, 3),
        "output": (res.stdout + res.stderr).strip(),
    }


def _action_logs(lines: int = 50) -> dict[str, Any]:
    # Resolve LOG_FILE at call time so tests can monkeypatch the module attr.
    log_file = sys.modules[__name__].LOG_FILE
    if log_file.exists():
        text = log_file.read_text(errors="replace").splitlines()
        return {"ok": True, "output": "\n".join(text[-lines:])}
    res = subprocess.run(
        ["journalctl", "--user", "-u", SERVICE, "-n", str(lines), "--no-pager"],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "ok": res.returncode == 0,
        "output": res.stdout.strip() or res.stderr.strip(),
    }


def _action_setup() -> dict[str, Any]:
    """Validate config + tools. Returns a human-readable report."""
    try:
        from src.config import load_config
    except Exception as err:
        return {"ok": False, "output": f"could not import config loader: {err}"}

    cfg_path = Path(__file__).resolve().parent.parent / "config.json"
    report: list[str] = [f"config path: {cfg_path}"]

    try:
        cfg = load_config(cfg_path)
        report.append("✓ config.json loaded")
    except Exception as err:
        return {"ok": False, "output": "\n".join([*report, f"✗ config error: {err}"])}

    kimi = subprocess.run(
        ["kimi", "--version"], capture_output=True, text=True, check=False
    )
    if kimi.returncode == 0:
        report.append(f"✓ kimi CLI found: {kimi.stdout.strip()}")
    else:
        report.append(f"✗ kimi --version failed: {kimi.stderr.strip()}")

    try:
        import httpx

        r = httpx.get(
            f"https://api.telegram.org/bot{cfg.telegram.bot_token}/getMe",
            timeout=10,
        )
        data = r.json()
        if data.get("ok"):
            user = data["result"]
            report.append(f"✓ telegram token valid (bot @{user.get('username')})")
        else:
            report.append(f"✗ telegram token rejected: {data.get('description')}")
    except Exception as err:
        report.append(f"✗ telegram check failed: {err}")

    ok = not any(line.startswith("✗") for line in report)
    return {"ok": ok, "output": "\n".join(report)}


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action")
    if action == "start":
        return _action_start()
    if action == "stop":
        return _action_stop()
    if action == "status":
        return _action_status()
    if action == "logs":
        return _action_logs(int(payload.get("lines") or 50))
    if action == "setup":
        return _action_setup()
    return {"ok": False, "output": f"unknown action: {action!r}"}


def main() -> None:  # pragma: no cover — IO wiring only
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as err:
        print(json.dumps({"ok": False, "output": f"invalid JSON on stdin: {err}"}))
        sys.exit(1)
    print(json.dumps(handle(payload)))


if __name__ == "__main__":  # pragma: no cover
    main()
