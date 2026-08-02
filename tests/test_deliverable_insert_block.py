"""Tests for the menteapex-deliverable insertion helper (scripts/insert_block.py).

The helper does exactly one thing: place a pre-formatted Markdown block at the
end of a named heading's section, deterministically. It does NOT reformat prose
(that is the agent's job) — it is the mechanical, testable insertion seam so a
free-hand Edit never mangles the customer copy.
"""

import io
import sys
from pathlib import Path

import pytest

# insert_block.py lives beside the skill, not in the repo-level scripts/ dir.
_SKILL_SCRIPTS = (
    Path(__file__).resolve().parents[1] / "skills" / "menteapex-deliverable" / "scripts"
)
sys.path.insert(0, str(_SKILL_SCRIPTS))

import insert_block  # noqa: E402


class TestInsertAfterHeading:
    def test_places_block_at_end_of_section_before_next_sibling_heading(self):
        document = "## Scope\n\nExisting scope line.\n\n## Terms\n\nExisting terms.\n"
        result = insert_block.insert_after_heading(
            document, "## Scope", "Added scope detail."
        )
        # The block lands inside the Scope section, before the Terms heading.
        assert result.index("Added scope detail.") < result.index("## Terms")
        assert result.index("Existing scope line.") < result.index(
            "Added scope detail."
        )
        # Terms section is untouched.
        assert "Existing terms." in result

    def test_appends_at_eof_when_section_is_last(self):
        document = "## Terms\n\nExisting terms.\n"
        result = insert_block.insert_after_heading(
            document, "## Terms", "Added terms detail."
        )
        assert result.index("Existing terms.") < result.index("Added terms detail.")
        assert result.rstrip().endswith("Added terms detail.")

    def test_subheading_of_lower_level_does_not_end_the_section(self):
        document = "## Scope\n\nScope intro.\n\n### Deliverables\n\nA list.\n\n## Terms\n\nTerms.\n"
        result = insert_block.insert_after_heading(
            document, "## Scope", "Extra scope note."
        )
        # The level-3 "### Deliverables" is inside Scope, so the block lands after it
        # but still before the sibling-level "## Terms".
        assert result.index("A list.") < result.index("Extra scope note.")
        assert result.index("Extra scope note.") < result.index("## Terms")

    def test_block_is_separated_by_blank_lines_from_neighbours(self):
        document = "## Scope\n\nScope line.\n\n## Terms\n\nTerms line.\n"
        result = insert_block.insert_after_heading(document, "## Scope", "Woven block.")
        assert "\n\nWoven block.\n\n" in result


class TestHeadingResolutionErrors:
    def test_raises_heading_not_found_when_absent(self):
        document = "## Scope\n\nScope line.\n"
        with pytest.raises(insert_block.HeadingNotFoundError):
            insert_block.insert_after_heading(document, "## Missing", "Block.")

    def test_raises_ambiguous_heading_when_two_match(self):
        document = "## Scope\n\nFirst.\n\n## Scope\n\nSecond.\n"
        with pytest.raises(insert_block.AmbiguousHeadingError):
            insert_block.insert_after_heading(document, "## Scope", "Block.")


class TestCliAdapter:
    def test_writes_inserted_block_back_to_file(self, tmp_path):
        copy = tmp_path / "engagement-acme.md"
        copy.write_text("## Scope\n\nBase scope.\n\n## Terms\n\nBase terms.\n")
        exit_code = insert_block.main(
            ["--file", str(copy), "--after-heading", "## Scope"],
            block_reader=io.StringIO("Custom on-site clause."),
        )
        assert exit_code == 0
        written = copy.read_text()
        assert written.index("Custom on-site clause.") < written.index("## Terms")

    def test_missing_heading_returns_nonzero_and_leaves_file_unchanged(self, tmp_path):
        copy = tmp_path / "engagement-acme.md"
        original = "## Scope\n\nBase scope.\n"
        copy.write_text(original)
        exit_code = insert_block.main(
            ["--file", str(copy), "--after-heading", "## Nonexistent"],
            block_reader=io.StringIO("Never inserted."),
        )
        assert exit_code != 0
        assert copy.read_text() == original


class TestInsertingIsSafeToRepeat:
    DOC = "# Agreement\n\n## Scope\n\nBaseline work.\n\n## Fees\n\n€X.\n"
    CLAUSE = "Bespoke NDA clause."

    def test_the_block_lands_at_the_end_of_the_named_section(self):
        updated = insert_block.insert_after_heading(self.DOC, "## Scope", self.CLAUSE)

        scope, _, fees = updated.partition("## Fees")
        assert self.CLAUSE in scope
        assert self.CLAUSE not in fees

    def test_a_second_insert_of_the_same_block_is_refused(self):
        """Not idempotent by nature -- prose has no identity of its own -- so a
        retry after an unrelated error shipped an engagement agreement carrying
        the same bespoke clause twice."""
        once = insert_block.insert_after_heading(self.DOC, "## Scope", self.CLAUSE)

        with pytest.raises(insert_block.BlockAlreadyPresentError):
            insert_block.insert_after_heading(once, "## Scope", self.CLAUSE)

    def test_a_repeat_run_exits_zero_and_leaves_the_file_alone(self, tmp_path):
        """The requested end state already holds, so a re-run is a no-op rather
        than a failure -- which is what makes the command safe to repeat."""
        document = tmp_path / "agreement.md"
        document.write_text(self.DOC, encoding="utf-8")

        import io

        first = insert_block.main(
            ["--file", str(document), "--after-heading", "## Scope"],
            block_reader=io.StringIO(self.CLAUSE),
        )
        after_first = document.read_text(encoding="utf-8")
        second = insert_block.main(
            ["--file", str(document), "--after-heading", "## Scope"],
            block_reader=io.StringIO(self.CLAUSE),
        )

        assert first == 0
        assert second == 0
        assert document.read_text(encoding="utf-8") == after_first
        assert after_first.count(self.CLAUSE) == 1

    def test_a_different_block_still_inserts(self):
        """The control: refusing a duplicate must not refuse new content."""
        once = insert_block.insert_after_heading(self.DOC, "## Scope", self.CLAUSE)
        twice = insert_block.insert_after_heading(once, "## Scope", "A second clause.")

        assert self.CLAUSE in twice
        assert "A second clause." in twice


class TestAnAnchorThatIsNotAHeadingIsRefused:
    def test_an_indented_anchor_raises_a_named_error_not_a_typeerror(self):
        """`line.strip() == target` matched, `_HEADING_RE` (which requires `#`
        at column 0) did not, and the level comparison blew up with an
        unhandled TypeError."""
        document = "# Agreement\n\n  ## Scope\n\nBody.\n"

        with pytest.raises(insert_block.AnchorIsNotAHeadingError):
            insert_block.insert_after_heading(document, "## Scope", "Clause.")

    def test_the_cli_reports_it_and_writes_nothing(self, tmp_path):
        import io

        document = tmp_path / "doc.md"
        original = "# Agreement\n\n  ## Scope\n\nBody.\n"
        document.write_text(original, encoding="utf-8")

        exit_code = insert_block.main(
            ["--file", str(document), "--after-heading", "## Scope"],
            block_reader=io.StringIO("Clause."),
        )

        assert exit_code == 1
        assert document.read_text(encoding="utf-8") == original


class TestIdempotencyDoesNotSwallowNewContent:
    """`block in section_text` was a substring test, so a new clause that
    happened to be a substring of existing prose was refused with exit 0 --
    telling the operator it was in the agreement when it was not.
    """

    DOC = "# Agreement\n\n## Fees\n\nPayment is due. See annex.\n"

    def test_a_new_block_that_is_a_substring_is_still_inserted(self):
        updated = insert_block.insert_after_heading(
            self.DOC, "## Fees", "Payment is due."
        )

        assert updated.count("Payment is due.") == 2

    def test_the_exact_block_as_whole_lines_is_still_refused(self):
        """The control: real idempotency must keep working."""
        once = insert_block.insert_after_heading(
            self.DOC, "## Fees", "A bespoke clause."
        )

        with pytest.raises(insert_block.BlockAlreadyPresentError):
            insert_block.insert_after_heading(once, "## Fees", "A bespoke clause.")

    def test_a_multi_line_block_is_matched_as_a_whole_sequence(self):
        block = "First line.\nSecond line."
        once = insert_block.insert_after_heading(self.DOC, "## Fees", block)

        with pytest.raises(insert_block.BlockAlreadyPresentError):
            insert_block.insert_after_heading(once, "## Fees", block)

    def test_a_block_sharing_only_its_first_line_is_inserted(self):
        once = insert_block.insert_after_heading(
            self.DOC, "## Fees", "First line.\nSecond line."
        )

        twice = insert_block.insert_after_heading(
            once, "## Fees", "First line.\nDifferent second line."
        )

        assert "Different second line." in twice
