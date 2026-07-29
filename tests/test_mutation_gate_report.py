"""Rendering survivors into the report.

Two rules the lens cannot bend: never a percentage, and never silence about an
inconclusive result. A timed-out mutant reported as nothing reads to an operator
exactly like a clean run, which is the failure this whole gate exists to stop.
"""

import pytest

from mutation_gate import GateResult, Survivor
from mutation_gate_report import as_report_payload, render_markdown


def result_with(
    *survivors,
    unavailable=(),
    unresolved=(),
    unclaimed=(),
    baseline_failures=(),
    baseline_error="",
    run_errors=(),
    selected=1,
):
    return GateResult(
        survivors=tuple(survivors),
        unavailable=unavailable,
        unresolved=unresolved,
        unclaimed=unclaimed,
        baseline_failures=baseline_failures,
        baseline_error=baseline_error,
        run_errors=run_errors,
        selected=selected,
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

SURVIVED_MINOR = Survivor(
    artifact="skills/test-quality/SKILL.md",
    location="skills/test-quality/SKILL.md:invert:1",
    mutant="invert presence guard",
    associated_tests=("tests/test_skill.py::test_guard",),
    backend="prose",
    granularity="prose",
    status="survived_minor",
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


def test_a_survived_minor_prose_survivor_is_not_hidden_under_no_survivors():
    """Reproduces Defect A: `survived_minor` is a real survivor at a lower
    tier (the prose backend's deliberate `invert`-operator tiering), not an
    inconclusive result. It must not be swallowed by the "No survivors in
    scope" headline, and its distinguishing tier must stay visible."""
    markdown = render_markdown(result_with(SURVIVED_MINOR), scope="merge-base")

    assert "No survivors in scope" not in markdown
    assert "Survivors" in markdown
    assert "skills/test-quality/SKILL.md:invert:1" in markdown
    assert "survived_minor" in markdown


def test_a_survived_minor_prose_survivor_is_not_filed_as_inconclusive():
    markdown = render_markdown(result_with(SURVIVED_MINOR), scope="merge-base")

    assert "Inconclusive" not in markdown


def test_a_survived_minor_prose_survivor_appears_in_the_payload_survivors():
    payload = as_report_payload(result_with(SURVIVED_MINOR), scope="merge-base")

    assert len(payload["survivors"]) == 1
    assert (
        payload["survivors"][0]["location"] == "skills/test-quality/SKILL.md:invert:1"
    )
    assert payload["survivors"][0]["status"] == "survived_minor"
    assert payload["inconclusive"] == []


def test_a_run_error_is_named_in_the_markdown_as_one_rollup():
    """Reproduces the reviewer's follow-up finding: a partition's tool run
    that did not complete (e.g. mutmut's stats collection crashing before a
    single mutant executed) must reach the operator as one named fact, the
    same way `baseline_error` already does for a broken baseline -- not be
    silently dropped, and not be re-expanded into per-mutant rows here."""
    markdown = render_markdown(
        result_with(
            run_errors=("mutmut run did not complete; 4298 mutants not checked",)
        ),
        scope="merge-base",
    )

    assert "mutmut run did not complete; 4298 mutants not checked" in markdown


def test_a_run_error_is_carried_in_the_json_payload_too():
    payload = as_report_payload(
        result_with(
            run_errors=("mutmut run did not complete; 4298 mutants not checked",)
        ),
        scope="merge-base",
    )

    assert payload["run_errors"] == [
        "mutmut run did not complete; 4298 mutants not checked"
    ]


def test_no_run_errors_does_not_render_a_run_errors_section():
    markdown = render_markdown(result_with(), scope="merge-base")

    assert "did not complete" not in markdown


def test_a_run_error_with_a_large_multiline_tool_dump_renders_bounded():
    """Reproduces the size-bomb defect: mutmut's raw run_errors message can
    carry a multi-KB tool dump as real newlines (a traceback plus one
    `not checked` line per uncollected mutant). render_markdown must not
    splice that verbatim -- the short summary must survive in full, the raw
    dump must be bounded to a head/tail excerpt of REAL lines inside a
    fenced block (not one giant repr()-style line), and the full size and
    line count must be stated so nothing is hidden by accident."""
    summary = "mutmut run did not complete in /repo -- 400 mutants not checked"
    dump_lines = [f"    money.x_discount__mutmut_{i}: not checked" for i in range(400)]
    raw_dump = "\n".join(dump_lines)
    message = f"{summary}\n{raw_dump}"

    markdown = render_markdown(result_with(run_errors=(message,)), scope="merge-base")

    assert summary in markdown
    assert "%" not in markdown
    # Bounded: not all 400 raw dump lines survive verbatim.
    assert markdown.count("not checked") < 400
    # Real lines, not a repr()-collapsed single giant line.
    assert "\\n" not in markdown
    longest_line = max(len(line) for line in markdown.splitlines())
    assert longest_line < 500
    # Nothing hidden by accident: size and mutant count stated.
    assert str(len(raw_dump)) in markdown or str(len(dump_lines)) in markdown
    assert "400" in markdown
    assert "elided" in markdown or "truncated" in markdown


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


def test_the_json_payload_carries_a_broken_baseline_too():
    """A baseline that never ran is a different, more urgent fact than an
    empty `baseline_failures` -- the machine-readable payload must not
    collapse the two."""
    payload = as_report_payload(
        result_with(baseline_error="uv run pytest exited 2: collection error"),
        scope="merge-base",
    )

    assert payload["baseline_error"] == "uv run pytest exited 2: collection error"
    assert payload["baseline_failures"] == []


def test_a_broken_baseline_is_stated_not_reduced_to_a_warning():
    """Reproduces the reviewer's live finding: a collection error during the
    baseline run must reach the rendered markdown, distinguishing "the
    baseline was clean" from "the baseline never ran" -- not degrade to a
    warning only visible to something that captures Python warnings."""
    markdown = render_markdown(
        result_with(baseline_error="uv run pytest exited 2: collection error"),
        scope="merge-base",
    )

    assert "did not complete" in markdown
    assert "collection error" in markdown


def test_a_clean_baseline_does_not_render_the_broken_baseline_section():
    markdown = render_markdown(result_with(), scope="merge-base")

    assert "did not complete" not in markdown


class TestARunWhereNothingWorkedDoesNotRenderAsACleanRun:
    """The renderer printed "No survivors in scope." unconditionally on an
    empty survivor list -- including directly beneath a "Baseline did not
    complete" banner and beneath "Run errors". Silence read as a pass, in the
    renderer of the lens built to stop exactly that.
    """

    def test_no_survivors_in_scope_is_not_claimed_under_a_broken_baseline(self):
        markdown = render_markdown(
            result_with(baseline_error="uv run pytest exited 2"), scope="merge-base"
        )

        assert "No survivors in scope." not in markdown
        assert "did not complete" in markdown

    def test_no_survivors_in_scope_is_not_claimed_under_run_errors(self):
        markdown = render_markdown(
            result_with(run_errors=("mutmut crashed before any mutant ran",)),
            scope="merge-base",
        )

        assert "No survivors in scope." not in markdown

    def test_an_incomplete_run_says_so_where_the_survivor_list_would_be(self):
        markdown = render_markdown(
            result_with(run_errors=("mutmut crashed",)), scope="merge-base"
        )

        assert "not a clean result" in markdown

    def test_a_genuinely_clean_run_still_says_no_survivors_in_scope(self):
        markdown = render_markdown(result_with(), scope="merge-base")

        assert "No survivors in scope." in markdown


class TestNothingToDoIsDistinguishableFromNothingFound:
    """A clean tree under `--scope working-tree` selects zero files and used to
    emit an all-empty payload with no signal that nothing was ever looked at.
    """

    def test_the_markdown_carries_how_many_files_were_selected(self):
        markdown = render_markdown(result_with(selected=7), scope="merge-base")

        assert "7" in markdown
        assert "%" not in markdown

    def test_a_zero_file_scope_says_nothing_was_selected_not_nothing_found(self):
        markdown = render_markdown(result_with(selected=0), scope="working-tree")

        assert "No survivors in scope." not in markdown
        assert "no files were selected" in markdown.lower()

    def test_the_json_payload_carries_the_selected_count_too(self):
        payload = as_report_payload(result_with(selected=0), scope="working-tree")

        assert payload["selected"] == 0

    def test_run_gate_reports_the_number_of_paths_it_was_given(self, tmp_path):
        from mutation_gate import run_gate

        result = run_gate(tmp_path, ["a.py", "b.ts", "c.md", "d.png"], [])

        assert result.selected == 4


@pytest.mark.covers(
    "skills/test-quality/references/report-template.md", section="Mutation gate"
)
def test_the_template_carries_the_markers_the_gate_writes_between(covered_slice):
    assert "<!-- mutation-gate:begin -->" in covered_slice
    assert "<!-- mutation-gate:end -->" in covered_slice
    assert "Never a score" in covered_slice
    # Marker presence and the score rule both survive an inversion that flips
    # this section's load-bearing directive ("the script does the writing,
    # never the agent" -> "always the agent"), which would licence exactly the
    # hand-pasted section the CLI splice exists to replace. Assert the
    # directive itself, not just the keywords around it.
    normalized = " ".join(covered_slice.split())
    assert "never the agent" in normalized


def test_gate_result_refuses_positional_construction():
    """Seven tuple-shaped fields, several interchangeable at the type level:
    `unresolved` and `unclaimed` are both tuple[str, ...], as are
    `baseline_failures` and `run_errors`. Swapping any pair positionally would
    silently misfile an entire category of finding and type-check clean.
    Keyword-only construction makes that transposition impossible.
    """
    with pytest.raises(TypeError):
        GateResult((), (), (), ())
