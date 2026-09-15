"""`/tdd` asks whether there is a domain, before the first test (issue #123).

The design lenses were reachable but never routed to. The arrow pointed one way:
`/ddd` design mode gates the model and then drives `/tdd` to build innermost-out
— but `/tdd`, which owns the wide trigger surface ("implement", "build", "add a
feature", "new endpoint"), never asked whether there was a domain to design
first. DDD appeared in its SKILL.md only as *testing* guidance for hexagonal
projects.

Net effect: the default path from "build me X" to code bypassed design entirely,
and quality arrived afterwards as an audit of something already built.

The fix is a triage, not a gate. Most work genuinely is a script or an adapter,
and forcing DDD on it is the dogma `ddd`'s own "when NOT to" list warns against —
so these tests pin both directions, and pin that the step stays cheap.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TDD = REPO_ROOT / "skills" / "tdd" / "SKILL.md"
DDD = REPO_ROOT / "skills" / "ddd" / "SKILL.md"


def tdd():
    return TDD.read_text(encoding="utf-8")


class TestTheTriageExists:
    def test_tdd_has_a_design_triage_step(self):
        assert "Design triage" in tdd()

    def test_it_runs_before_the_first_red_test(self):
        """After the first test the decision has already been made by default,
        and remaking it costs a rewrite."""
        text = tdd()

        assert "before the first red test" in text
        assert text.index("Design triage") < text.index(
            "## Phase 2 — Build with red-green-refactor"
        )

    def test_it_sits_in_the_interactive_phase_where_a_person_can_answer(self):
        text = tdd()

        assert text.index("## Phase 1 — Understand") < text.index("Design triage")


class TestBothAnswersAreRealAnswers:
    def test_yes_hands_off_to_ddd_design_mode(self):
        text = tdd()

        assert "/ddd` design mode" in text
        assert "innermost-out" in text

    def test_it_names_what_a_domain_actually_looks_like(self):
        """A triage question with no criteria is a coin flip with extra steps."""
        text = tdd()

        for signal in ("identity", "lifecycle", "invariants", "CRUD"):
            assert signal in text

    def test_no_goes_straight_to_red_green(self):
        text = tdd()

        assert "straight to red-green" in text

    def test_most_work_is_the_no_branch_and_it_says_so(self):
        """Without this the triage becomes a DDD funnel, which is the exact
        dogma the ddd skill's own when-NOT-to list warns against."""
        text = tdd()

        assert "Most work is this" in text
        assert "dogma" in text


class TestItStaysCheap:
    def test_it_is_one_judgment_and_not_an_interview(self):
        text = tdd()

        assert "never an interview" in text
        assert "One question" in text or "One judgment" in text

    def test_a_pre_authorization_skips_it(self):
        """The same courtesy every other gate in this repo extends: someone who
        already decided should not be asked again."""
        assert "pre-authorization" in tdd()

    def test_silence_is_not_an_acceptable_outcome(self):
        """The failure mode this skill already names for the REFACTOR step: a
        step nobody sees is a step that evaporated."""
        text = tdd()

        assert "Silence is not an acceptable outcome" in text


class TestTheHandoffIsRealOnBothSides:
    def test_ddd_still_drives_tdd_programmatically(self):
        """The triage is only worth anything if the far side of the handoff
        exists — this is the half that already worked."""
        text = DDD.read_text(encoding="utf-8")

        assert "programmatic" in text.lower()
        assert "tdd" in text.lower()

    def test_tdd_states_why_this_beats_auditing_afterwards(self):
        """The argument for the step's existence, kept in the file so a future
        editor knows what they would be deleting: an anemic model found in a
        report costs a refactor; the same call made before the first test costs
        nothing."""
        text = tdd()

        assert "costs a refactor" in text
