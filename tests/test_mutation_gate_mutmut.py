"""Parsing real mutmut 3.6.0 output.

Pinned against output captured verbatim from a live run, so a schema change in
mutmut fails loudly here instead of silently reporting no survivors — the worst
possible failure for a tool whose whole job is to report survivors.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

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


def test_killed_is_silently_dropped():
    results = "    money.x_discount__mutmut_1: killed\n"

    survivors = survivors_from_output(results, {}, diffs={})

    assert survivors == ()


def test_single_word_inconclusive_statuses_reach_the_operator():
    """timeout/suspicious/skipped/segfault match RESULT_LINE but were
    previously silently dropped by the `!= "survived"` check -- they must
    surface as Survivors carrying their real status, not vanish."""
    results = "\n".join(
        [
            "    money.x_a__mutmut_1: timeout",
            "    money.x_b__mutmut_1: suspicious",
            "    money.x_c__mutmut_1: skipped",
            "    money.x_d__mutmut_1: segfault",
        ]
    )

    survivors = survivors_from_output(results, {}, diffs={})

    assert [s.status for s in survivors] == [
        "timeout",
        "suspicious",
        "skipped",
        "segfault",
    ]


def test_multi_word_statuses_are_parsed_not_invisible():
    """Multi-word statuses (space-separated) never matched RESULT_LINE's
    \\w+ at all -- structurally invisible, not just mis-tagged."""
    results = "\n".join(
        [
            "    money.x_a__mutmut_1: no tests",
            "    money.x_b__mutmut_1: not checked",
            "    money.x_c__mutmut_1: caught by type check",
            "    money.x_d__mutmut_1: check was interrupted by user",
        ]
    )

    survivors = survivors_from_output(results, {}, diffs={})

    assert [s.status for s in survivors] == [
        "no tests",
        "not checked",
        "caught by type check",
        "check was interrupted by user",
    ]


def test_survived_status_is_still_the_default_survived():
    results = "    money.x_discount__mutmut_1: survived\n"

    survivors = survivors_from_output(results, {}, diffs={})

    assert survivors[0].status == "survived"


def test_an_unrecognised_status_raises_rather_than_vanishing():
    results = "    money.x_discount__mutmut_1: some_new_status\n"

    with pytest.raises(ValueError, match="some_new_status"):
        survivors_from_output(results, {}, diffs={})


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


def _fake_subprocess_run(run_stdout="", run_returncode=1, run_stderr="crashed"):
    def fake_run(argv, cwd, capture_output, text):
        if argv[-1] == "run":
            return subprocess.CompletedProcess(
                argv, run_returncode, stdout="", stderr=run_stderr
            )
        return subprocess.CompletedProcess(argv, 0, stdout=run_stdout, stderr="")

    return fake_run


def test_a_crashed_collection_reports_one_rollup_not_a_flood_of_rows(
    tmp_path, monkeypatch
):
    """Reproduces the reviewer's follow-up finding: when
    `mutants/mutmut-stats.json` was never written -- collection crashed
    before a single mutant ran -- `mutmut results` can still print a
    `not checked` line per mutant it would have run. Defect B's fix, taken
    alone, would turn that ONE system-level failure into a Survivor per
    line (reproduced live: 4298 of them). It must instead surface as a
    single run-level fact, and `survivors()` must not emit any of those rows.
    """
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n', encoding="utf-8"
    )
    not_checked_output = "\n".join(
        f"    money.x_discount__mutmut_{i}: not checked" for i in range(1, 5)
    )
    monkeypatch.setattr(
        "mutation_gate_mutmut.subprocess.run",
        _fake_subprocess_run(run_stdout=not_checked_output + "\n"),
    )
    monkeypatch.setattr("mutation_gate_mutmut._mutmut_executable", lambda: "mutmut")

    backend = MutmutBackend()
    with pytest.warns(UserWarning):
        survivors = backend.survivors(tmp_path, ["scripts/money.py"])

    assert survivors == ()
    run_errors = backend.run_errors(tmp_path)
    assert len(run_errors) == 1
    assert "did not complete" in run_errors[0]
    assert "4" in run_errors[0]


def test_a_completed_run_has_no_run_errors(tmp_path, monkeypatch):
    """The rollup is specific to the stats-file-missing crash signal -- a run
    that completed (stats file written) must not report a run error, and its
    real survived/inconclusive mutants keep flowing through individually."""
    mutants_dir = tmp_path / "mutants"
    mutants_dir.mkdir()
    (mutants_dir / "mutmut-stats.json").write_text("{}", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n', encoding="utf-8"
    )
    monkeypatch.setattr("mutation_gate_mutmut._mutmut_executable", lambda: "mutmut")
    monkeypatch.setattr(
        "mutation_gate_mutmut.subprocess.run",
        lambda argv, cwd, capture_output, text: subprocess.CompletedProcess(
            argv,
            0,
            stdout=(
                "    money.x_discount__mutmut_1: survived\n"
                "    money.x_discount__mutmut_2: timeout\n"
            ),
            stderr="",
        ),
    )

    backend = MutmutBackend()
    survivors = backend.survivors(tmp_path, ["scripts/money.py"])

    assert backend.run_errors(tmp_path) == ()
    assert [s.status for s in survivors] == ["survived", "timeout"]


def test_run_errors_defaults_to_empty_before_survivors_is_ever_called(tmp_path):
    assert MutmutBackend().run_errors(tmp_path) == ()
