"""Every document that names the lenses names all of them.

Nine of the fifteen findings in the 2026-09-16 review were one shape: a
mechanism built correctly, with the roster it operates on hand-enumerated in
prose beside it. Adding the seventh lens should have been one edit. It was five,
four were missed, and the suite stayed green — because every guard that could
have caught it iterated a hardcoded tuple that also said six.

Prose cannot glob, so a document that must name the lenses still names them.
What changes here is that something compares what it names against what the repo
actually ships (`tests/lens_roster.py`, discovered from the filesystem), so the
next lens fails these tests until every roster agrees.

`tests/test_lens_agents_delegate.py` already discovers its own roster and is
therefore not in this drift class.
"""

from pathlib import Path

import pytest

from lens_roster import (
    discovered_id_prefixes,
    discovered_lenses,
    id_prefix,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_CONTRACT = REPO_ROOT / "docs" / "report-contract.md"
REFACTOR_WORKFLOW = REPO_ROOT / "docs" / "refactor-workflow.md"
UMBRELLA = REPO_ROOT / "skills" / "code-quality" / "SKILL.md"
CONSOLIDATOR = REPO_ROOT / "skills" / "code-quality" / "agents" / "consolidator.md"
UMBRELLA_TEMPLATE = (
    REPO_ROOT / "skills" / "code-quality" / "references" / "report-template.md"
)


def flat(path):
    """The file with runs of whitespace collapsed — these are wrapped prose
    files, so a roster is routinely split across a line break."""
    return " ".join(path.read_text(encoding="utf-8").split())


def test_the_roster_is_discovered_and_non_empty():
    """A guard on the guard: discovery returning nothing would make every test
    below vacuously pass, which is the failure the hardcoded tuples had."""
    assert len(discovered_lenses()) >= 7
    assert "acceptance-quality" in discovered_lenses()


class TestTheCanonicalIdContract:
    """`docs/report-contract.md` is named by `docs/refactor-workflow.md` as the
    one place the finding ID scheme is defined, and `tests/test_lens_report_
    contract.py` PARSES it to derive the lenses it checks — so a lens missing
    from that line is a lens silently skipped by six other guards."""

    @pytest.mark.parametrize("prefix", discovered_id_prefixes())
    def test_every_lens_prefix_is_sanctioned(self, prefix):
        contract = flat(REPORT_CONTRACT)
        scheme_line = contract.split("`<lens>` ∈", 1)[1].split("—", 1)[0]

        assert prefix in scheme_line, f"{prefix} is not a sanctioned ID prefix"

    @pytest.mark.parametrize("lens", discovered_lenses())
    def test_every_lens_has_a_report_filename(self, lens):
        assert f"| {lens} |" in REPORT_CONTRACT.read_text(encoding="utf-8")

    def test_the_lens_count_in_prose_matches_the_roster(self):
        """The prose says "all N lenses" in words, and words drift silently."""
        spelled = {6: "six", 7: "seven", 8: "eight", 9: "nine"}[
            len(discovered_lenses())
        ]

        assert f"all {spelled}" in flat(REPORT_CONTRACT)


class TestTheUmbrellaKnowsEveryLens:
    @pytest.mark.parametrize("lens", discovered_lenses())
    def test_the_fan_out_dispatches_it(self, lens):
        assert f"skills/{lens}/agents/analyzer.md" in UMBRELLA.read_text(
            encoding="utf-8"
        )

    @pytest.mark.parametrize("lens", discovered_lenses())
    def test_the_worktree_set_includes_it(self, lens):
        """A lens absent from the `--lenses` list gets no subject root, so it
        audits the orchestrator's checkout — the #156 failure, re-armed."""
        assert lens in flat(UMBRELLA).split("--lenses", 1)[1][:300]

    @pytest.mark.parametrize("lens", discovered_lenses())
    def test_the_consolidators_precedence_ladder_places_it(self, lens):
        """A lens with no place in the ladder has no defined answer for who files
        a shared smell, which is the question the ladder exists to settle.

        Either spelling counts: this document works in finding IDs, so it calls
        `clean-architecture` by its `clean-arch` prefix."""
        consolidator = flat(CONSOLIDATOR)

        assert lens in consolidator or id_prefix(lens) in consolidator

    @pytest.mark.parametrize("prefix", discovered_id_prefixes())
    def test_the_consolidated_template_sanctions_its_ids(self, prefix):
        assert prefix in flat(UMBRELLA_TEMPLATE)


class TestTheSharedWorkflowKnowsEveryLens:
    @pytest.mark.parametrize("lens", discovered_lenses())
    def test_the_worktree_example_lists_it(self, lens):
        """The shared doc's `--lenses` example is what the orchestrator copies;
        it said six for as long as the umbrella said seven."""
        example = flat(REFACTOR_WORKFLOW).split("lens_worktrees.py", 1)[1][:400]

        assert lens in example


class TestTheIdPrefixExceptionIsDataNotAccident:
    def test_clean_architecture_is_the_only_renamed_prefix(self):
        """`clean-arch` exists because the full name made every ID in the
        consolidated report unreadably long. It is the one exception, and it
        lives in the roster as data rather than as a special case in each guard."""
        renamed = [lens for lens in discovered_lenses() if id_prefix(lens) != lens]

        assert renamed == ["clean-architecture"]
        assert id_prefix("clean-architecture") == "clean-arch"
