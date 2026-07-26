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
