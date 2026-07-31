"""Behaviour of bin/mente-python, the one place interpreter choice is decided.

Every test here EXECUTES the launcher against a synthetic PATH. Its sibling
guard in test_skill_integrity.py can only substring-match the source, which a
control-flow bug survives intact: invert the `command -v uv` test and every
literal that guard checks is still present while the behaviour is reversed.
Nothing short of running it catches that.

The interpreters are stubs rather than real installs so the suite answers the
same on a laptop with five Pythons and on CI with one.
"""

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPO_ROOT / "bin" / "mente-python"

# Enough of a PATH for `sh` itself; deliberately excludes the directories where
# this machine keeps real interpreters, so only the stubs below are findable.
BARE_PATH = "/usr/bin:/bin"


def write_stub(directory, name, body):
    """An executable stand-in for a program on PATH."""
    stub = directory / name
    stub.write_text(f"#!/bin/sh\n{body}\n")
    stub.chmod(0o755)
    return stub


@pytest.fixture
def path_dir(tmp_path):
    """A directory that will be the only non-system entry on PATH."""
    directory = tmp_path / "bin"
    directory.mkdir()
    return directory


def run_launcher(path_dir, *arguments):
    return subprocess.run(
        ["sh", str(LAUNCHER), *arguments],
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{path_dir}:{BARE_PATH}"},
    )


def test_uv_is_preferred_and_invoked_without_a_version_pin(path_dir):
    """The uv branch, asserted through the argv uv actually receives. This is
    the contract the hook test names but cannot see: --no-project present so the
    session's directory is not adopted, and no --python so the operator's own
    pin is what decides."""
    write_stub(path_dir, "uv", 'echo "UV-ARGV: $*"')
    write_stub(path_dir, "python3", "echo SHOULD-NOT-REACH-FALLBACK")

    completed = run_launcher(path_dir, "engine.py", "status")

    assert completed.returncode == 0, completed.stderr
    assert "UV-ARGV: run --no-project python engine.py status" in completed.stdout
    assert "--python" not in completed.stdout, "the operator's pin must decide"
    assert "SHOULD-NOT-REACH-FALLBACK" not in completed.stdout


def test_a_new_enough_system_interpreter_is_used_when_uv_is_absent(path_dir):
    """The branch the user asked for: no uv, so run what the machine has —
    and say so, because a silent fallback is how the pin quietly stops
    applying."""
    write_stub(path_dir, "python3", 'echo "RAN: $*"')

    completed = run_launcher(path_dir, "engine.py")

    assert completed.returncode == 0, completed.stderr
    assert "RAN: engine.py" in completed.stdout
    assert "uv not found" in completed.stderr
    assert "docs.astral.sh/uv" in completed.stderr, "the nudge must be actionable"


def test_an_interpreter_below_the_floor_is_refused_not_run(path_dir):
    """The case that started all this. A 3.9 on PATH cannot parse this
    plugin's code, so running it produces a SyntaxError traceback that names a
    line number and hides the actual problem. Refusing names the problem."""
    # `exit 1` from the version probe is exactly how a pre-3.14 interpreter
    # answers it, without needing an old interpreter installed to find out.
    for name in ("python3.14", "python3", "python"):
        write_stub(path_dir, name, "exit 1")

    completed = run_launcher(path_dir, "engine.py")

    assert completed.returncode == 1
    assert "no usable Python" in completed.stderr
    assert "3.14" in completed.stderr, "the refusal must name the floor"
    assert "docs.astral.sh/uv" in completed.stderr


def test_the_first_candidate_meeting_the_floor_wins(path_dir):
    """Ordering matters: an old `python3` earlier on PATH must not shadow a
    usable `python3.14`, or the fallback refuses on a machine that could
    perfectly well have run."""
    write_stub(path_dir, "python3.14", 'echo "RAN-314: $*"')
    write_stub(path_dir, "python3", "exit 1")

    completed = run_launcher(path_dir, "engine.py")

    assert completed.returncode == 0, completed.stderr
    assert "RAN-314: engine.py" in completed.stdout


def test_arguments_survive_the_fallback_verbatim(path_dir):
    """Whitespace and empty arguments must reach the module unsplit — the
    engine is handed JSON and paths, and a lost quote corrupts both."""
    write_stub(path_dir, "python3", 'for argument in "$@"; do echo "[$argument]"; done')

    completed = run_launcher(path_dir, "engine.py", "two words", "")

    assert completed.returncode == 0, completed.stderr
    assert "[engine.py]" in completed.stdout
    assert "[two words]" in completed.stdout
    assert "[]" in completed.stdout


def test_the_exit_code_of_the_delegated_interpreter_is_preserved(path_dir):
    """The launcher `exec`s rather than wrapping, so a failing engine must
    still fail. A launcher that swallowed this would make every caller's error
    handling — including the hook's — read success."""
    # The launcher probes the candidate's version with `-c` before running it,
    # so the stub has to pass that probe and fail only the real invocation --
    # otherwise it reads as "too old" and is skipped, testing nothing.
    write_stub(path_dir, "python3", 'case "$1" in -c) exit 0 ;; esac\nexit 42')

    assert run_launcher(path_dir, "engine.py").returncode == 42
