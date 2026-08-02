"""A run that never mutated anything must not render, or exit, as a clean run.

The gate's whole purpose is to refuse silence-as-a-pass, and it had five ways
left to produce exactly that: an unavailable tool, an unclaimed stack, a
backend that applied zero mutants, a backend that does not say how many it
applied, and a run whose every mutant came back inconclusive. All five
reported "No survivors in scope." over code nothing had touched.

These are the guards. Each one names the specific vacuous run it forbids.
"""

from mutation_gate import (
    BackendRun,
    GateResult,
    Survivor,
    exit_code_for,
    unverified_reasons,
)
from mutation_gate_report import as_report_payload, render_markdown

CLEAN_SENTENCE = "No survivors in scope."


def result_with(**overrides):
    """A run that looked at one file with one working backend and found nothing.

    The genuinely-clean baseline every test below perturbs by exactly one fact.
    """
    fields = {
        "survivors": (),
        "unavailable": (),
        "unresolved": (),
        "unclaimed": (),
        "selected": 1,
        "backend_runs": (
            BackendRun(
                stack="python", tool="mutmut", mutants_executed=12, counts_mutants=True
            ),
        ),
    }
    fields.update(overrides)
    return GateResult(**fields)


def inconclusive(status):
    return Survivor(
        artifact="a.py",
        location="a.py:1",
        mutant="x -> y",
        associated_tests=(),
        backend="stryker",
        granularity="line",
        status=status,
    )


class TestTheGenuinelyCleanRunStillReadsAsClean:
    """The control. Without this, every assertion below could pass by the
    renderer having simply stopped saying the clean sentence at all."""

    def test_it_prints_the_clean_sentence(self):
        assert CLEAN_SENTENCE in render_markdown(result_with(), scope="merge-base")

    def test_it_has_no_unverified_reasons(self):
        assert unverified_reasons(result_with()) == ()

    def test_it_exits_zero(self):
        assert exit_code_for(result_with()) == 0


class TestARunThatNeverMutatedTheFilesIsNotClean:
    def test_an_unavailable_tool_does_not_render_as_clean(self):
        """Twelve files selected, mutmut not installed, zero mutants ever
        generated -- and the headline said the scope was clean."""
        markdown = render_markdown(
            result_with(
                unavailable=(("python", "uv add --dev mutmut"),),
                backend_runs=(),
                selected=12,
            ),
            scope="merge-base",
        )

        assert CLEAN_SENTENCE not in markdown
        assert "did not verify its scope" in markdown
        assert "never mutated" in markdown

    def test_an_unclaimed_stack_does_not_render_as_clean(self):
        markdown = render_markdown(
            result_with(unclaimed=("a.ts",), backend_runs=(), selected=1),
            scope="merge-base",
        )

        assert CLEAN_SENTENCE not in markdown
        assert "did not verify its scope" in markdown

    def test_a_backend_that_applied_no_mutants_does_not_render_as_clean(self):
        """A `mutate` glob matching nothing, or source paths the parser choked
        on: the tool ran, wrote a report, and tested not one line."""
        markdown = render_markdown(
            result_with(
                backend_runs=(
                    BackendRun(
                        stack="js",
                        tool="stryker",
                        mutants_executed=0,
                        counts_mutants=True,
                    ),
                ),
            ),
            scope="merge-base",
        )

        assert CLEAN_SENTENCE not in markdown
        assert "applied no mutants" in markdown

    def test_a_backend_that_does_not_report_a_count_does_not_render_as_clean(self):
        """`None` is not `0`: the question was never answered, rather than
        answered badly. Either way the empty survivor list proves nothing."""
        markdown = render_markdown(
            result_with(
                backend_runs=(
                    BackendRun(
                        stack="js",
                        tool="stryker",
                        mutants_executed=None,
                        counts_mutants=True,
                    ),
                ),
            ),
            scope="merge-base",
        )

        assert CLEAN_SENTENCE not in markdown
        assert "could not say how many mutants" in markdown

    def test_an_all_inconclusive_run_does_not_render_as_clean(self):
        """Stryker's coverage analysis misfires and every mutant comes back
        NoCoverage: nothing was killed, nothing survived, nothing was tested."""
        markdown = render_markdown(
            result_with(
                survivors=(inconclusive("no_coverage"), inconclusive("no_coverage")),
                backend_runs=(
                    BackendRun(
                        stack="js",
                        tool="stryker",
                        mutants_executed=2,
                        counts_mutants=True,
                    ),
                ),
            ),
            scope="merge-base",
        )

        assert CLEAN_SENTENCE not in markdown
        assert "inconclusive" in markdown
        assert "nothing was actually verified" in markdown

    def test_a_partially_inconclusive_run_is_still_clean(self):
        """Two of ten mutants timed out and the other eight were killed. That
        is a real, if partial, verification -- not a vacuous run. Without this,
        the guard above would be free to condemn every run with any
        inconclusive result in it."""
        markdown = render_markdown(
            result_with(
                survivors=(inconclusive("timeout"), inconclusive("timeout")),
                backend_runs=(
                    BackendRun(
                        stack="js",
                        tool="stryker",
                        mutants_executed=10,
                        counts_mutants=True,
                    ),
                ),
            ),
            scope="merge-base",
        )

        assert CLEAN_SENTENCE in markdown

    def test_nothing_selected_still_says_nothing_to_do_not_nothing_found(self):
        """An empty scope is honest, and keeps its own distinct sentence rather
        than being swept in with the runs that failed to look."""
        markdown = render_markdown(
            result_with(selected=0, backend_runs=()), scope="working-tree"
        )

        assert CLEAN_SENTENCE not in markdown
        assert "Nothing selected" in markdown


class TestTheVerdictReachesEveryConsumer:
    """The markdown is for a human, the JSON for the analyzer agent and the
    exit code for a shell. A verdict that reaches only one of the three leaves
    the other two reading a vacuous run as a pass."""

    def test_the_exit_code_separates_a_finding_from_an_unverified_run(self):
        survived = Survivor(
            artifact="a.py",
            location="a.py:1",
            mutant="x -> y",
            associated_tests=(),
            backend="mutmut",
            granularity="line",
        )

        assert exit_code_for(result_with(survivors=(survived,))) == 1
        assert exit_code_for(result_with(unclaimed=("a.ts",))) == 2

    def test_the_json_payload_carries_the_reasons_and_the_mutant_counts(self):
        payload = as_report_payload(
            result_with(
                backend_runs=(
                    BackendRun(
                        stack="js",
                        tool="stryker",
                        mutants_executed=0,
                        counts_mutants=True,
                    ),
                ),
            ),
            scope="merge-base",
        )

        assert payload["backend_runs"] == [
            {"stack": "js", "tool": "stryker", "mutants_executed": 0}
        ]
        assert any(
            "applied no mutants" in reason for reason in payload["unverified_reasons"]
        )

    def test_the_mutant_count_is_on_the_headline_beside_the_file_count(self):
        """12 files selected and 0 mutants executed is a vacuous run, and read
        identically to a real one until this number was on the page."""
        markdown = render_markdown(result_with(selected=12), scope="merge-base")

        assert "**Files selected:** 12" in markdown
        assert "**Mutants executed:** mutmut: 12" in markdown


class TestTheRunErrorDumpStaysBounded:
    def test_an_unverified_reason_carries_the_summary_not_the_whole_dump(self):
        """`run_errors` messages can carry a multi-KB tool dump. The report
        renders that once, bounded, in its own section; the reason line must
        not splice it back in unbounded."""
        dump = "\n".join(f"mutant_{index}: not checked" for index in range(400))
        message = f"mutmut run did not complete -- 400 mutants not checked\n{dump}"

        reasons = unverified_reasons(result_with(run_errors=(message,)))

        assert len(reasons) == 1
        assert "400 mutants not checked" in reasons[0]
        assert "mutant_399" not in reasons[0]


class TestSurvivorDiffsAreBounded:
    def test_a_huge_diff_is_clipped_in_the_markdown_but_whole_in_the_json(self):
        """`run_errors` dumps were carefully clipped; survivor diffs were
        emitted in full, once per survivor."""
        huge_diff = "\n".join(f"-    line {index}" for index in range(200))
        survivor = Survivor(
            artifact="a.py",
            location="a.py:1",
            mutant="x -> y",
            associated_tests=(),
            backend="mutmut",
            granularity="line",
            mutant_diff=huge_diff,
        )

        result = result_with(survivors=(survivor,))
        markdown = render_markdown(result, scope="merge-base")

        assert "line 199" not in markdown
        assert "elided" in markdown
        assert (
            as_report_payload(result, scope="merge-base")["survivors"][0]["diff"]
            == huge_diff
        )
