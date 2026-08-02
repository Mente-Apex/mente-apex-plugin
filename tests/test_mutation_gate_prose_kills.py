"""What the prose backend may and may not count as a kill.

`return result.returncode == 0` treated every nonzero pytest exit as "the guard
killed the mutant". pytest exits nonzero for reasons that are not a test
failure -- 2 interrupted, 3 internal error, 4 usage error, 5 no tests collected
-- so a mutant that broke collection outright scored as caught, produced no
survivor and no run error, and rendered as a clean result.
"""

import subprocess

import pytest

from mutation_gate_prose import (
    ProseBackend,
    _pytest_still_green,
    mutants_executed_for,
    prose_survivors,
)

DOC = "# Guard\n\nThe value MUST be positive.\n"


def _doc(tmp_path):
    (tmp_path / "doc.md").write_text(DOC, encoding="utf-8")
    return [("tests/test_g.py::test_guard", "doc.md", "Guard")]


class TestPytestExitCodesAreNotAllTheSameFact:
    @pytest.mark.parametrize("exit_code", [2, 3, 4, 5])
    def test_a_code_that_is_not_pass_or_fail_yields_no_answer(
        self, tmp_path, monkeypatch, exit_code
    ):
        monkeypatch.setattr(
            "mutation_gate_prose.subprocess.run",
            lambda argv, cwd, capture_output, text, timeout: (
                subprocess.CompletedProcess(argv, exit_code, stdout="", stderr="")
            ),
        )

        assert _pytest_still_green(tmp_path, "tests/test_g.py::test_guard") is None

    def test_zero_still_means_the_test_passed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "mutation_gate_prose.subprocess.run",
            lambda argv, cwd, capture_output, text, timeout: (
                subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
            ),
        )

        assert _pytest_still_green(tmp_path, "tests/test_g.py::test_guard") is True

    def test_one_still_means_the_test_failed_and_killed_the_mutant(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "mutation_gate_prose.subprocess.run",
            lambda argv, cwd, capture_output, text, timeout: (
                subprocess.CompletedProcess(argv, 1, stdout="", stderr="")
            ),
        )

        assert _pytest_still_green(tmp_path, "tests/test_g.py::test_guard") is False

    def test_a_hung_test_yields_no_answer_rather_than_hanging(
        self, tmp_path, monkeypatch
    ):
        def fake_run(argv, cwd, capture_output, text, timeout):
            raise subprocess.TimeoutExpired(argv, timeout)

        monkeypatch.setattr("mutation_gate_prose.subprocess.run", fake_run)

        assert _pytest_still_green(tmp_path, "tests/test_g.py::test_guard") is None


class TestAnUnanswerableMutantIsReportedNotCountedAsAKill:
    def test_it_becomes_an_inconclusive_row(self, tmp_path):
        declarations = _doc(tmp_path)

        survivors = prose_survivors(
            tmp_path, declarations, run_test=lambda node_id: None
        )

        assert survivors
        assert {survivor.status for survivor in survivors} == {"runtime_error"}

    def test_the_artifact_is_restored_afterwards(self, tmp_path):
        declarations = _doc(tmp_path)

        prose_survivors(tmp_path, declarations, run_test=lambda node_id: None)

        assert (tmp_path / "doc.md").read_text(encoding="utf-8") == DOC

    def test_a_real_kill_still_produces_no_survivor(self, tmp_path):
        """The control: a guard that genuinely notices every mutant reports
        nothing, and must keep doing so."""
        declarations = _doc(tmp_path)

        survivors = prose_survivors(
            tmp_path, declarations, run_test=lambda node_id: False
        )

        assert [s for s in survivors if s.status != "no_op_mutant"] == []


class TestOneBadDeclarationDoesNotTakeDownTheRun:
    def test_a_heading_that_no_longer_exists_degrades_to_one_row(self, tmp_path):
        """A stale `@pytest.mark.covers("docs/x.md", "Old Heading")` left after
        a rename raised straight out of `run_gate`, discarding the mutmut,
        Stryker and PIT survivors already collected."""
        (tmp_path / "doc.md").write_text(DOC, encoding="utf-8")
        declarations = [("tests/test_g.py::test_guard", "doc.md", "Old Heading")]

        survivors = prose_survivors(
            tmp_path, declarations, run_test=lambda node_id: True
        )

        assert [survivor.status for survivor in survivors] == ["declaration_error"]

    def test_a_missing_artifact_degrades_to_one_row(self, tmp_path):
        declarations = [("tests/test_g.py::test_guard", "gone.md", "Guard")]

        survivors = prose_survivors(
            tmp_path, declarations, run_test=lambda node_id: True
        )

        assert [survivor.status for survivor in survivors] == ["declaration_error"]

    def test_a_good_declaration_beside_a_bad_one_still_runs(self, tmp_path):
        """The point of degrading rather than raising: the rest of the run
        survives one broken declaration."""
        (tmp_path / "doc.md").write_text(DOC, encoding="utf-8")
        declarations = [
            ("tests/test_g.py::test_stale", "doc.md", "Old Heading"),
            ("tests/test_g.py::test_guard", "doc.md", "Guard"),
        ]

        survivors = prose_survivors(
            tmp_path, declarations, run_test=lambda node_id: True
        )

        statuses = {survivor.status for survivor in survivors}
        assert "declaration_error" in statuses
        assert statuses & {"survived", "survived_minor"}


class TestTheMutantCountIsExact:
    def test_a_failed_declaration_costs_all_its_operators(self, tmp_path):
        (tmp_path / "doc.md").write_text(DOC, encoding="utf-8")
        declarations = [("tests/test_g.py::test_stale", "doc.md", "Old Heading")]

        survivors = prose_survivors(
            tmp_path, declarations, run_test=lambda node_id: True
        )

        assert mutants_executed_for(declarations, survivors) == 0

    def test_a_clean_declaration_counts_every_operator_that_applied(self, tmp_path):
        declarations = _doc(tmp_path)

        survivors = prose_survivors(
            tmp_path, declarations, run_test=lambda node_id: False
        )
        no_ops = sum(1 for s in survivors if s.status == "no_op_mutant")

        from mutation_gate_prose import OPERATORS

        assert mutants_executed_for(declarations, survivors) == len(OPERATORS) - no_ops

    def test_the_backend_reports_none_before_it_has_run(self):
        assert ProseBackend().mutants_executed("/repo") is None


class TestTheProseBackendDegradesRatherThanTakingTheRunDown:
    def test_a_missing_uv_during_the_mutant_test_is_an_unanswered_mutant(
        self, tmp_path, monkeypatch
    ):
        """`_pytest_still_green` caught only TimeoutExpired, so a missing `uv`
        -- the very reason bin/mente-python exists -- raised FileNotFoundError
        out of `run_gate` and discarded every survivor the other backends had
        already collected."""

        def no_uv(argv, cwd, capture_output, text, timeout):
            raise FileNotFoundError(2, "No such file or directory", "uv")

        monkeypatch.setattr("mutation_gate_prose.subprocess.run", no_uv)

        assert _pytest_still_green(tmp_path, "tests/test_g.py::test_guard") is None

    def test_a_missing_uv_during_collection_is_a_run_error_not_a_crash(
        self, tmp_path, monkeypatch
    ):
        from mutation_gate_prose import collect_declarations

        def no_uv(argv, cwd, capture_output, text, env, timeout):
            raise FileNotFoundError(2, "No such file or directory", "uv")

        monkeypatch.setattr("mutation_gate_prose.subprocess.run", no_uv)

        with pytest.raises(RuntimeError, match="could not start"):
            collect_declarations(tmp_path)

    def test_collection_is_bounded_by_a_timeout(self, tmp_path, monkeypatch):
        from mutation_gate_prose import collect_declarations

        def hang(argv, cwd, capture_output, text, env, timeout):
            raise subprocess.TimeoutExpired(argv, timeout)

        monkeypatch.setattr("mutation_gate_prose.subprocess.run", hang)

        with pytest.raises(RuntimeError, match="did not finish within"):
            collect_declarations(tmp_path)

    def test_a_failed_run_clears_the_previous_runs_mutant_count(
        self, tmp_path, monkeypatch
    ):
        """Every other backend sets None on each failure path; this one
        returned a stale positive count after a crash, reading as 'that many
        mutants ran' when none did."""
        backend = ProseBackend()
        backend._mutants_executed = 3

        def explode(repo_root):
            raise RuntimeError("collection blew up")

        monkeypatch.setattr(backend, "_collect", explode)

        with pytest.warns(UserWarning):
            backend.survivors(tmp_path, ["doc.md"])

        assert backend.mutants_executed(tmp_path) is None
