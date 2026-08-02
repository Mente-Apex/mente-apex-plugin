"""A previous run's report must never be read as this run's result.

Every backend that reads results out of a file had the same hole, and three of
the four had it open: check the report exists, find one there, parse it. The
workspace makes that the normal case rather than a corner one -- `--scope
working-tree` copies the operator's tree verbatim and every report location is
gitignored (`reports/`, `mutants/`, `target/`), so a stale report is carried in
by construction. A tool that then dies before writing anything leaves last
week's all-killed report exactly where the backend looks, and the run passes
clean over code it never mutated.

These are the guards, one per backend, plus the shared policy they now use.
"""

import subprocess
from pathlib import Path

import pytest

from mutation_gate_freshness import ReportFreshness
from mutation_gate_mutmut import MutmutBackend
from mutation_gate_stryker import StrykerBackend

STALE_STRYKER_REPORT = """
{"files": {"src/a.ts": {"mutants": [
  {"id": "1", "status": "Killed", "mutatorName": "Arithmetic",
   "replacement": "-", "location": {"start": {"line": 1, "column": 1}}}
]}}}
"""


class TestTheSharedFreshnessPolicy:
    def test_a_file_that_was_already_there_and_untouched_is_not_written_since(
        self, tmp_path
    ):
        report = tmp_path / "report.json"
        report.write_text("{}", encoding="utf-8")
        freshness = ReportFreshness(lambda root: (Path(root) / "report.json",))

        freshness.snapshot(tmp_path)

        assert freshness.written_since(tmp_path) == ()

    def test_a_file_the_run_rewrote_is_written_since(self, tmp_path):
        """A genuine rewrite, not `os.utime` moving the mtime backwards -- that
        passed only because the comparison is `!=`, and modelled nothing that
        happens in production."""
        report = tmp_path / "report.json"
        report.write_text("{}", encoding="utf-8")
        freshness = ReportFreshness(lambda root: (Path(root) / "report.json",))
        freshness.snapshot(tmp_path)

        report.write_text('{"files": {}}', encoding="utf-8")

        assert freshness.written_since(tmp_path) == (report,)

    def test_a_file_that_did_not_exist_before_is_written_since(self, tmp_path):
        freshness = ReportFreshness(lambda root: (Path(root) / "report.json",))
        freshness.snapshot(tmp_path)
        (tmp_path / "report.json").write_text("{}", encoding="utf-8")

        assert freshness.written_since(tmp_path) == (tmp_path / "report.json",)

    def test_every_written_report_is_returned_not_just_the_newest(self, tmp_path):
        """A Maven reactor writes one report per module. Returning only the
        newest meant a run over `billing` (3 survivors) and `shipping` (clean)
        read whichever finished last and discarded the other."""
        freshness = ReportFreshness(
            lambda root: tuple(sorted(Path(root).glob("*.xml")))
        )
        freshness.snapshot(tmp_path)
        (tmp_path / "billing.xml").write_text("<a/>", encoding="utf-8")
        (tmp_path / "shipping.xml").write_text("<a/>", encoding="utf-8")

        assert len(freshness.written_since(tmp_path)) == 2


def _installed_stryker(root):
    (root / "node_modules" / "@stryker-mutator").mkdir(parents=True)
    (root / "package.json").write_text(
        '{"devDependencies": {"@stryker-mutator/vitest-runner": "1"}}',
        encoding="utf-8",
    )


class TestStrykerDoesNotReadAPreviousRunsReport:
    def test_a_crashed_run_over_a_stale_report_is_a_run_error_not_a_clean_pass(
        self, tmp_path, monkeypatch
    ):
        """The reproduced trap: `reports/` is gitignored and copied into the
        workspace, `npx stryker run` dies on a TS compile error and writes
        nothing, and the week-old all-Killed report parses clean."""
        _installed_stryker(tmp_path)
        stale = tmp_path / "reports" / "mutation" / "mutation.json"
        stale.parent.mkdir(parents=True)
        stale.write_text(STALE_STRYKER_REPORT, encoding="utf-8")

        monkeypatch.setattr(
            "mutation_gate_stryker.subprocess.run",
            lambda argv, cwd, capture_output, text, timeout: (
                subprocess.CompletedProcess(argv, 1, stdout="", stderr="TS2304")
            ),
        )

        backend = StrykerBackend()
        with pytest.warns(UserWarning):
            survivors = backend.survivors(tmp_path, ["src/a.ts"])

        assert survivors == ()
        assert backend.run_errors(tmp_path)
        assert "earlier run" in backend.run_errors(tmp_path)[0]
        # Unanswered, not a truthful zero: no report was read at all.
        assert backend.mutants_executed(tmp_path) is None

    def test_a_run_that_writes_its_own_report_is_read_normally(
        self, tmp_path, monkeypatch
    ):
        """The control: without it, the guard above could pass by the backend
        having simply stopped reading reports."""
        _installed_stryker(tmp_path)

        def fake_run(argv, cwd, capture_output, text, timeout):
            report = tmp_path / "reports" / "mutation" / "mutation.json"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(STALE_STRYKER_REPORT, encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        monkeypatch.setattr("mutation_gate_stryker.subprocess.run", fake_run)

        backend = StrykerBackend()
        survivors = backend.survivors(tmp_path, ["src/a.ts"])

        assert survivors == ()
        assert backend.run_errors(tmp_path) == ()
        # One mutant, killed. A real clean run -- and now distinguishable from
        # a run that generated none.
        assert backend.mutants_executed(tmp_path) == 1

    def test_a_repos_own_config_is_reported_as_a_scope_caveat(self, tmp_path):
        """Stryker mutates its config's `mutate` globs, not the selection. PIT
        already reported this class of fact; Stryker silently did not."""
        _installed_stryker(tmp_path)
        (tmp_path / "stryker.conf.json").write_text(
            '{"testRunner": "jest", "mutate": ["lib/**/*.js"]}', encoding="utf-8"
        )

        from mutation_gate_stryker import _scope_notes_for

        notes = _scope_notes_for(tmp_path, ["src/a.ts"])

        assert notes
        assert "own config" in notes[0]


class TestMutmutDoesNotReplayAPreviousRunsCache:
    def test_a_crashed_run_over_a_stale_stats_file_is_a_run_error(
        self, tmp_path, monkeypatch
    ):
        """`mutants/` is gitignored and copied in verbatim, so a stale
        `mutmut-stats.json` was present for a run that never got past
        collection -- and `mutmut results` replayed the previous run's cached
        statuses. Presence was never the converse of absence."""
        mutants = tmp_path / "mutants"
        mutants.mkdir()
        (mutants / "mutmut-stats.json").write_text("{}", encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\n', encoding="utf-8"
        )
        monkeypatch.setattr("mutation_gate_mutmut._mutmut_executable", lambda: "mutmut")
        monkeypatch.setattr(
            "mutation_gate_mutmut.subprocess.run",
            lambda argv, cwd, capture_output, text, timeout: (
                subprocess.CompletedProcess(
                    argv,
                    1,
                    stdout="    money.x_a__mutmut_1: killed\n",
                    stderr="collection crashed",
                )
            ),
        )

        backend = MutmutBackend()
        with pytest.warns(UserWarning):
            survivors = backend.survivors(tmp_path, ["scripts/money.py"])

        assert survivors == ()
        assert "earlier run" in backend.run_errors(tmp_path)[0]
        assert backend.mutants_executed(tmp_path) is None

    def test_a_repos_own_tool_mutmut_table_is_reported_as_a_scope_caveat(
        self, tmp_path
    ):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\n\n[tool.mutmut]\nsource_paths = ["src"]\n',
            encoding="utf-8",
        )
        from mutation_gate_mutmut import _scope_notes_for

        notes = _scope_notes_for(tmp_path, ["scripts/money.py"])

        assert notes
        assert "own [tool.mutmut]" in notes[0]


class TestTheRealWorkingTreeScenarioIsCovered:
    """The module docstring is about a stale report OVERWRITTEN IN PLACE by a
    successful run, and no test exercised that: every other freshness test
    creates a file that did not exist before, and the rewrite test moved the
    mtime backwards with `os.utime`, passing only because the comparison is
    `!=`.
    """

    def test_a_stale_report_overwritten_by_a_successful_run_is_read(
        self, tmp_path, monkeypatch
    ):
        _installed_stryker(tmp_path)
        report = tmp_path / "reports" / "mutation" / "mutation.json"
        report.parent.mkdir(parents=True)
        report.write_text(STALE_STRYKER_REPORT, encoding="utf-8")

        fresh = STALE_STRYKER_REPORT.replace('"Killed"', '"Survived"')

        def fake_run(argv, cwd, capture_output, text, timeout):
            report.write_text(fresh, encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        monkeypatch.setattr("mutation_gate_stryker.subprocess.run", fake_run)

        backend = StrykerBackend()
        survivors = backend.survivors(tmp_path, ["src/a.ts"])

        assert backend.run_errors(tmp_path) == ()
        assert [survivor.status for survivor in survivors] == ["survived"]
        assert backend.mutants_executed(tmp_path) == 1

    def test_written_since_without_a_snapshot_refuses(self, tmp_path):
        """With no before-picture every existing report looks new -- the exact
        bug. One refactor dropping the snapshot call would reopen it silently."""
        report = tmp_path / "report.json"
        report.write_text("{}", encoding="utf-8")
        freshness = ReportFreshness(lambda root: (Path(root) / "report.json",))

        with pytest.raises(RuntimeError, match="without snapshot"):
            freshness.written_since(tmp_path)
