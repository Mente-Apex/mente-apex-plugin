"""Rendering survivors into the report.

Two rules the lens cannot bend: never a percentage, and never silence about an
inconclusive result. A timed-out mutant reported as nothing reads to an operator
exactly like a clean run, which is the failure this whole gate exists to stop.
"""

import pytest

from mutation_gate import GateResult, Survivor
from mutation_gate_report import as_report_payload, render_markdown


def result_with(
    *survivors, unavailable=(), unresolved=(), unclaimed=(), baseline_failures=()
):
    return GateResult(
        survivors=tuple(survivors),
        unavailable=unavailable,
        unresolved=unresolved,
        unclaimed=unclaimed,
        baseline_failures=baseline_failures,
    )


SURVIVED = Survivor(
    artifact="src/money.py",
    location="money.x_discount",
    mutant="money.x_discount__mutmut_1",
    mutant_diff="-    if is_member and total > 100:\n+    if is_member or total > 100:",
    associated_tests=("tests/test_money.py::test_member_discount",),
    backend="mutmut",
    granularity="function",
)

TIMED_OUT = Survivor(
    artifact="src/money.js",
    location="src/money.js:3:12",
    mutant="ArithmeticOperator -> total / 0.9",
    associated_tests=("member over threshold gets ten percent off",),
    backend="stryker",
    granularity="line",
    status="timeout",
)


def test_names_the_test_and_the_mutant_not_a_score():
    markdown = render_markdown(result_with(SURVIVED), scope="merge-base")

    assert "tests/test_money.py::test_member_discount" in markdown
    assert "money.x_discount__mutmut_1" in markdown
    assert "%" not in markdown


def test_states_the_granularity_each_backend_supplied():
    markdown = render_markdown(result_with(SURVIVED), scope="merge-base")

    assert "function" in markdown
    assert "mutmut" in markdown


def test_a_timeout_is_rendered_as_inconclusive_not_as_a_survivor():
    markdown = render_markdown(result_with(TIMED_OUT), scope="merge-base")

    assert "Inconclusive" in markdown
    assert "src/money.js:3:12" in markdown


def test_an_unavailable_tool_is_stated_with_its_install_command():
    markdown = render_markdown(
        result_with(unavailable=(("js", "npm install -D @stryker-mutator/core"),)),
        scope="merge-base",
    )

    assert "not available" in markdown
    assert "npm install -D @stryker-mutator/core" in markdown


def test_the_scope_that_produced_the_result_is_recorded():
    markdown = render_markdown(result_with(SURVIVED), scope="full")

    assert "full" in markdown


def test_a_clean_run_says_so_rather_than_rendering_an_empty_section():
    markdown = render_markdown(result_with(), scope="merge-base")

    assert "No survivors" in markdown


def test_an_unclaimed_file_is_named_and_distinguished_from_unresolved():
    markdown = render_markdown(
        result_with(unclaimed=("api/money.py",)), scope="merge-base"
    )

    assert "Unclaimed" in markdown
    assert "api/money.py" in markdown
    assert "Unresolved" not in markdown


def test_an_unresolved_file_is_named_and_distinguished_from_unclaimed():
    markdown = render_markdown(
        result_with(unresolved=("assets/logo.png",)), scope="merge-base"
    )

    assert "Unresolved" in markdown
    assert "assets/logo.png" in markdown
    assert "Unclaimed" not in markdown


def test_the_json_payload_carries_baseline_failures_too():
    """Not just the markdown -- the machine-readable payload the CLI actually
    prints is exactly as capable of silently dropping this signal."""
    payload = as_report_payload(
        result_with(baseline_failures=("tests/test_a.py::test_flaky",)),
        scope="merge-base",
    )

    assert payload["baseline_failures"] == ["tests/test_a.py::test_flaky"]


def test_baseline_failures_are_stated_not_swallowed():
    markdown = render_markdown(
        result_with(baseline_failures=("tests/test_a.py::test_flaky",)),
        scope="merge-base",
    )

    assert "already failing" in markdown
    assert "tests/test_a.py::test_flaky" in markdown


@pytest.mark.covers(
    "skills/test-quality/references/report-template.md", section="Mutation gate"
)
def test_the_template_carries_the_markers_the_gate_writes_between(covered_slice):
    assert "<!-- mutation-gate:begin -->" in covered_slice
    assert "<!-- mutation-gate:end -->" in covered_slice
    assert "Never a score" in covered_slice
