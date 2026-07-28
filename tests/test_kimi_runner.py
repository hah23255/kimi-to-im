"""Tests for src.kimi_runner — parser and subprocess spawn."""
from __future__ import annotations

import stat
import textwrap
from pathlib import Path

import pytest

from src.kimi_runner import KimiResult, parse_stream_json, run_kimi


# --- parser ----------------------------------------------------------

def test_parse_extracts_assistant_text_from_string_content() -> None:
    """Real kimi --no-thinking shape: content is a plain string."""
    stream = '{"role":"assistant","content":"Hello world"}\n'
    assert parse_stream_json(stream) == "Hello world"


def test_parse_extracts_assistant_text_from_list_content() -> None:
    """Real kimi (default thinking on) shape: content is a list of parts."""
    stream = (
        '{"role":"assistant","content":['
        '{"type":"text","text":"Hello "},'
        '{"type":"text","text":"world"}'
        ']}\n'
    )
    assert parse_stream_json(stream) == "Hello world"


def test_parse_ignores_think_blocks() -> None:
    """Think parts use the `think` key (not `text`); they are not the reply."""
    stream = (
        '{"role":"assistant","content":['
        '{"type":"think","think":"hmm","encrypted":null},'
        '{"type":"text","text":"hi"}'
        ']}\n'
    )
    assert parse_stream_json(stream) == "hi"


def test_parse_ignores_resume_session_trailer() -> None:
    """Real kimi appends a non-JSON line: `To resume this session: kimi -r ...`."""
    stream = (
        '{"role":"assistant","content":"reply"}\n'
        '\n'
        'To resume this session: kimi -r abc-123\n'
    )
    assert parse_stream_json(stream) == "reply"


def test_parse_ignores_non_assistant_role() -> None:
    """Other roles (user, system, tool) and untyped events are skipped."""
    stream = (
        '{"role":"user","content":"hi"}\n'
        '{"role":"system","content":"sys"}\n'
        '{"role":"assistant","content":"the reply"}\n'
    )
    assert parse_stream_json(stream) == "the reply"


def test_parse_skips_blank_lines_and_invalid_json() -> None:
    stream = (
        "\n"
        "not-json-junk\n"
        '{"role":"assistant","content":"hi"}\n'
    )
    assert parse_stream_json(stream) == "hi"


def test_parse_empty_stream_returns_empty_string() -> None:
    assert parse_stream_json("") == ""


def test_parse_handles_mixed_string_and_list_events_in_one_stream() -> None:
    """Multiple events back-to-back; each may be either shape."""
    stream = (
        '{"role":"assistant","content":"first"}\n'
        '{"role":"assistant","content":[{"type":"text","text":" then second"}]}\n'
    )
    assert parse_stream_json(stream) == "first then second"


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
            {"role":"assistant","content":"fake reply"}
            EOF
            """
        )
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


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
            {{"role":"assistant","content":"ok"}}
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
    assert "-p" in args
    assert "--output-format" in args
    assert "stream-json" in args
    assert "-S" in args and "abc" in args
    assert "--add-dir" in args and "/tmp/work" in args
    assert "--model" in args and "kimi-code/kimi-for-coding" in args


async def test_run_kimi_returns_synthetic_timeout_result(tmp_path: Path) -> None:
    """A kimi process that exceeds the timeout returns exit_code 124."""
    script = tmp_path / "kimi-hang"
    script.write_text("#!/bin/sh\ncat > /dev/null\nsleep 5\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    result = await run_kimi(
        prompt="x",
        session_id="s",
        workdir=str(tmp_path),
        model="",
        agent="default",
        kimi_path=str(script),
        timeout=0.5,
    )
    assert result.exit_code == 124
    assert "timeout" in result.stderr
    assert result.text == ""


async def test_run_kimi_no_timeout_by_default(tmp_path: Path) -> None:
    """Without a timeout, a quick kimi invocation completes normally."""
    script = tmp_path / "kimi-quick"
    script.write_text(
        '#!/bin/sh\ncat > /dev/null\necho \'{"role":"assistant","content":"ok"}\'\n'
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    result = await run_kimi(
        prompt="x",
        session_id="s",
        workdir=str(tmp_path),
        model="",
        agent="default",
        kimi_path=str(script),
    )
    assert result.exit_code == 0
    assert result.text == "ok"
