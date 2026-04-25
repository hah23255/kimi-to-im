"""Tests for src.control — plugin tool entry point."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.control import handle


def _run_handle(action: str, **extra: object) -> dict:
    payload = {"action": action, **extra}
    return handle(payload)


def test_start_invokes_systemctl_start(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="active\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = _run_handle("start")
    assert result["ok"] is True
    assert any("start" in c and "kimi-telegram-bridge.service" in c for c in calls)


def test_stop_invokes_systemctl_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = _run_handle("stop")
    assert result["ok"] is True
    assert any("stop" in c and "kimi-telegram-bridge.service" in c for c in calls)


def test_status_returns_systemctl_output(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            cmd, 0, stdout="Active: active (running)\n", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = _run_handle("status")
    assert "Active: active (running)" in result["output"]


def test_logs_tails_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log_file = tmp_path / "bridge.log"
    log_file.write_text("\n".join(f"line {i}" for i in range(100)) + "\n")
    monkeypatch.setattr("src.control.LOG_FILE", log_file)
    result = _run_handle("logs", lines=5)
    assert result["ok"] is True
    out_lines = result["output"].splitlines()
    assert len(out_lines) == 5
    assert out_lines[-1] == "line 99"


def test_logs_fallback_to_journalctl_when_file_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("src.control.LOG_FILE", tmp_path / "missing.log")
    captured: list[list[str]] = []

    def fake_run(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        captured.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="from journal\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = _run_handle("logs", lines=10)
    assert "from journal" in result["output"]
    assert any("journalctl" in c[0] for c in captured)


def test_unknown_action_returns_error() -> None:
    result = _run_handle("nuke")
    assert result["ok"] is False
    assert "unknown action" in result["output"].lower()
