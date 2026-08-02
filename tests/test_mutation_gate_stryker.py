# tests/test_mutation_gate_stryker.py
"""Parsing a real Stryker JSON report (schemaVersion 1.0).

Stryker is the richer of the two backends — it resolves a survivor to a line,
a column, and the ids of the tests that covered it. This module is where that
precision is turned into the same Survivor shape mutmut produces, so the report
never asks an operator to reconcile two tools' output.

Fixture provenance: tests/fixtures/stryker-mutation.json was captured from a
real Stryker + vitest run (see the spike notes for 2026-07-29), except mutants
"3" (CompileError) and "4" (NoCoverage), which were added by hand in fix round
1 to cover statuses the captured run happened not to produce — shaped like
real Stryker mutant records, not invented fields.
"""

import json
import subprocess
from pathlib import Path

import pytest

from mutation_gate_stryker import StrykerBackend, default_config, survivors_from_report

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_report():
    return json.loads((FIXTURES / "stryker-mutation.json").read_text(encoding="utf-8"))


def test_reports_survivors_and_ignores_killed_mutants():
    survivors = survivors_from_report(load_report())

    assert [s.mutant for s in survivors if s.status == "survived"] == [
        "ConditionalExpression -> true"
    ]


def test_resolves_covering_test_ids_to_names():
    survivors = survivors_from_report(load_report())
    survived = next(s for s in survivors if s.status == "survived")

    assert survived.associated_tests == (
        "member over threshold gets ten percent off",
        "vacuous guard asserts nothing real",
    )


def test_declares_line_granularity_and_a_precise_location():
    survivors = survivors_from_report(load_report())
    survived = next(s for s in survivors if s.status == "survived")

    assert survived.granularity == "line"
    assert survived.location == "src/money.js:2:7"
    assert survived.backend == "stryker"


def test_a_timeout_is_inconclusive_not_a_pass():
    survivors = survivors_from_report(load_report())

    timed_out = [s for s in survivors if s.status == "timeout"]
    assert len(timed_out) == 1
    assert timed_out[0].location == "src/money.js:3:12"


def test_generated_config_requests_per_test_coverage():
    config = default_config(mutate_globs=["src/**/*.js"], test_runner="vitest")

    assert config["coverageAnalysis"] == "perTest"
    assert config["testRunner"] == "vitest"
    assert config["mutate"] == ["src/**/*.js"]
    assert "json" in config["reporters"]


def test_killed_mutant_is_dropped():
    survivors = survivors_from_report(load_report())

    assert not any(s.mutant.startswith("BlockStatement") for s in survivors)


def test_a_compile_error_lands_as_inconclusive_not_dropped():
    survivors = survivors_from_report(load_report())

    compile_errors = [s for s in survivors if s.status == "compile_error"]
    assert len(compile_errors) == 1
    assert compile_errors[0].location == "src/money.js:4:5"


def test_no_coverage_lands_as_inconclusive_not_dropped():
    survivors = survivors_from_report(load_report())

    no_coverage = [s for s in survivors if s.status == "no_coverage"]
    assert len(no_coverage) == 1
    assert no_coverage[0].location == "src/money.js:5:3"


def test_an_unrecognized_status_fails_loudly_instead_of_vanishing():
    report = load_report()
    report["files"]["src/money.js"]["mutants"].append(
        {
            "id": "5",
            "mutatorName": "FutureMutator",
            "replacement": "??",
            "status": "SomeFutureStatus",
            "static": False,
            "coveredBy": [],
            "location": {
                "start": {"line": 6, "column": 1},
                "end": {"line": 6, "column": 2},
            },
        }
    )

    with pytest.raises(ValueError, match="SomeFutureStatus"):
        survivors_from_report(report)


def test_a_covering_test_id_missing_from_test_files_is_surfaced_not_swallowed():
    report = load_report()
    report["files"]["src/money.js"]["mutants"][0]["coveredBy"] = ["0", "1", "99"]

    with pytest.warns(UserWarning, match="99"):
        survivors = survivors_from_report(report)

    survived = next(s for s in survivors if s.status == "survived")
    assert survived.associated_tests == (
        "member over threshold gets ten percent off",
        "vacuous guard asserts nothing real",
    )


def test_available_sees_an_installed_stryker_through_a_real_default_scope_workspace(
    tmp_path,
):
    """Review round 1, Critical 2. `run_gate` always passes `StrykerBackend`
    the SCRATCH WORKSPACE, never the operator's real tree. For the default
    merge-base/full scope that workspace comes from `git worktree add`, which
    checks out tracked files only -- `node_modules` is virtually always
    gitignored, so `.available()` would previously always see it as absent,
    even on a repo with Stryker genuinely installed. This runs the real
    `scratch_workspace` (not a fake) against a repo with an untracked
    `node_modules/@stryker-mutator`, so it fails for the same reason a real
    operator's run would have.
    """
    from mutation_gate_workspace import scratch_workspace

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    (tmp_path / "money.js").write_text("export const x = 1;\n", encoding="utf-8")
    # Tracked, so it reaches the worktree: availability now also requires the
    # repo to be configurable (a declared runner plugin), not merely to have
    # Stryker installed -- see TestAvailabilityMeansItCanActuallyRun. The
    # untracked `node_modules` below is still what this test is really about.
    (tmp_path / "package.json").write_text(
        json.dumps({"devDependencies": {"@stryker-mutator/vitest-runner": "^8"}}),
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    (tmp_path / "node_modules" / "@stryker-mutator").mkdir(parents=True)

    backend = StrykerBackend()
    with scratch_workspace(tmp_path) as workspace:
        assert backend.available(workspace) is True


def test_a_missing_report_after_a_run_is_a_run_error_not_silent_success(
    tmp_path, monkeypatch
):
    """Stryker's equivalent of mutmut's crashed-collection case: `stryker
    run` exits non-zero and no report ever lands at
    reports/mutation/mutation.json. Previously this surfaced only as a
    stderr-only `warnings.warn` and an empty survivor list -- indistinguishable
    from a genuinely clean run. It must now be a named `run_errors()` fact,
    the same standard `mutation_gate_mutmut.MutmutBackend` now holds for its
    own equivalent failure.
    """
    monkeypatch.setattr(
        "mutation_gate_stryker.subprocess.run",
        lambda argv, cwd, capture_output, text, timeout: subprocess.CompletedProcess(
            argv, 1, stdout="", stderr="stryker crashed"
        ),
    )

    backend = StrykerBackend()
    with pytest.warns(UserWarning):
        survivors = backend.survivors(tmp_path, ["src/money.ts"])

    assert survivors == ()
    run_errors = backend.run_errors(tmp_path)
    assert len(run_errors) == 1
    assert "did not complete" in run_errors[0] or "no report" in run_errors[0]


def test_run_errors_defaults_to_empty_before_survivors_is_ever_called():
    assert StrykerBackend().run_errors("/irrelevant/repo/root") == ()


def _installed_stryker(root, runner="@stryker-mutator/vitest-runner"):
    (root / "node_modules" / "@stryker-mutator").mkdir(parents=True)
    (root / "package.json").write_text(
        json.dumps({"devDependencies": {"@stryker-mutator/core": "^8", runner: "^8"}}),
        encoding="utf-8",
    )


def _stryker_run_that_fails(monkeypatch):
    monkeypatch.setattr(
        "mutation_gate_stryker.subprocess.run",
        lambda argv, cwd, capture_output, text, timeout: subprocess.CompletedProcess(
            argv, 1, stdout="", stderr=""
        ),
    )


class TestAvailabilityMeansItCanActuallyRun:
    """`default_config` had no caller outside tests: nothing ever generated a
    `stryker.conf.json`. `available()` checked only for the `@stryker-mutator`
    directory, so a repo with Stryker INSTALLED BUT UNCONFIGURED passed the
    check, `npx stryker run` failed, and the whole JS partition degraded to a
    run error the operator could do nothing about -- `install_hint` never even
    mentioned the config.
    """

    def test_an_unconfigured_repo_gets_a_config_generated_from_its_selection(
        self, tmp_path, monkeypatch
    ):
        _installed_stryker(tmp_path)
        _stryker_run_that_fails(monkeypatch)

        with pytest.warns(UserWarning):
            StrykerBackend().survivors(tmp_path, ["src/cart.ts", "src/money.ts"])

        config = json.loads(
            (tmp_path / "stryker.conf.json").read_text(encoding="utf-8")
        )
        assert config["mutate"] == ["src/cart.ts", "src/money.ts"]
        assert config["coverageAnalysis"] == "perTest"
        assert config["testRunner"] == "vitest"

    def test_a_repo_that_configures_stryker_itself_is_left_alone(
        self, tmp_path, monkeypatch
    ):
        """Mirrors `_configure_source_paths`: a real configuration decision by
        the operator beats a derived one.
        """
        _installed_stryker(tmp_path)
        theirs = json.dumps({"testRunner": "jest", "mutate": ["lib/**/*.js"]})
        (tmp_path / "stryker.conf.json").write_text(theirs, encoding="utf-8")
        _stryker_run_that_fails(monkeypatch)

        with pytest.warns(UserWarning):
            StrykerBackend().survivors(tmp_path, ["src/cart.ts"])

        assert (tmp_path / "stryker.conf.json").read_text(encoding="utf-8") == theirs

    def test_installed_but_with_no_runner_plugin_is_not_available(self, tmp_path):
        (tmp_path / "node_modules" / "@stryker-mutator").mkdir(parents=True)
        (tmp_path / "package.json").write_text(
            json.dumps({"devDependencies": {"@stryker-mutator/core": "^8"}}),
            encoding="utf-8",
        )

        assert StrykerBackend().available(tmp_path) is False

    def test_a_repo_with_its_own_config_is_available_without_a_known_runner(
        self, tmp_path
    ):
        """The operator already declared how Stryker runs; the gate does not
        second-guess a runner it does not recognise.
        """
        (tmp_path / "node_modules" / "@stryker-mutator").mkdir(parents=True)
        (tmp_path / "stryker.conf.json").write_text("{}", encoding="utf-8")

        assert StrykerBackend().available(tmp_path) is True

    def test_a_jest_runner_is_detected_as_well_as_vitest(self, tmp_path):
        _installed_stryker(tmp_path, runner="@stryker-mutator/jest-runner")

        assert StrykerBackend().available(tmp_path) is True

    def test_the_install_hint_names_the_config_not_only_the_packages(self, tmp_path):
        hint = StrykerBackend().install_hint(tmp_path)

        assert "runner" in hint
        assert "stryker.conf.json" in hint
