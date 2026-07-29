"""Parsing real mutmut 3.6.0 output.

Pinned against output captured verbatim from a live run, so a schema change in
mutmut fails loudly here instead of silently reporting no survivors — the worst
possible failure for a tool whose whole job is to report survivors.
"""

import json
import sys
from pathlib import Path

from mutation_gate_mutmut import (
    MutmutBackend,
    _configure_source_paths,
    _mutmut_executable,
    survivors_from_output,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_fixtures():
    stats = json.loads((FIXTURES / "mutmut-stats.json").read_text(encoding="utf-8"))
    results = (FIXTURES / "mutmut-results.txt").read_text(encoding="utf-8")
    return results, stats


def test_reports_only_the_survivors_not_the_killed_mutants():
    results, stats = load_fixtures()

    survivors = survivors_from_output(results, stats, diffs={})

    assert [s.mutant for s in survivors] == [
        "money.x_discount__mutmut_1",
        "money.x_discount__mutmut_2",
    ]


def test_associates_each_survivor_with_the_tests_that_exercise_its_function():
    results, stats = load_fixtures()

    survivors = survivors_from_output(results, stats, diffs={})

    assert survivors[0].associated_tests == (
        "tests/test_money.py::test_member_over_threshold_gets_ten_percent_off",
        "tests/test_money.py::test_vacuous_guard_asserts_nothing_real",
    )


def test_declares_function_granularity_because_mutmut_has_no_line_mapping():
    results, stats = load_fixtures()

    survivors = survivors_from_output(results, stats, diffs={})

    assert survivors[0].granularity == "function"
    assert survivors[0].location == "money.x_discount"
    assert survivors[0].backend == "mutmut"


def test_carries_the_diff_when_mutmut_show_supplied_one():
    results, stats = load_fixtures()
    diff = "-    if is_member and total > 100:\n+    if is_member or total > 100:"

    survivors = survivors_from_output(
        results, stats, diffs={"money.x_discount__mutmut_1": diff}
    )

    assert diff in survivors[0].mutant_diff


def test_an_unmapped_function_yields_no_tests_rather_than_an_exception():
    results = "    ghost.x_vanished__mutmut_1: survived\n"

    survivors = survivors_from_output(results, {}, diffs={})

    assert survivors[0].associated_tests == ()


def test_resolves_artifact_to_the_real_source_path_when_selection_is_given():
    results = "    api.money.x_discount__mutmut_1: survived\n"

    survivors = survivors_from_output(
        results, {}, diffs={}, source_paths=("src/api/money.py",)
    )

    assert survivors[0].artifact == "src/api/money.py"


def test_the_longest_matching_source_path_wins_over_a_shorter_package_prefix():
    results = "    api.money.x_discount__mutmut_1: survived\n"

    survivors = survivors_from_output(
        results,
        {},
        diffs={},
        source_paths=("src/api.py", "src/api/money.py"),
    )

    assert survivors[0].artifact == "src/api/money.py"


def test_falls_back_to_a_dotted_path_approximation_when_nothing_matches():
    results = "    money.x_discount__mutmut_1: survived\n"

    survivors = survivors_from_output(results, {}, diffs={}, source_paths=())

    assert survivors[0].artifact == "money.py"


def test_configure_source_paths_writes_a_fresh_tool_mutmut_table(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n', encoding="utf-8"
    )

    _configure_source_paths(tmp_path, ["scripts/foo.py", "scripts/bar.py"])

    import tomllib

    data = tomllib.loads((tmp_path / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["tool"]["mutmut"]["source_paths"] == [
        "scripts/foo.py",
        "scripts/bar.py",
    ]


def test_configure_source_paths_respects_an_existing_tool_mutmut_table(tmp_path):
    """Important (fix round 1): appending `[tool.mutmut]` unconditionally
    produces a second, duplicate table -- invalid TOML -- for any repo that
    already configures mutmut itself. Parse first; where a `[tool.mutmut]`
    table already exists, respect the operator's own configuration rather
    than corrupting the file.
    """
    original = '[project]\nname = "x"\n\n[tool.mutmut]\nsource_paths = ["src"]\n'
    (tmp_path / "pyproject.toml").write_text(original, encoding="utf-8")

    _configure_source_paths(tmp_path, ["scripts/foo.py"])

    after = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert after == original

    import tomllib

    data = tomllib.loads(after)  # still valid, single-table TOML
    assert data["tool"]["mutmut"]["source_paths"] == ["src"]


def test_mutmut_executable_resolves_relative_to_sys_executable_even_off_path(
    tmp_path, monkeypatch
):
    """Important (fix round 1): `shutil.which("mutmut")` only ever succeeded
    because the documented invocation (`uv run python scripts/mutation_gate.py`)
    happens to put `.venv/bin` on the child process's PATH -- nothing enforced
    or even checked that. A bare `python3 scripts/mutation_gate.py` still has
    a real, uv-managed `sys.executable` inside `.venv/bin`, with mutmut's own
    console script right beside it regardless of PATH, so resolving relative
    to `sys.executable` must find it even when PATH does not carry `.venv/bin`
    at all -- rather than silently reporting the whole Python partition as
    unavailable with a misleading "already installed" hint.
    """
    fake_venv_bin = tmp_path / "venv" / "bin"
    fake_venv_bin.mkdir(parents=True)
    fake_python = fake_venv_bin / "python3"
    fake_python.write_text("", encoding="utf-8")
    fake_mutmut = fake_venv_bin / "mutmut"
    fake_mutmut.write_text("", encoding="utf-8")

    monkeypatch.setattr(sys, "executable", str(fake_python))
    monkeypatch.setattr("mutation_gate_mutmut.shutil.which", lambda name: None)

    assert _mutmut_executable() == str(fake_mutmut)
    assert MutmutBackend().available("/irrelevant/repo/root") is True


def test_mutmut_executable_falls_back_to_path_when_no_venv_sibling_exists(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python3"))
    monkeypatch.setattr(
        "mutation_gate_mutmut.shutil.which", lambda name: "/usr/local/bin/mutmut"
    )

    assert _mutmut_executable() == "/usr/local/bin/mutmut"


def test_mutmut_executable_is_none_when_neither_resolves(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python3"))
    monkeypatch.setattr("mutation_gate_mutmut.shutil.which", lambda name: None)

    assert _mutmut_executable() is None
    assert MutmutBackend().available("/irrelevant/repo/root") is False
