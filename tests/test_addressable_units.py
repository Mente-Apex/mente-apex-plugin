"""The one enumeration+addressing vocabulary that export and the filters share.

A drift between the units this yields and the units the filters query is silent:
every provenance lookup would miss, every unit would fall back to the export
timestamp, and the resurrection fix would stop working with no error at all.
That is the failure this file exists to make loud.
"""

import json

import config_sync_rejections as rejections
from config_sync_rejections import iter_addressable_units

SETTINGS = {
    "permissions": {"defaultMode": "acceptEdits"},
    "model": "opus",
}

FILES = {
    "CLAUDE.md": "# Top\n\n## Alpha\nalpha body\n\n## Beta\nbeta body\n",
    "rules/a.md": "## Only\nonly body\n",
    "settings.json": json.dumps(SETTINGS),
    "keybindings.json": '{"a": 1}',
}


def _units_by_kind(files):
    grouped = {}
    for unit in iter_addressable_units(files):
        grouped.setdefault(unit.kind, []).append(unit)
    return grouped


def test_every_file_key_yields_a_file_unit():
    addresses = {unit.address for unit in _units_by_kind(FILES)["snapshot-file"]}
    assert addresses == set(FILES)


def test_a_markdown_file_yields_one_unit_per_section():
    sections = _units_by_kind(FILES)["snapshot-section"]
    addresses = {unit.address for unit in sections}
    expected = rejections.section_address("rules/a.md", "## Only", 0)
    assert expected in addresses
    assert any('"file": "CLAUDE.md"' in address for address in addresses)


def test_a_repeated_heading_stays_distinct_by_occurrence():
    files = {"CLAUDE.md": "## Notes\nfirst\n\n## Notes\nsecond\n"}
    sections = _units_by_kind(files)["snapshot-section"]
    assert len({unit.address for unit in sections}) == len(sections)


def test_a_non_markdown_file_yields_no_section_units():
    files = {"keybindings.json": '{"a": 1}'}
    assert "snapshot-section" not in _units_by_kind(files)


def test_settings_keys_are_yielded_at_every_depth():
    addresses = {unit.address for unit in _units_by_kind(FILES)["settings-key"]}
    assert rejections.settings_key_address(("permissions",)) in addresses
    assert rejections.settings_key_address(("permissions", "defaultMode")) in addresses
    assert rejections.settings_key_address(("model",)) in addresses


def test_only_the_settings_json_key_yields_settings_units():
    """A different .json file is not settings, however well it parses."""
    files = {"keybindings.json": json.dumps({"permissions": {"defaultMode": "x"}})}
    assert "settings-key" not in _units_by_kind(files)


def test_an_unparseable_settings_blob_yields_no_settings_units():
    files = {"settings.json": "{not json"}
    assert "settings-key" not in _units_by_kind(files)


def test_a_section_unit_carries_the_triple_needed_to_rebuild():
    """`_parse_sections` always leads with a `__preamble__` triple, even an empty
    one when a document opens directly on a heading (see `FILES["rules/a.md"]`).
    That preamble unit is real vocabulary too -- `filter_snapshot_files` asks
    about it, so the iterator must yield it (the drift guard above proves it
    does) -- but it is not the section under test here, so select by heading
    rather than assuming index 0 is the first real section."""
    sections = _units_by_kind({"rules/a.md": "## Only\nonly body\n"})[
        "snapshot-section"
    ]
    only_unit = next(unit for unit in sections if unit.source[1] == "## Only")
    key, heading, body = only_unit.source
    assert heading == "## Only"
    assert "only body" in body


def test_payloads_differ_when_content_differs():
    first = {"rules/a.md": "## Only\none\n"}
    second = {"rules/a.md": "## Only\ntwo\n"}
    first_payloads = [unit.payload for unit in iter_addressable_units(first)]
    second_payloads = [unit.payload for unit in iter_addressable_units(second)]
    assert first_payloads != second_payloads


def test_the_iterator_and_the_filters_agree_on_every_address():
    """THE DRIFT GUARD. If anyone reimplements addressing on either side, this
    fails loudly instead of provenance silently degrading to the old behaviour."""

    class _RecordingPolicy:
        """Rejects nothing; records every address the filters ask about."""

        def __init__(self):
            self.asked = set()

        def all(self):
            return []

        def is_rejected(self, target, source_timestamp):
            self.asked.add((target.kind, target.address))
            return False

    policy = _RecordingPolicy()
    # `all()` returning [] makes `addresses_of_interest` a prefilter that skips
    # everything, so drive the filters with a policy that has no prefilter.
    policy.all = lambda: (_ for _ in ()).throw(RuntimeError("no prefilter"))

    rejections.filter_snapshot_files(FILES, policy, "")
    rejections.filter_settings_blob(FILES, policy, "")

    iterated = {(unit.kind, unit.address) for unit in iter_addressable_units(FILES)}
    assert iterated == policy.asked


def test_a_file_with_no_rejected_section_is_passed_through_unchanged():
    """The round-trip invariant: `_parse_sections` is not injective for a
    document ending in a bodiless heading, so an untouched file must never be
    rebuilt. Object identity is the assertion — equality would not catch a
    lossless-looking rebuild."""

    class _RejectsNothing:
        def all(self):
            return []

        def is_rejected(self, target, source_timestamp):
            return False

    content = "## Foo"
    files = {"rules/a.md": content}
    kept, removed = rejections.filter_snapshot_files(files, _RejectsNothing(), "")
    assert kept["rules/a.md"] is content
    assert removed == []


def test_rejecting_one_section_still_rebuilds_the_rest():
    target_address = rejections.section_address("rules/a.md", "## Beta", 0)

    class _RejectsBeta:
        def all(self):
            return []

        def is_rejected(self, target, source_timestamp):
            return target.address == target_address

    files = {"rules/a.md": "## Alpha\nalpha\n\n## Beta\nbeta\n"}
    kept, removed = rejections.filter_snapshot_files(files, _RejectsBeta(), "")
    assert "## Alpha" in kept["rules/a.md"]
    assert "## Beta" not in kept["rules/a.md"]
    assert removed == [target_address]
