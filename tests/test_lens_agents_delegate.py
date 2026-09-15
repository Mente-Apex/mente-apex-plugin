"""Every lens agent reaches the shared role contract (issue #131).

The lens agent files were bimodal: `solid` and `gof` were five-line pointers at
`docs/refactor-agents/`, while `clean-architecture`, `clean-code`, `ddd` and
`test-quality` carried 32-112 line local copies that restated the shared
read-only contract, the draft-writing rule and the critic's verify/prune loop in
their own words.

Duplicated contract prose drifts in silence. A change to the shared read-only
rule reached two lenses and missed four, and nothing failed.

Some local content is inherent and stays: `ddd`'s analyze mode has genuinely
different subject matter, and `test-quality` carries two safety gates (mutation,
coverage-non-regression) no other lens has. What is NOT inherent is restating a
contract that already exists one directory up.

So this file pins the two halves that matter: the shared roles state each
contract, and every lens agent file points at its shared role. A lens may add
whatever lens-specific instruction it needs on top; it may not fork the
contract.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SHARED_ROLES = REPO_ROOT / "docs" / "refactor-agents"
SKILLS = REPO_ROOT / "skills"

# The umbrella's consolidator is not one of the three shared roles -- it merges
# six lens reports and has no analyzer/reviewer/implementer counterpart.
EXCLUDED_SKILLS = {"code-quality"}

ROLES = ("analyzer", "reviewer", "implementer")


def lens_agent_files():
    """Every (lens, role, path) a lens ships for one of the three shared roles."""
    for skill_directory in sorted(SKILLS.iterdir()):
        if not skill_directory.is_dir() or skill_directory.name in EXCLUDED_SKILLS:
            continue
        for role in ROLES:
            agent_file = skill_directory / "agents" / f"{role}.md"
            if agent_file.is_file():
                yield skill_directory.name, role, agent_file


def test_there_are_lens_agents_to_check():
    """A guard on the guard: a glob that silently matches nothing would make
    every parametrized test below vacuously pass."""
    assert len(list(lens_agent_files())) >= 12


@pytest.mark.parametrize(
    "lens,role,agent_file",
    [
        pytest.param(lens, role, path, id=f"{lens}-{role}")
        for lens, role, path in lens_agent_files()
    ],
)
def test_every_lens_agent_points_at_its_shared_role(lens, role, agent_file):
    """The one rule. Whatever else a lens agent says, it must send the agent to
    the shared role first — that is what makes a change to the contract reach
    all six lenses instead of the two that happened to link it."""
    text = agent_file.read_text(encoding="utf-8")

    assert (
        f"refactor-agents/{role}.md" in text
    ), f"{lens}/{role} does not reference docs/refactor-agents/{role}.md"


class TestTheSharedRolesActuallyCarryTheContract:
    """Delegation is only safe if there is something to delegate TO. If these
    fail, the parametrized test above is pointing every lens at an empty
    promise."""

    def test_the_analyzer_role_states_the_read_only_contract(self):
        text = (SHARED_ROLES / "analyzer.md").read_text(encoding="utf-8")

        assert "read-only" in text.lower()
        assert "edit no code" in text.lower()
        # The failure mode that motivated the split: an agent that returns its
        # draft as chat text re-emits the whole thing through the orchestrator's
        # context, which is the cost the subagent split exists to avoid.
        assert "failed run" in text.lower()

    def test_the_reviewer_role_states_the_critic_contract(self):
        text = (SHARED_ROLES / "reviewer.md").read_text(encoding="utf-8")

        assert "verif" in text.lower()
        assert "prune" in text.lower()
        assert "lens-overlap.md" in text  # file a shared smell once

    def test_the_implementer_role_states_that_it_does_edit_code(self):
        """The inverted-quote class of drift (#152): the implementer's rule is
        that it DOES edit code, through the refactor job, never ad hoc."""
        text = (SHARED_ROLES / "implementer.md").read_text(encoding="utf-8")

        assert "You do edit code" in text
        assert "refactor-jobs.md" in text


class TestTheThinLensesStayThin:
    """`solid` and `gof` are the intended pattern in full: read the shared role,
    name the rubric, name the draft path. They are the control group — if they
    ever grow a local contract, the bimodality is back."""

    @pytest.mark.parametrize("lens", ["solid", "gof"])
    @pytest.mark.parametrize("role", ROLES)
    def test_the_pointer_lenses_are_still_pointers(self, lens, role):
        agent_file = SKILLS / lens / "agents" / f"{role}.md"
        if not agent_file.is_file():
            pytest.skip(f"{lens} ships no {role}")

        line_count = len(agent_file.read_text(encoding="utf-8").splitlines())

        assert line_count <= 15, (
            f"{lens}/{role} has grown to {line_count} lines — if it needs local "
            "instruction, say why; if it is restating the shared contract, delete it"
        )


class TestTheCollapsedLensesKeptWhatIsTheirs:
    """Collapsing must not throw away lens-specific instruction. These are the
    facts that would have been lost if the delegation had gone too far."""

    def test_clean_architecture_kept_its_tier_flags_and_graph_work(self):
        analyzer = (SKILLS / "clean-architecture/agents/analyzer.md").read_text()

        assert "--cohesion" in analyzer and "--metrics" in analyzer
        assert "cycles (ADP)" in analyzer

    def test_clean_architecture_kept_the_dependency_rule_contract(self):
        """The only lens that leaves an executable guard behind."""
        reviewer = (SKILLS / "clean-architecture/agents/reviewer.md").read_text()

        assert "dependency-rule contract" in reviewer.lower()
        assert "importlinter" in reviewer.lower()
        assert "never committed silently" in reviewer

    def test_clean_code_kept_its_declared_alias(self):
        """`Suggestion` is this lens's declared alias for the shared
        `Proposed change`, and the reviewer's template uses the same word so it
        edits the candidate fix rather than authoring one."""
        analyzer = (SKILLS / "clean-code/agents/analyzer.md").read_text()

        assert "**Suggestion:**" in analyzer
        assert "report-contract.md" in analyzer

    def test_clean_code_kept_the_where_this_bends_check(self):
        """The guard against filing style preferences as findings."""
        analyzer = (SKILLS / "clean-code/agents/analyzer.md").read_text()

        assert "Where this bends" in analyzer

    def test_the_inherently_local_lenses_still_carry_their_own_material(self):
        """`ddd`'s analyze mode and `test-quality`'s two extra gates are the
        legitimately-local cases this issue named. Delegating their contract
        must not have flattened their content."""
        ddd_analyzer = (SKILLS / "ddd/agents/analyzer.md").read_text()
        test_quality_analyzer = (SKILLS / "test-quality/agents/analyzer.md").read_text()

        assert "anemic" in ddd_analyzer.lower()
        assert "mutation" in test_quality_analyzer.lower()
