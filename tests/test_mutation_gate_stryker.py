# tests/test_mutation_gate_stryker.py
"""Parsing a real Stryker JSON report (schemaVersion 1.0).

Stryker is the richer of the two backends — it resolves a survivor to a line,
a column, and the ids of the tests that covered it. This module is where that
precision is turned into the same Survivor shape mutmut produces, so the report
never asks an operator to reconcile two tools' output.

Fixture provenance: tests/fixtures/stryker-mutation.json was captured from a
real Stryker + vitest run (see the spike notes for 2026-07-29).
"""

import json
from pathlib import Path

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
