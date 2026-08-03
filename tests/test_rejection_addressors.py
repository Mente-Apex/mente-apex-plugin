"""Addressing a snapshot file or one section of it, and subtracting rejections.

The round-trip test comes first deliberately: section removal rewrites a file by
splitting and rejoining it, so a lossy rejoin would corrupt every file it
touched. Pin that before building on it.
"""

import json

import config_sync_merge as merge
import config_sync_rejections as rejections
from config_sync_rejections import (
    NullRejectionPolicy,
    SnapshotFileAddressor,
    SnapshotSectionAddressor,
    filter_snapshot_files,
)

DOCUMENT = """preamble line

## Alpha

alpha body

## Beta

beta body

## Alpha

second alpha body
"""


class _RejectingPolicy:
    """Rejects exactly the addresses it was given. Substitutes for the real
    policy so addressing is tested without a ledger on disk."""

    def __init__(self, rejected_addresses):
        self._rejected = set(rejected_addresses)

    def is_rejected(self, target, source_timestamp):
        return target.address in self._rejected


def test_split_then_rejoin_is_lossless():
    assert rejections.rejoin_sections(merge._parse_sections(DOCUMENT)) == DOCUMENT


def test_section_address_round_trips_through_the_addressor():
    addressor = SnapshotSectionAddressor()
    address = rejections.section_address("CLAUDE.md", "## Beta", 0)
    assert addressor.matches(address, ("CLAUDE.md", "## Beta", 0))
    assert not addressor.matches(address, ("CLAUDE.md", "## Beta", 1))
    assert not addressor.matches(address, ("other.md", "## Beta", 0))


def test_section_address_is_json_so_headings_may_contain_any_character():
    address = rejections.section_address("CLAUDE.md", "## Weird # heading", 2)
    assert json.loads(address) == {
        "file": "CLAUDE.md",
        "heading": "## Weird # heading",
        "occurrence": 2,
    }


def test_file_addressor_uses_the_snapshot_key(tmp_path):
    addressor = SnapshotFileAddressor()
    assert addressor.identify("rules/a.md") == "rules/a.md"
    assert addressor.matches("rules/a.md", "rules/a.md")


def test_null_policy_leaves_every_file_untouched():
    files = {"CLAUDE.md": DOCUMENT, "rules/a.md": "keep me"}
    kept, removed = filter_snapshot_files(
        files, NullRejectionPolicy(), "2026-08-03T09:00:00+00:00"
    )
    assert kept == files
    assert removed == []


def test_a_rejected_file_is_dropped_whole():
    files = {"CLAUDE.md": DOCUMENT, "rules/a.md": "drop me"}
    policy = _RejectingPolicy(["rules/a.md"])
    kept, removed = filter_snapshot_files(files, policy, "2026-08-03T09:00:00+00:00")
    assert set(kept) == {"CLAUDE.md"}
    assert removed == ["rules/a.md"]


def test_a_rejected_section_is_removed_and_the_rest_survives():
    policy = _RejectingPolicy([rejections.section_address("CLAUDE.md", "## Beta", 0)])
    kept, removed = filter_snapshot_files(
        {"CLAUDE.md": DOCUMENT}, policy, "2026-08-03T09:00:00+00:00"
    )
    assert "beta body" not in kept["CLAUDE.md"]
    assert "alpha body" in kept["CLAUDE.md"]
    assert "second alpha body" in kept["CLAUDE.md"]
    assert len(removed) == 1


def test_the_nth_repeated_heading_is_addressed_independently():
    policy = _RejectingPolicy([rejections.section_address("CLAUDE.md", "## Alpha", 1)])
    kept, _ = filter_snapshot_files(
        {"CLAUDE.md": DOCUMENT}, policy, "2026-08-03T09:00:00+00:00"
    )
    assert "alpha body" in kept["CLAUDE.md"]
    assert "second alpha body" not in kept["CLAUDE.md"]


def test_rejecting_every_section_leaves_an_empty_file_not_a_missing_one():
    every_address = [
        rejections.section_address("CLAUDE.md", heading_text, occurrence)
        for (heading_text, occurrence), _heading, _body in merge._parse_sections(
            DOCUMENT
        )
    ]
    kept, _ = filter_snapshot_files(
        {"CLAUDE.md": DOCUMENT},
        _RejectingPolicy(every_address),
        "2026-08-03T09:00:00+00:00",
    )
    assert "CLAUDE.md" in kept
    assert kept["CLAUDE.md"].strip() == ""


def test_a_file_with_no_rejected_sections_passes_through_byte_identical():
    """Direct test of the fix: filter_snapshot_files must never round-trip a
    file through _parse_sections/rejoin_sections unless something in it was
    actually rejected, because that round-trip is not lossless for every
    input shape (see the next test). A file nobody touched must come back as
    the exact same object/content, trailing newline or not."""
    no_trailing_newline = "## Alpha\n\nalpha body"
    files = {"CLAUDE.md": DOCUMENT, "no-trailing-newline.md": no_trailing_newline}
    policy = _RejectingPolicy(["rules/unrelated.md"])
    kept, removed = filter_snapshot_files(files, policy, "2026-08-03T09:00:00+00:00")
    assert kept["CLAUDE.md"] == DOCUMENT
    assert kept["no-trailing-newline.md"] == no_trailing_newline
    assert removed == []


def test_a_bodiless_heading_at_eof_survives_untouched_when_nothing_is_rejected():
    """Regression test for the reported shape: a document ending in a bodiless
    heading with no trailing newline. merge._parse_sections('## Foo') and
    merge._parse_sections('## Foo\\n') parse to the same triples, so
    rejoin_sections cannot tell them apart and would add a spurious '\\n' to
    the former. The governing property is that filter_snapshot_files never
    calls rejoin_sections at all when no section of the file was rejected."""
    bodiless_heading_no_trailing_newline = "## Foo"
    kept, removed = filter_snapshot_files(
        {"CLAUDE.md": bodiless_heading_no_trailing_newline},
        NullRejectionPolicy(),
        "2026-08-03T09:00:00+00:00",
    )
    assert kept["CLAUDE.md"] == bodiless_heading_no_trailing_newline
    assert removed == []


def test_rejecting_a_section_in_a_bodiless_heading_document_may_gain_a_trailing_newline():
    """Documents the residual, accepted behaviour: once a document is
    genuinely edited (a section actually rejected), the surviving content is
    rebuilt via rejoin_sections, and a bodiless final heading with no
    original trailing newline gains one. This is acceptable because the file
    content was going to change anyway; it is the untouched case (tested
    above) that the fix guarantees is exact."""
    document = "## Alpha\n\nalpha body\n\n## Foo"
    policy = _RejectingPolicy([rejections.section_address("CLAUDE.md", "## Alpha", 0)])
    kept, removed = filter_snapshot_files(
        {"CLAUDE.md": document}, policy, "2026-08-03T09:00:00+00:00"
    )
    assert "alpha body" not in kept["CLAUDE.md"]
    assert kept["CLAUDE.md"] == "## Foo\n"
    assert len(removed) == 1
