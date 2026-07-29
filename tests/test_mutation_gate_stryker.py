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
from pathlib import Path

import pytest

from mutation_gate_stryker import default_config, survivors_from_report

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
