#!/usr/bin/env python3
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


def _heading_level(line: str) -> int | None:
    """The heading level (number of leading #) for a heading line, else None."""
    match = _HEADING_RE.match(line)
    return len(match.group(1)) if match else None


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

    section_end = len(lines)
    for index in range(heading_index + 1, len(lines)):
        level = _heading_level(lines[index])
        if level is not None and level <= target_level:
            section_end = index
            break

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
    parser.add_argument("--file", required=True, help="The deliverable copy to edit in place.")
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
        updated = insert_after_heading(document_path.read_text(), args.after_heading, block)
    except AmbiguousHeadingError as ambiguous:
        print(f"✗ ambiguous heading {ambiguous} — more than one match; nothing written.",
              file=sys.stderr)
        return 1
    except HeadingNotFoundError as missing:
        print(f"✗ heading not found: {missing} — nothing written.", file=sys.stderr)
        return 1

    document_path.write_text(updated)
    print(f"✓ inserted block into {document_path} under {args.after_heading!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
