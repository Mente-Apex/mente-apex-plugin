"""Mutation score as a standing sensor, not only an apply gate (issue #119).

The gate's native output is a **proof obligation** attached to one edit: located
survivors, read as pass/fail on a specific risky change. A score is the other
thing mutation testing is for — a **sensor**, a health reading on a whole
codebase alongside coverage, cyclomatic complexity and module size.

Same raw material, different question. So this aggregates and never replaces:
every survivor stays enumerated, and the gate's verdict is untouched.

The interesting half is when a score must NOT be produced. A number is read as
health, so an unsupportable one is worse than none — and 0/0 renders as either
0% or 100% depending on which way you round a lie.
"""

import pytest

from mutation_gate import BackendRun, GateResult, Survivor
from mutation_gate_report import as_report_payload, mutation_score, render_markdown


def run_with(**overrides):
    fields = {
        "survivors": (),
        "unavailable": (),
        "unresolved": (),
        "unclaimed": (),
        "selected": 3,
        "backend_runs": (
            BackendRun(
                stack="python", tool="mutmut", mutants_executed=10, counts_mutants=True
            ),
        ),
    }
    fields.update(overrides)
    return GateResult(**fields)


def survivor(status="survived", artifact="a.py"):
    return Survivor(
        artifact=artifact,
        location=f"{artifact}:1",
        mutant="x -> y",
        associated_tests=(),
        backend="mutmut",
        granularity="line",
        status=status,
    )


class TestTheReading:
    def test_a_clean_sweep_scores_one_hundred(self):
        assert mutation_score(run_with(survivors=())) == 100.0

    def test_each_survivor_comes_off_the_score(self):
        result = run_with(survivors=(survivor(), survivor(artifact="b.py")))

        assert mutation_score(result) == 80.0  # 8 killed of 10

    def test_it_rounds_to_one_decimal_rather_than_pretending_to_precision(self):
        result = run_with(
            survivors=(survivor(),),
            backend_runs=(
                BackendRun(
                    stack="python",
                    tool="mutmut",
                    mutants_executed=3,
                    counts_mutants=True,
                ),
            ),
        )

        assert mutation_score(result) == 66.7

    def test_several_backends_aggregate_into_one_reading(self):
        """A polyglot repo's score is over everything that ran, not per stack —
        the sensor answers "how healthy is this codebase"."""
        result = run_with(
            survivors=(survivor(),),
            backend_runs=(
                BackendRun(
                    stack="python",
                    tool="mutmut",
                    mutants_executed=10,
                    counts_mutants=True,
                ),
                BackendRun(
                    stack="js", tool="stryker", mutants_executed=10, counts_mutants=True
                ),
            ),
        )

        assert mutation_score(result) == 95.0


class TestWhenThereMustBeNoNumber:
    """A score is read as health. An unsupportable one is worse than none."""

    def test_a_backend_that_cannot_count_makes_the_denominator_a_guess(self):
        result = run_with(
            backend_runs=(
                BackendRun(
                    stack="python",
                    tool="mutmut",
                    mutants_executed=None,
                    counts_mutants=True,
                ),
            )
        )

        assert mutation_score(result) is None

    def test_no_counting_backend_at_all_yields_no_score(self):
        result = run_with(backend_runs=())

        assert mutation_score(result) is None

    def test_zero_executed_is_not_zero_percent_and_not_a_hundred(self):
        """0/0 renders as either, and both are lies about a run that tested
        nothing. This is the `Nothing selected` case wearing a number."""
        result = run_with(
            backend_runs=(
                BackendRun(
                    stack="python",
                    tool="mutmut",
                    mutants_executed=0,
                    counts_mutants=True,
                ),
            )
        )

        assert mutation_score(result) is None

    def test_a_zero_score_is_a_real_reading_and_is_not_suppressed(self):
        """0.0 and None are different facts: "every mutant survived" is the
        worst possible suite, and it must not be hidden by the guard that hides
        "we could not tell"."""
        result = run_with(
            survivors=tuple(
                survivor(artifact=f"module_{index}.py") for index in range(10)
            )
        )

        assert mutation_score(result) == 0.0


class TestWhatCountsAsKilled:
    def test_a_mutant_that_never_ran_is_not_a_survivor(self):
        """`no_op_mutant` and `declaration_error` were never executed, so they
        are not "the suite failed to kill this" — counting them would score a
        tool's limitation as a test-suite defect."""
        result = run_with(survivors=(survivor(status="no_op_mutant"),))

        assert mutation_score(result) == 100.0

    @pytest.mark.parametrize(
        "status",
        ["survived", "no_coverage", "timeout", "non_viable", "unreliable_baseline"],
    )
    def test_every_executed_row_counts_against_the_score(self, status):
        """The gate records a row only for a mutant it did not cleanly kill, so
        any EXECUTED row is a mutant the suite did not kill.

        Counting only the literal `survived` status scored the other four as
        kills: 75 uncovered mutants out of 100 reported 100% — a perfect reading
        on code nothing tests. `no_coverage` especially: no test touched it.
        """
        result = run_with(survivors=(survivor(status=status),))

        assert mutation_score(result) == 90.0

    def test_an_inconclusive_row_understates_health_rather_than_overstating_it(self):
        """`unreliable_baseline` proves nothing in either direction, so it has to
        fall one way or the other. It falls against the score, because this
        number is read as reassurance and the survivors stay enumerated with
        their statuses for anyone who needs the distinction."""
        clean = run_with(survivors=())
        inconclusive = run_with(survivors=(survivor(status="unreliable_baseline"),))

        assert mutation_score(inconclusive) < mutation_score(clean)


class TestItReachesBothConsumers:
    def test_the_markdown_carries_it_for_the_human(self):
        markdown = render_markdown(run_with(survivors=(survivor(),)), scope="full")

        assert "**Mutation score:** 90.0% killed" in markdown

    def test_the_payload_carries_it_for_the_agent(self):
        payload = as_report_payload(run_with(survivors=(survivor(),)), scope="full")

        assert payload["mutation_score"] == 90.0

    def test_an_unsupportable_score_is_omitted_from_the_markdown_not_faked(self):
        markdown = render_markdown(run_with(backend_runs=()), scope="full")

        assert "Mutation score" not in markdown

    def test_the_payload_says_none_rather_than_dropping_the_key(self):
        """The agent parses the payload; a missing key and a null mean different
        things to code reading it."""
        payload = as_report_payload(run_with(backend_runs=()), scope="full")

        assert payload["mutation_score"] is None

    def test_the_survivors_are_still_enumerated_alongside_the_score(self):
        """The sensor is added to the gate, never in place of it: a score with
        the survivors swallowed would be the "87%" the issue explicitly did not
        want."""
        markdown = render_markdown(run_with(survivors=(survivor(),)), scope="full")

        assert "a.py:1" in markdown
