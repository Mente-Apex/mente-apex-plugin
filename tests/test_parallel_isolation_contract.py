"""The contract that makes a parallel fan-out survivable (issue #156).

Two facts drive all of it, and neither is discoverable from inside an agent:

1. A subagent cannot put itself in a worktree. It is isolated only if the
   dispatch asked for it, and once running it cannot tell which regime it is in
   except by finding its inputs missing. So the *dispatcher* must decide, and
   say so.
2. A worktree carries tracked files at one ref and nothing else. Git-excluded
   paths (`docs/reports/`, `graphify-out/`) are absent, and a worktree cut at a
   branch's merge-base does not carry that branch's code.

Left unstated, both fail silently: in the reported run five of six analyzers
re-resolved their scoped files against the orchestrator's checkout by absolute
path and audited it from inside their sandbox, while the sixth -- whose gate has
to execute the code -- could not fall back and reported nothing. The audit
looked complete and one lens had been reduced to zero.

These tests pin the prose contract, because that is what the orchestrator and
the agents actually execute. Read the shared rule in
`docs/refactor-workflow.md`; these only guard that it stays said, and stays said
in the places a role will actually look.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / "docs" / "refactor-workflow.md"
SHARED_ANALYZER = REPO_ROOT / "docs" / "refactor-agents" / "analyzer.md"
SHARED_REVIEWER = REPO_ROOT / "docs" / "refactor-agents" / "reviewer.md"
UMBRELLA = REPO_ROOT / "skills" / "code-quality" / "SKILL.md"
TEST_QUALITY_ANALYZER = REPO_ROOT / "skills" / "test-quality" / "agents" / "analyzer.md"

ISOLATION_SECTION = "### Isolation and artifact collection"


def section_of(path, heading):
    """One `###` section of a Markdown file, heading included."""
    text = path.read_text(encoding="utf-8")
    start = text.index(heading)
    remainder = text[start + len(heading) :]
    next_heading = remainder.find("\n### ")
    end = len(text) if next_heading == -1 else start + len(heading) + next_heading
    return text[start:end]


class TestTheSharedRuleStatesTheContract:
    def test_the_workflow_carries_an_isolation_section_at_all(self):
        assert ISOLATION_SECTION in WORKFLOW.read_text(encoding="utf-8")

    def test_it_puts_the_isolation_decision_on_the_dispatcher(self):
        """An agent cannot request its own worktree, so a rule addressed to the
        agent would be unexecutable."""
        section = section_of(WORKFLOW, ISOLATION_SECTION)

        assert "dispatcher's call, never the agent's" in section
        assert 'isolation: "worktree"' in section

    def test_it_names_both_things_a_worktree_does_not_carry(self):
        section = section_of(WORKFLOW, ISOLATION_SECTION)

        # Git-excluded paths: where an artifact would have landed.
        assert "docs/reports/" in section and "graphify-out/" in section
        # And the ref: where the subject of the audit would have been.
        assert "merge-base" in section

    def test_it_splits_the_subject_root_from_the_artifact_root(self):
        """The asymmetry IS the fix: read where you were put, write where you
        were told. Absolute code paths are what let five analyzers read outside
        their sandbox without noticing."""
        section = section_of(WORKFLOW, ISOLATION_SECTION)

        assert "subject root" in section
        assert "artifact root" in section
        assert "outside the worktree" in section

    def test_it_makes_the_worktrees_itself_rather_than_asking_the_harness(self):
        """`isolation: "worktree"` takes no ref, so it cannot be pointed at the
        branch under review — which is the whole defect. The orchestrator cuts
        the set itself, and is told not to nest one sandbox inside another."""
        section = section_of(WORKFLOW, ISOLATION_SECTION)

        assert "lens_worktrees.py" in section
        assert "takes no ref" in section
        assert "do not also pass" in section

    def test_it_requires_the_ref_to_be_verified_not_trusted(self):
        section = section_of(WORKFLOW, ISOLATION_SECTION)

        assert "verifies the ref rather than trusting it" in section
        assert "partial set is worse than none" in section

    def test_it_requires_the_subject_to_be_asserted_present(self):
        section = section_of(WORKFLOW, ISOLATION_SECTION)

        assert "own subject root" in section
        assert "coverage gap" in section

    def test_it_forbids_deriving_a_path_into_another_checkout(self):
        """The observed failure was not a missing rule about worktrees; it was
        an agent silently resolving its way back out of one."""
        section = section_of(WORKFLOW, ISOLATION_SECTION)

        assert "never" in section.lower() and "derive" in section.lower()


class TestTheUmbrellaDispatchesTheWayTheRuleRequires:
    def test_it_cuts_the_worktree_set_at_the_reviewed_ref(self):
        text = UMBRELLA.read_text(encoding="utf-8")

        assert "lens_worktrees.py" in text
        assert "--ref <branch-under-review>" in text

    def test_it_does_not_also_ask_the_harness_for_isolation(self):
        """A harness worktree wrapping an orchestrator worktree is two sandboxes
        deep with the code in neither."""
        text = UMBRELLA.read_text(encoding="utf-8")

        assert "without** `isolation:`" in text

    def test_reviewers_reuse_the_set_rather_than_cutting_a_second(self):
        """A reviewer must verify against exactly the tree its analyzer read."""
        text = UMBRELLA.read_text(encoding="utf-8")

        assert "same worktree set Phase 1 used" in text

    def test_it_names_the_three_things_dispatch_owns(self):
        text = UMBRELLA.read_text(encoding="utf-8")

        assert "subject root" in text
        assert "artifact root" in text
        assert "own subject root" in text

    def test_it_tears_the_set_down_afterwards(self):
        text = UMBRELLA.read_text(encoding="utf-8")

        assert "remove --root" in text

    def test_it_points_at_the_shared_rule_rather_than_restating_it(self):
        """One contract, one home -- a second copy is a second thing to drift."""
        text = UMBRELLA.read_text(encoding="utf-8")

        assert "Isolation and artifact collection" in text
        assert "docs/refactor-workflow.md" in text


class TestTheAgentSideHalf:
    def test_the_analyzer_takes_its_output_path_from_the_brief(self):
        text = SHARED_ANALYZER.read_text(encoding="utf-8")

        assert "artifact root" in text
        assert "Never derive" in text

    def test_the_analyzer_checks_the_subject_is_present_before_reading_it(self):
        text = SHARED_ANALYZER.read_text(encoding="utf-8")

        assert "your own working directory" in text
        assert "coverage gap" in text

    def test_the_assertion_is_documented_as_a_backstop_not_the_mechanism(self):
        """The script is what makes a correct worktree; the assertion is what
        makes a wrong one loud. Conflating them invites someone to delete the
        script and keep the prose."""
        section = section_of(WORKFLOW, ISOLATION_SECTION)

        assert "backstop, not the mechanism" in section

    def test_the_reviewer_does_not_verify_against_a_different_tree(self):
        """A reviewer confirming and pruning findings against another checkout
        is worse than one that stops: it produces a verified-looking report on
        evidence that is not there."""
        text = SHARED_REVIEWER.read_text(encoding="utf-8")

        assert "your own working directory" in text
        assert "coverage gap" in text

    def test_the_reviewer_reads_the_draft_from_the_artifact_root(self):
        text = SHARED_REVIEWER.read_text(encoding="utf-8")

        assert "artifact root" in text


class TestTheLensWhoseGateExecutesCode:
    def test_test_quality_points_the_gate_at_its_own_working_directory(self):
        """The other five can still read a file when isolation goes wrong; a
        mutation sweep over code that is not there has nothing to run, which is
        why this lens is the one that reported nothing at all."""
        text = TEST_QUALITY_ANALYZER.read_text(encoding="utf-8")

        assert "--repo-root" in text
        assert "own working directory" in text

    def test_it_refuses_the_absolute_path_workaround(self):
        text = TEST_QUALITY_ANALYZER.read_text(encoding="utf-8")

        assert "never at an absolute path into another checkout" in text


class TestTheApplyPhaseInheritsTheSameRule:
    def test_parallel_chains_assert_their_code_is_present(self):
        """A chain in a worktree at the wrong ref does not fail to find the
        code -- it EDITS code that is not under review."""
        text = WORKFLOW.read_text(encoding="utf-8")
        parallel = text[text.index("**Parallel option**") :][:900]

        assert "Isolation and artifact collection" in parallel
        assert "lens_worktrees.py" in parallel
        assert "edits code that is not under review" in parallel
