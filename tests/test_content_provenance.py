"""When content changed, decided by hashing rather than by the export clock.

The bug this closes: an export is stamped with the time it ran, so unchanged
content re-exports as strictly newer than any rejection and resurrects.
"""

import json

from config_sync_provenance import ContentProvenanceStamper, hash_payload

EARLIER = "2026-07-01T09:00:00+00:00"
NOW = "2026-08-04T09:00:00+00:00"

FILES = {
    "rules/a.md": "## Only\nonly body\n",
    "settings.json": json.dumps({"model": "opus"}),
}


def _stamp(files, previous, now=NOW):
    return ContentProvenanceStamper().stamp(files, previous, now)


def test_a_first_export_stamps_everything_now():
    provenance = _stamp(FILES, {})
    assert provenance["snapshot-file"]["rules/a.md"]["changed_at"] == NOW


def test_an_entry_carries_the_hash_that_justified_it():
    provenance = _stamp(FILES, {})
    entry = provenance["snapshot-file"]["rules/a.md"]
    assert entry["hash"] == hash_payload(FILES["rules/a.md"])


def test_unchanged_content_carries_its_original_changed_at_forward():
    first = _stamp(FILES, {}, now=EARLIER)
    second = _stamp(FILES, first, now=NOW)
    assert second["snapshot-file"]["rules/a.md"]["changed_at"] == EARLIER


def test_changed_at_does_not_slide_forward_across_repeated_exports():
    """A sliding stamp passes a single-export test and reintroduces the bug."""
    provenance = _stamp(FILES, {}, now=EARLIER)
    for _ in range(3):
        provenance = _stamp(FILES, provenance, now=NOW)
    assert provenance["snapshot-file"]["rules/a.md"]["changed_at"] == EARLIER


def test_changed_content_is_restamped():
    first = _stamp(FILES, {}, now=EARLIER)
    edited = dict(FILES, **{"rules/a.md": "## Only\nedited body\n"})
    second = _stamp(edited, first, now=NOW)
    assert second["snapshot-file"]["rules/a.md"]["changed_at"] == NOW


def test_editing_one_section_leaves_a_sibling_section_untouched():
    """The resurrection fix, at the unit level."""
    two_sections = {"rules/a.md": "## Alpha\nalpha\n\n## Beta\nbeta\n"}
    first = _stamp(two_sections, {}, now=EARLIER)
    edited = {"rules/a.md": "## Alpha\nCHANGED\n\n## Beta\nbeta\n"}
    second = _stamp(edited, first, now=NOW)

    sections = second["snapshot-section"]
    beta = [entry for address, entry in sections.items() if "Beta" in address]
    alpha = [entry for address, entry in sections.items() if "Alpha" in address]
    assert beta[0]["changed_at"] == EARLIER
    assert alpha[0]["changed_at"] == NOW


def test_editing_a_section_does_restamp_the_enclosing_file():
    """Deliberate, per design spec 6.1: for a FILE rejection the unit of intent
    is the file, and any edit to it is a change to the thing that was declined."""
    two_sections = {"rules/a.md": "## Alpha\nalpha\n\n## Beta\nbeta\n"}
    first = _stamp(two_sections, {}, now=EARLIER)
    edited = {"rules/a.md": "## Alpha\nCHANGED\n\n## Beta\nbeta\n"}
    second = _stamp(edited, first, now=NOW)
    assert second["snapshot-file"]["rules/a.md"]["changed_at"] == NOW


def test_a_vanished_unit_simply_drops_out():
    first = _stamp(FILES, {}, now=EARLIER)
    second = _stamp({"settings.json": FILES["settings.json"]}, first, now=NOW)
    assert "rules/a.md" not in second["snapshot-file"]


def test_the_input_is_never_mutated():
    previous = _stamp(FILES, {}, now=EARLIER)
    before = json.dumps(previous, sort_keys=True)
    _stamp(FILES, previous, now=NOW)
    assert json.dumps(previous, sort_keys=True) == before


def test_a_previous_entry_whose_hash_does_not_match_is_restamped():
    previous = {"snapshot-file": {"rules/a.md": {"hash": "deadbeef"}}}
    provenance = _stamp(FILES, previous, now=NOW)
    assert provenance["snapshot-file"]["rules/a.md"]["changed_at"] == NOW


def test_a_previous_map_of_the_wrong_shape_is_ignored():
    provenance = _stamp(FILES, {"snapshot-file": "not a dict"}, now=NOW)
    assert provenance["snapshot-file"]["rules/a.md"]["changed_at"] == NOW


def test_a_previous_of_none_restamps_everything_without_raising():
    """Covers the top-level `isinstance(previous, dict)` guard: a caller that
    passes `None` instead of `{}` degrades to a full restamp, not an exception."""
    provenance = _stamp(FILES, None, now=NOW)
    assert provenance["snapshot-file"]["rules/a.md"]["changed_at"] == NOW


def test_a_non_dict_entry_for_an_address_restamps_that_unit():
    """Covers the `isinstance(entry, dict)` guard: `previous[kind][address]` is
    a dict (so `test_a_previous_map_of_the_wrong_shape_is_ignored` does not
    reach here), but the per-address value itself is a scalar, not an entry
    dict."""
    previous = {"snapshot-file": {"rules/a.md": "not a dict"}}
    provenance = _stamp(FILES, previous, now=NOW)
    assert provenance["snapshot-file"]["rules/a.md"]["changed_at"] == NOW


def test_a_matching_hash_with_no_changed_at_restamps_rather_than_carrying_a_bad_value():
    """Covers the `changed_at` extraction guard: the hash matches (so the
    function reaches past the mismatch check, unlike
    `test_a_previous_entry_whose_hash_does_not_match_is_restamped`, whose
    `hash` does not match and returns earlier), but `changed_at` itself is
    missing -- so it must not be trusted."""
    previous = {
        "snapshot-file": {"rules/a.md": {"hash": hash_payload(FILES["rules/a.md"])}}
    }
    provenance = _stamp(FILES, previous, now=NOW)
    assert provenance["snapshot-file"]["rules/a.md"]["changed_at"] == NOW
