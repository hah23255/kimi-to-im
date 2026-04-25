"""Tests for src.kimi_runner — parser and subprocess spawn."""
from __future__ import annotations

import stat
import textwrap
from pathlib import Path

import pytest

from src.kimi_runner import KimiResult, parse_stream_json, run_kimi


# --- parser ----------------------------------------------------------

def test_parse_extracts_assistant_text() -> None:
    stream = (
        '{"type": "assistant", "content": [{"type": "text", "text": "Hello "}]}\n'
        '{"type": "assistant", "content": [{"type": "text", "text": "world"}]}\n'
    )
    assert parse_stream_json(stream) == "Hello world"


def test_parse_ignores_think_blocks() -> None:
    stream = (
        '{"type": "assistant", "content": [{"type": "think", "text": "hmm"}]}\n'
        '{"type": "assistant", "content": [{"type": "text", "text": "hi"}]}\n'
    )
    assert parse_stream_json(stream) == "hi"


def test_parse_ignores_unknown_event_types() -> None:
    stream = (
        '{"type": "turn_begin"}\n'
        '{"type": "step_begin", "id": 1}\n'
        '{"type": "assistant", "content": [{"type": "text", "text": "ok"}]}\n'
        '{"type": "turn_end"}\n'
    )
    assert parse_stream_json(stream) == "ok"


def test_parse_skips_blank_lines_and_invalid_json() -> None:
    stream = (
        "\n"
        "not-json-junk\n"
        '{"type": "assistant", "content": [{"type": "text", "text": "hi"}]}\n'
    )
    assert parse_stream_json(stream) == "hi"


def test_parse_handles_assistant_with_multiple_text_parts() -> None:
    stream = (
        '{"type": "assistant", "content": ['
        '{"type": "text", "text": "part one. "},'
        '{"type": "text", "text": "part two."}'
        ']}\n'
    )
    assert parse_stream_json(stream) == "part one. part two."


def test_parse_empty_stream_returns_empty_string() -> None:
    assert parse_stream_json("") == ""


# --- run_kimi (integration with a fake kimi binary) ------------------

@pytest.fixture
def fake_kimi(tmp_path: Path) -> Path:
    """Create an executable shell stub that emits a known stream-json reply."""
    script = tmp_path / "kimi"
    script.write_text(
        textwrap.dedent(
            """\
            #!/bin/sh
            # Read prompt from stdin to mimic real kimi --print behaviour.
            cat > /dev/null
            cat <<'EOF'
            {"type": "assistant", "content": [{"type": "text", "text": "fake reply"}]}
            EOF
            """
        )
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


pytestmark = pytest.mark.asyncio


async def test_run_kimi_returns_assistant_text(fake_kimi: Path, tmp_path: Path) -> None:
    result = await run_kimi(
        prompt="hello",
        session_id="sess-1",
        workdir=str(tmp_path),
        model="",
        agent="default",
        kimi_path=str(fake_kimi),
    )
    assert isinstance(result, KimiResult)
    assert result.exit_code == 0
    assert result.text == "fake reply"


async def test_run_kimi_surfaces_nonzero_exit(tmp_path: Path) -> None:
    """A fake binary that exits 1 should produce KimiResult with exit_code=1."""
    script = tmp_path / "kimi-fail"
    script.write_text("#!/bin/sh\necho boom 1>&2\nexit 1\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    result = await run_kimi(
        prompt="x",
        session_id="s",
        workdir=str(tmp_path),
        model="",
        agent="default",
        kimi_path=str(script),
    )
    assert result.exit_code == 1
    assert "boom" in result.stderr
    assert result.text == ""


async def test_run_kimi_passes_session_and_workdir_args(tmp_path: Path) -> None:
    """The fake binary records its argv so we can assert the runner built the
    correct command line."""
    captured = tmp_path / "argv.txt"
    script = tmp_path / "kimi-record"
    script.write_text(
        textwrap.dedent(
            f"""\
            #!/bin/sh
            cat > /dev/null
            printf '%s\\n' "$@" > "{captured}"
            cat <<'EOF'
            {{"type": "assistant", "content": [{{"type": "text", "text": "ok"}}]}}
            EOF
            """
        )
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    await run_kimi(
        prompt="hi",
        session_id="abc",
        workdir="/tmp/work",
        model="kimi-code/kimi-for-coding",
        agent="default",
        kimi_path=str(script),
    )
    args = captured.read_text().splitlines()
    assert "--print" in args
    assert "--output-format" in args
    assert "stream-json" in args
    assert "-S" in args and "abc" in args
    assert "--work-dir" in args and "/tmp/work" in args
    assert "--model" in args and "kimi-code/kimi-for-coding" in args
    assert "--agent" in args and "default" in args
