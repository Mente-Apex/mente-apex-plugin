"""The one deletion `coverage tool: none` permits (issue #148).

Three documents govern a test-quality deletion, and for a while two of them
disagreed. `SKILL.md` and `references/rubric.md` permit exactly one deletion
without a coverage tool -- a test that fails to import because the symbol it
names is gone, whose proof is the missing symbol rather than a coverage
measurement -- while `agents/implementer.md` told the implementer to refuse
*every* deletion arriving under `coverage tool: none` as a report defect.

A run following the skill faithfully then stalled with no way forward: the
reviewer correctly surfaced the dead test, and the implementer correctly refused
it. Nothing was wrong with either agent; the contract they shared was
self-contradictory.

The prose agrees now. Nothing pinned it, which is why it could drift in the
first place -- so these tests pin the agreement itself, not any one document's
wording of it. The refusal must stay scoped to COVERAGE-PROVED recs, and the
exception must stay stated wherever the refusal is.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL = REPO_ROOT / "skills" / "test-quality" / "SKILL.md"
IMPLEMENTER = REPO_ROOT / "skills" / "test-quality" / "agents" / "implementer.md"
RUBRIC = REPO_ROOT / "skills" / "test-quality" / "references" / "rubric.md"


def text_of(path):
    return path.read_text(encoding="utf-8")


class TestTheImplementerAdmitsTheDeletionTheSkillPermits:
    def test_gate_b_states_the_dead_import_exception(self):
        """The defect, stated as a test: this paragraph did not exist, so the
        one permitted deletion had nowhere to land."""
        implementer = text_of(IMPLEMENTER)

        assert "The one exception — a dead test that fails to import" in implementer
        assert "survives `coverage tool: none`" in implementer

    def test_the_blanket_refusal_is_scoped_to_coverage_proved_recs(self):
        """ "No deletion recs reach you at all" is what collided with the
        exception. Scoping the refusal to the recs that actually need a coverage
        proof is what makes both sentences true at once."""
        implementer = text_of(IMPLEMENTER)

        assert "no coverage-proved\ndeletion recs reach you at all" in implementer
        assert "Treat a coverage-proved deletion rec that does arrive" in implementer

    def test_the_exception_substitutes_a_proof_rather_than_waiving_one(self):
        """Admissible is not unguarded: the import failure replaces the coverage
        run as evidence, and is re-confirmed the same way."""
        implementer = text_of(IMPLEMENTER)

        assert "substituting the import failure for the" in implementer
        assert "fails at collection" in implementer

    def test_a_moved_symbol_is_a_broken_import_to_fix_not_a_test_to_delete(self):
        """The failure mode that makes this exception dangerous if left vague:
        a refactor that moved a symbol produces the identical collection error,
        and deleting the test there destroys a real guard."""
        implementer = text_of(IMPLEMENTER)

        assert "not merely moved" in implementer
        assert "broken import to *fix*" in implementer

    def test_it_is_still_never_an_auto_delete(self):
        implementer = text_of(IMPLEMENTER)

        assert "never** an auto-delete" in implementer
        assert "human sign-off" in implementer


class TestTheThreeDocumentsAgree:
    """Any one of them can be edited alone; the agreement is what must hold."""

    def test_the_skill_permits_the_dead_import_delete_without_coverage(self):
        skill = text_of(SKILL)

        assert "coverage tool: none" in skill
        assert "fails to import is still the one exception" in skill

    def test_the_rubric_classes_an_unimportable_test_as_dead(self):
        rubric = text_of(RUBRIC)

        assert "won't import" in rubric

    def test_every_document_grounds_the_exception_in_the_missing_symbol(self):
        """The same reason in all three, not three compatible-sounding reasons:
        the proof is the absent symbol, never a waived coverage requirement."""
        for document in (SKILL, IMPLEMENTER):
            assert "missing symbol" in text_of(document)

    def test_no_document_still_says_no_deletion_recs_at_all_unqualified(self):
        """The exact sentence that contradicted the exception. It may return
        only with its qualifier attached."""
        for document in (SKILL, IMPLEMENTER, RUBRIC):
            body = text_of(document)
            for line_number, line in enumerate(body.splitlines(), start=1):
                if "deletion recs reach you at all" not in line:
                    continue
                assert "coverage-proved" in line or "coverage-proved" in (
                    body.splitlines()[line_number - 2]
                ), f"{document.name}:{line_number} refuses every deletion again"
