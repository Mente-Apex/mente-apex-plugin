"""The sweep a stand-alone audit can actually reach (issue #149).

`--scope merge-base` is the right default and stays one: it is stable under an
operator committing mid-audit, and whole-repo mutation is far too slow to be
anyone's default in an interactive skill. But on a stand-alone audit of an
untouched tree that scope resolves to an empty diff, so the sweep selects zero
files -- and born-vacuous tests, the one thing only this sweep can find, live
exactly there. The mechanism was inert precisely where the skill advertised it.

The reachable path (`--scope full --paths <subtree>`) already exists. What was
missing is everything that keeps it reachable: a gate that says so when its
selection comes up empty, and prose contracts nothing pins. An empty selection
stays exit 0 and stays out of `unverified_reasons` -- nothing broke, so calling
it unverified would be a lie in the other direction. It just has to stop reading
like a finished sweep.
"""

from pathlib import Path

import pytest

from mutation_gate import GateResult
from mutation_gate_report import as_report_payload, render_markdown
from mutation_gate_scope import empty_scope_advice, scope_label

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL = REPO_ROOT / "skills" / "test-quality" / "SKILL.md"
ANALYZER = REPO_ROOT / "skills" / "test-quality" / "agents" / "analyzer.md"
REVIEWER = REPO_ROOT / "skills" / "test-quality" / "agents" / "reviewer.md"


def result_with(**overrides):
    """A completed run, perturbed by exactly one fact per test.

    No backend rows: a run that selected nothing never dispatched a backend, so
    inventing one here would test a shape the gate cannot produce.
    """
    fields = {
        "survivors": (),
        "unavailable": (),
        "unresolved": (),
        "unclaimed": (),
        "selected": 0,
        "backend_runs": (),
    }
    fields.update(overrides)
    return GateResult(**fields)


def empty_result():
    """A run that selected nothing: the shape a stand-alone audit produces."""
    return result_with(selected=0)


class TestWhatAnEmptySelectionMeansPerScope:
    """Scope semantics belong to the scope module. The renderer renders; it
    does not know what `merge-base` implies about a tree."""

    def test_an_empty_merge_base_names_the_reachable_sweep(self):
        advice = empty_scope_advice("merge-base")

        assert "--scope full --paths" in advice

    def test_an_empty_working_tree_names_it_too(self):
        """Same shape: nothing changed, so a diff-shaped scope covers nothing,
        and the audit still has a test tree to sweep."""
        advice = empty_scope_advice("working-tree")

        assert "--scope full --paths" in advice

    def test_an_empty_full_scope_does_not_suggest_widening_to_full(self):
        """It already is full. Advising the scope you are in reads as a bug in
        the tool rather than a remedy for the operator."""
        advice = empty_scope_advice("full")

        assert "--scope full --paths" not in advice

    def test_a_pathspec_that_matched_nothing_is_called_out_as_such(self):
        """`full` selecting zero files with a pathspec given is a typo or a
        moved directory, not an empty repo -- and the operator is the only one
        who can tell which."""
        advice = empty_scope_advice("full", pathspec=("tests/orders",))

        assert "tests/orders" in advice
        assert "matched no files" in advice

    def test_advice_is_a_plain_string_for_every_known_scope(self):
        for scope in ("merge-base", "working-tree", "full"):
            assert isinstance(empty_scope_advice(scope), str)

    def test_an_unknown_scope_is_silent_rather_than_guessing(self):
        """`changed_paths` rejects unknown scopes; if one ever reaches here,
        inventing advice for it is worse than saying nothing."""
        assert empty_scope_advice("everything-ever") == ""


class TestTheAdviceReachesTheOperator:
    def test_the_markdown_carries_it_under_nothing_selected(self):
        markdown = render_markdown(
            empty_result(),
            scope="merge-base",
            empty_scope_advice=empty_scope_advice("merge-base"),
        )

        assert "Nothing selected" in markdown
        assert "--scope full --paths" in markdown

    def test_the_json_payload_carries_it_for_the_analyzer_agent(self):
        """The analyzer parses the JSON, not the markdown. Advice only the
        human sees is advice the agent acts against."""
        payload = as_report_payload(
            empty_result(),
            scope="merge-base",
            empty_scope_advice=empty_scope_advice("merge-base"),
        )

        assert "--scope full --paths" in payload["empty_scope_advice"]

    def test_a_run_that_selected_files_carries_no_advice(self):
        """Advice on a sweep that covered something is noise, and noise in this
        section is how the real sentences stop being read."""
        markdown = render_markdown(
            result_with(selected=12),
            scope="merge-base",
            empty_scope_advice=empty_scope_advice("merge-base"),
        )

        assert "--scope full --paths" not in markdown

    def test_the_renderer_still_works_without_advice(self):
        """Backwards-compatible by construction: the advice is an optional
        input, so every existing caller keeps its current output."""
        markdown = render_markdown(empty_result(), scope="merge-base")

        assert "Nothing selected" in markdown

    def test_an_empty_selection_is_still_nothing_to_do_not_a_failure(self):
        """The exit-code contract does not move: nothing broke, so this is not
        an unverified run. Only the sentence changes."""
        from mutation_gate import exit_code_for, unverified_reasons

        assert not unverified_reasons(empty_result())
        assert exit_code_for(empty_result()) == 0


class TestTheSkillDoesNotOverclaimTheSweep:
    """The original defect was a claim, not a default: "the analyzer runs the
    mutation sweep, which catches born-vacuous tests" is false at the default
    scope on the audit the skill exists to run."""

    def test_the_skill_states_the_default_covers_the_diff(self):
        text = SKILL.read_text(encoding="utf-8")

        assert "--scope merge-base" in text
        assert "zero files" in text

    def test_the_skill_names_the_reachable_sweep_rather_than_dropping_the_claim(self):
        text = SKILL.read_text(encoding="utf-8")

        assert "--scope full --paths" in text
        assert "Coverage note" in text

    def test_the_skill_keeps_whole_repo_mutation_off_the_default_path(self):
        text = SKILL.read_text(encoding="utf-8")

        assert "too slow to be a default" in text


class TestTheAnalyzerOffersItRatherThanSilentlyWidening:
    def test_it_names_the_stand_alone_zero_file_case(self):
        text = ANALYZER.read_text(encoding="utf-8")

        assert "stand-alone audit selects zero files" in text

    def test_it_forbids_reporting_an_empty_sweep_as_clean(self):
        text = ANALYZER.read_text(encoding="utf-8")

        assert "Do not report that as a clean sweep" in text

    def test_it_forbids_silently_widening_to_the_whole_repo(self):
        """Widening unasked spends the operator's time by surprise -- the same
        cost the merge-base default exists to avoid."""
        text = ANALYZER.read_text(encoding="utf-8")

        assert "do not silently widen" in text.lower()

    def test_it_records_what_the_narrowed_sweep_left_out(self):
        text = ANALYZER.read_text(encoding="utf-8")

        assert "Coverage notes" in text


class TestTheReviewerSweepsTheSameScope:
    def test_it_reuses_the_analyzers_scope_rather_than_the_default(self):
        """A reviewer re-running at the default would sweep an empty diff and
        prune findings the analyzer drew from a sweep that covered real code."""
        text = REVIEWER.read_text(encoding="utf-8")

        assert "same scope the analyzer's sweep used, not the default" in text
        assert "--scope full --paths" in text


@pytest.mark.parametrize(
    "scope,pathspec,expected",
    [
        ("merge-base", (), "merge-base"),
        ("full", ("tests/orders",), "full (paths: tests/orders)"),
    ],
)
def test_the_scope_line_still_names_a_narrowed_run_as_narrowed(
    scope, pathspec, expected
):
    """Unchanged, and re-pinned here because the advice above is worthless if a
    narrowed sweep can still print as a whole-repo one."""
    assert scope_label(scope, pathspec) == expected
