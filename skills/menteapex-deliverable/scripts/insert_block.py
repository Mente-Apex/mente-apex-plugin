"""Insert a pre-formatted Markdown block at the end of a named heading's section.

Single responsibility: deterministic, mechanical placement — the testable seam so
weaving customer-specific prose into a deliverable copy never depends on a free-hand
edit that could mangle the file. It does NOT reformat prose into Markdown; that is a
semantic judgement the agent makes before calling this. Stdlib-only, to match render.py
(the plugin is config-synced and must not need `pip install` on a fresh box).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import TextIO

_HEADING_RE = re.compile(r"^(#{1,6})\s+\S")


class HeadingNotFoundError(LookupError):
    """No heading in the document matched the requested anchor."""


class AmbiguousHeadingError(LookupError):
    """More than one heading matched the anchor — placement would be a guess."""


class AnchorIsNotAHeadingError(LookupError):
    """A line matched the anchor text but is not a heading.

    An indented `  ## Scope` matches `line.strip() == target` while
    `_HEADING_RE` (which requires `#` at column 0) does not, so the section
    end could not be computed. That used to surface as an unhandled
    `TypeError: '<=' not supported between 'int' and 'NoneType'`; it is a
    stated refusal now, like the other two.
    """


class BlockAlreadyPresentError(LookupError):
    """The exact block is already in the target section.

    Inserting is not idempotent by nature — the block is prose with no
    identity of its own — so a re-run (a retry after an unrelated error, a
    repeated skill step) silently shipped an engagement agreement carrying the
    same bespoke clause twice. Refusing when the section already contains it
    makes the operation safe to repeat.
    """


def _heading_level(line: str) -> int | None:
    """The heading level (number of leading #) for a heading line, else None."""
    match = _HEADING_RE.match(line)
    return len(match.group(1)) if match else None


def _block_already_in(section_text: str, block: str) -> bool:
    """True only when `block` appears in the section as WHOLE LINES.

    A plain `block in section_text` substring test refused genuinely new
    content: inserting "Payment is due." into a section already reading
    "Payment is due. See annex." reported the block as already present and
    wrote nothing, while telling the operator the clause was in the agreement.

    Comparing stripped line sequences makes the test mean what idempotency
    needs it to mean — this exact block was inserted before — rather than
    "these characters occur somewhere nearby".
    """
    wanted = [line.strip() for line in block.strip().splitlines() if line.strip()]
    if not wanted:
        return False
    present = [line.strip() for line in section_text.splitlines() if line.strip()]
    span = len(wanted)
    return any(
        present[start : start + span] == wanted
        for start in range(len(present) - span + 1)
    )


def insert_after_heading(document_text: str, heading: str, block: str) -> str:
    """Return `document_text` with `block` placed at the end of `heading`'s section.

    The section ends at the first later heading of the same or higher level (fewer or
    equal `#`), or end of document. The inserted block is padded with a blank line on
    each side so it never glues to adjacent content.
    """
    lines = document_text.split("\n")
    target = heading.strip()

    matching_indices = [
        index for index, line in enumerate(lines) if line.strip() == target
    ]
    if not matching_indices:
        raise HeadingNotFoundError(target)
    if len(matching_indices) > 1:
        raise AmbiguousHeadingError(target)
    heading_index = matching_indices[0]
    target_level = _heading_level(lines[heading_index])
    if target_level is None:
        # The anchor matched on stripped text but the line is not a heading —
        # an indented `  ## Scope`, say. Without this the level comparison
        # below raised TypeError, and where no later heading existed it never
        # ran at all and the block was appended at end of document: the wrong
        # section, silently.
        raise AnchorIsNotAHeadingError(target)

    section_end = len(lines)
    for index in range(heading_index + 1, len(lines)):
        level = _heading_level(lines[index])
        if level is not None and level <= target_level:
            section_end = index
            break

    section_text = "\n".join(lines[heading_index:section_end])
    if _block_already_in(section_text, block):
        raise BlockAlreadyPresentError(target)

    before = lines[:section_end]
    after = lines[section_end:]
    rebuilt = "\n".join(before).rstrip("\n") + "\n\n" + block.strip("\n") + "\n\n"
    if after:
        rebuilt += "\n".join(after).lstrip("\n")
    return rebuilt


# --- CLI adapter -------------------------------------------------------------
# Thin I/O shell around the pure core. The block source is injected (defaults to
# stdin) so the adapter is exercisable without touching the real process streams.


def main(argv: list[str] | None = None, *, block_reader: TextIO = sys.stdin) -> int:
    parser = argparse.ArgumentParser(
        description="Insert a Markdown block at the end of a named heading's section."
    )
    parser.add_argument(
        "--file", required=True, help="The deliverable copy to edit in place."
    )
    parser.add_argument(
        "--after-heading",
        required=True,
        dest="after_heading",
        help='The target heading line, exactly as it appears (e.g. "## Scope").',
    )
    args = parser.parse_args(argv)

    document_path = Path(args.file)
    block = block_reader.read()
    try:
        updated = insert_after_heading(
            document_path.read_text(), args.after_heading, block
        )
    except AmbiguousHeadingError as ambiguous:
        print(
            f"✗ ambiguous heading {ambiguous} — more than one match; nothing written.",
            file=sys.stderr,
        )
        return 1
    except AnchorIsNotAHeadingError as not_heading:
        print(
            f"✗ {not_heading} matches a line that is not a heading (a heading's "
            "'#' must start at column 0); nothing written.",
            file=sys.stderr,
        )
        return 1
    except BlockAlreadyPresentError as already:
        # Exit 0: the requested end state already holds. A re-run is a no-op,
        # not a failure, which is what makes the command safe to repeat.
        print(f"✓ block already present under {already} — nothing to do.")
        return 0
    except HeadingNotFoundError as missing:
        print(f"✗ heading not found: {missing} — nothing written.", file=sys.stderr)
        return 1

    document_path.write_text(updated)
    print(f"✓ inserted block into {document_path} under {args.after_heading!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
