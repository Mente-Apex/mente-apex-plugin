"""Parsing real mutmut 3.6.0 output.

Pinned against output captured verbatim from a live run, so a schema change in
mutmut fails loudly here instead of silently reporting no survivors — the worst
possible failure for a tool whose whole job is to report survivors.
"""

import json
from pathlib import Path

from mutation_gate_mutmut import survivors_from_output

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
