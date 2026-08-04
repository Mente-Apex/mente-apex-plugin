"""Per-unit timestamps reaching the suppression rule."""

import json

import config_sync_rejections as rejections
from config_sync_rejections import (
    NullProvenance,
    RejectionRecord,
    SnapshotProvenance,
    rejection_id_of,
)

REJECTED_AT = "2026-08-01T09:00:00+00:00"
OLDER = "2026-07-01T09:00:00+00:00"
NEWER = "2026-08-03T09:00:00+00:00"
EXPORTED_AT = "2026-08-04T09:00:00+00:00"
# A source timestamp that is itself OLDER than REJECTED_AT, so it diverges
# from the per-unit `changed_at` (NEWER) instead of agreeing with it by
# coincidence. See test_genuinely_readded_content_overrides_the_rejection.
STALE_EXPORT = "2026-07-20T09:00:00+00:00"

FILES = {"rules/a.md": "## Only\nonly body\n"}
ADDRESS = "rules/a.md"


class _LedgerPolicy:
    """A real suppression decision over one in-memory record."""

    def __init__(self):
        self._records = [
            RejectionRecord(
                id=rejection_id_of("snapshot-file", ADDRESS),
                kind="snapshot-file",
                address=ADDRESS,
                scope="network",
                rejected_at=REJECTED_AT,
                machine_id="machine-a",
            )
        ]

    def all(self):
        return list(self._records)

    def is_rejected(self, target, source_timestamp):
        return rejections.CompositeRejectionPolicy([_Store(self._records)]).is_rejected(
            target, source_timestamp
        )


class _Store:
    scope = "network"

    def __init__(self, records):
        self._records = records

    def all(self):
        return list(self._records)


def test_the_null_provenance_always_answers_with_the_fallback():
    assert NullProvenance().timestamp_for("snapshot-file", ADDRESS, "fb") == "fb"


def test_a_recorded_changed_at_is_returned():
    provenance = SnapshotProvenance(
        {"snapshot-file": {ADDRESS: {"changed_at": OLDER, "hash": "x"}}}
    )
    assert provenance.timestamp_for("snapshot-file", ADDRESS, EXPORTED_AT) == OLDER


def test_a_missing_unit_falls_back():
    provenance = SnapshotProvenance({"snapshot-file": {}})
    assert (
        provenance.timestamp_for("snapshot-file", ADDRESS, EXPORTED_AT) == EXPORTED_AT
    )


def test_a_missing_map_falls_back():
    assert (
        SnapshotProvenance({}).timestamp_for("snapshot-file", ADDRESS, EXPORTED_AT)
        == EXPORTED_AT
    )


def test_a_malformed_entry_falls_back():
    provenance = SnapshotProvenance({"snapshot-file": {ADDRESS: "not a dict"}})
    assert (
        provenance.timestamp_for("snapshot-file", ADDRESS, EXPORTED_AT) == EXPORTED_AT
    )


def test_unchanged_content_stays_suppressed_despite_a_fresh_export_stamp():
    """THE FIX. Without provenance the fresh export stamp reads as a re-add."""
    provenance = SnapshotProvenance(
        {"snapshot-file": {ADDRESS: {"changed_at": OLDER, "hash": "x"}}}
    )
    kept, removed = rejections.filter_snapshot_files(
        FILES, _LedgerPolicy(), EXPORTED_AT, provenance=provenance
    )
    assert ADDRESS not in kept
    assert removed == [ADDRESS]


def test_a_rejected_section_stays_suppressed_despite_a_fresh_export_stamp():
    """The section-level mirror of
    test_unchanged_content_stays_suppressed_despite_a_fresh_export_stamp: the
    file target survives, but a rejected section within it must still honour
    its own recorded `changed_at`, not the file's fresh export stamp.

    A `.md` file also yields a `__preamble__` section unit (unrejected here),
    so assert on the specific section's absence from the rebuilt content
    rather than on the file being dropped entirely.
    """
    heading = "## Only"
    section_target_address = rejections.section_address(ADDRESS, heading, 0)

    class _SectionPolicy(_LedgerPolicy):
        def __init__(self):
            self._records = [
                RejectionRecord(
                    id=rejection_id_of("snapshot-section", section_target_address),
                    kind="snapshot-section",
                    address=section_target_address,
                    scope="network",
                    rejected_at=REJECTED_AT,
                    machine_id="machine-a",
                )
            ]

    provenance = SnapshotProvenance(
        {
            "snapshot-section": {
                section_target_address: {"changed_at": OLDER, "hash": "x"}
            }
        }
    )
    kept, removed = rejections.filter_snapshot_files(
        FILES, _SectionPolicy(), EXPORTED_AT, provenance=provenance
    )
    assert ADDRESS in kept
    assert "only body" not in kept[ADDRESS]
    assert removed == [section_target_address]


def test_genuinely_readded_content_overrides_the_rejection():
    """The source timestamp is STALE (older than REJECTED_AT) so the two
    directions diverge: ignoring provenance would suppress on the stale
    fallback, honouring it keeps on the fresher recorded `changed_at`."""
    provenance = SnapshotProvenance(
        {"snapshot-file": {ADDRESS: {"changed_at": NEWER, "hash": "x"}}}
    )
    kept, removed = rejections.filter_snapshot_files(
        FILES, _LedgerPolicy(), STALE_EXPORT, provenance=provenance
    )
    assert ADDRESS in kept
    assert removed == []


def test_without_provenance_the_old_behaviour_is_unchanged():
    """The mixed-fleet path: an un-upgraded machine resurrects exactly as today."""
    kept, _removed = rejections.filter_snapshot_files(
        FILES, _LedgerPolicy(), EXPORTED_AT
    )
    assert ADDRESS in kept


def test_settings_keys_honour_provenance_too():
    settings_files = {"settings.json": json.dumps({"model": "opus"})}
    address = rejections.settings_key_address(("model",))

    class _SettingsPolicy(_LedgerPolicy):
        def __init__(self):
            self._records = [
                RejectionRecord(
                    id=rejection_id_of("settings-key", address),
                    kind="settings-key",
                    address=address,
                    scope="network",
                    rejected_at=REJECTED_AT,
                    machine_id="machine-a",
                )
            ]

    provenance = SnapshotProvenance(
        {"settings-key": {address: {"changed_at": OLDER, "hash": "x"}}}
    )
    kept, removed = rejections.filter_settings_blob(
        settings_files, _SettingsPolicy(), EXPORTED_AT, provenance=provenance
    )
    assert "model" not in json.loads(kept["settings.json"])
    assert removed == [address]


OMIT_PROVENANCE = object()


def _repo_with(
    tmp_path, provenance, content="## Only\nonly body\n", timestamp=EXPORTED_AT
):
    repo = tmp_path / "repo"
    (repo / "machines").mkdir(parents=True)
    (repo / "consolidated").mkdir(parents=True)
    snapshot = {
        "machine_id": "machine-b",
        "timestamp": timestamp,
        "files": {"rules/a.md": content},
    }
    if provenance is not OMIT_PROVENANCE:
        snapshot["provenance"] = provenance
    (repo / "machines" / "machine-b.json").write_text(
        json.dumps(snapshot),
        encoding="utf-8",
    )
    return repo


def _consolidated_files(repo):
    payload = json.loads(
        (repo / "consolidated" / "snapshot.json").read_text(encoding="utf-8")
    )
    return payload["files"]


def _record_network_rejection(repo):
    from config_sync_rejections import SharedRejectionStore

    SharedRejectionStore(repo, "machine-a").record(
        RejectionRecord(
            id=rejection_id_of("snapshot-file", ADDRESS),
            kind="snapshot-file",
            address=ADDRESS,
            scope="network",
            rejected_at=REJECTED_AT,
            machine_id="machine-a",
        )
    )


def test_consolidate_honours_a_snapshots_provenance(tmp_path, capsys):
    import config_sync

    repo = _repo_with(
        tmp_path, {"snapshot-file": {ADDRESS: {"changed_at": OLDER, "hash": "x"}}}
    )
    _record_network_rejection(repo)

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert ADDRESS not in _consolidated_files(repo)


def test_consolidate_lets_a_genuine_readd_through(tmp_path, capsys):
    """The source timestamp is STALE (older than REJECTED_AT) so the two
    paths diverge: ignoring provenance would suppress on the stale fallback,
    honouring it keeps on the fresher recorded `changed_at`. See
    test_genuinely_readded_content_overrides_the_rejection for the unit-level
    version of the same discrimination."""
    import config_sync

    repo = _repo_with(
        tmp_path,
        {"snapshot-file": {ADDRESS: {"changed_at": NEWER, "hash": "x"}}},
        timestamp=STALE_EXPORT,
    )
    _record_network_rejection(repo)

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert ADDRESS in _consolidated_files(repo)


def test_a_snapshot_without_provenance_falls_back_to_its_export_stamp(tmp_path, capsys):
    """Mixed fleet: an un-upgraded machine behaves exactly as it does today.

    `OMIT_PROVENANCE` must leave the `provenance` key genuinely absent from
    the written snapshot, not present-and-null: Task 8 makes that distinction
    load-bearing (a missing key is a silent un-upgraded machine, a malformed
    value warns)."""
    import config_sync

    repo = _repo_with(tmp_path, OMIT_PROVENANCE)
    _record_network_rejection(repo)

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert ADDRESS in _consolidated_files(repo)


def test_a_snapshot_without_provenance_does_not_warn(tmp_path, capsys):
    """The mixed-fleet path is expected, not degraded — warning here would fire
    on every sync until the entire fleet upgrades."""
    import config_sync

    repo = _repo_with(tmp_path, OMIT_PROVENANCE)

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    payload = json.loads(
        (repo / "consolidated" / "snapshot.json").read_text(encoding="utf-8")
    )
    assert payload["provenance_warnings"] == []


def test_a_malformed_provenance_map_warns_and_names_the_machine(tmp_path, capsys):
    import config_sync

    repo = _repo_with(tmp_path, "not a dict")

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    payload = json.loads(
        (repo / "consolidated" / "snapshot.json").read_text(encoding="utf-8")
    )
    assert any("machine-b" in warning for warning in payload["provenance_warnings"])


def test_a_malformed_provenance_map_still_consolidates(tmp_path, capsys):
    """Degrades, never aborts — unlike a corrupt rejection ledger."""
    import config_sync

    repo = _repo_with(tmp_path, "not a dict")
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()
    assert "rules/a.md" in _consolidated_files(repo)


def test_a_null_provenance_value_warns_and_still_consolidates(tmp_path, capsys):
    """`null` is a VALUE, not an absent key -- a genuinely un-upgraded machine
    never writes the key at all (see OMIT_PROVENANCE above). A present-but-null
    value is a defect and must warn, not be mistaken for the silent
    mixed-fleet path."""
    import config_sync

    repo = _repo_with(tmp_path, None)

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    payload = json.loads(
        (repo / "consolidated" / "snapshot.json").read_text(encoding="utf-8")
    )
    assert any("machine-b" in warning for warning in payload["provenance_warnings"])
    assert "rules/a.md" in _consolidated_files(repo)


# ---------------------------------------------------------------------------
# Spec §9's fuller warning set: a malformed map warns at every depth, and the
# absent-key mixed-fleet path stays silent.
# ---------------------------------------------------------------------------


def _warnings_from(repo):
    payload = json.loads(
        (repo / "consolidated" / "snapshot.json").read_text(encoding="utf-8")
    )
    return payload["provenance_warnings"]


def test_a_wellformed_map_produces_no_warning():
    assert (
        rejections.provenance_map_defects(
            {"snapshot-file": {ADDRESS: {"changed_at": OLDER, "hash": "x"}}}
        )
        == []
    )


def test_a_unit_merely_absent_from_the_map_is_not_a_defect():
    """§9 rules an absent unit the same silent fallback as an absent key: a file
    created between two exports lands there naturally and is not a defect."""
    assert rejections.provenance_map_defects({"snapshot-file": {}}) == []


def test_a_malformed_kind_section_is_one_line_not_one_per_unit():
    defects = rejections.provenance_map_defects({"snapshot-file": "not a dict"})
    assert len(defects) == 1
    assert "snapshot-file" in defects[0]


def test_every_unusable_entry_is_summarised_into_a_single_counted_line():
    """Deduplication is the point: an operator with a wholly corrupt map needs
    one actionable line naming a count, not one line per addressable unit."""
    defects = rejections.provenance_map_defects(
        {
            "snapshot-file": {
                "rules/a.md": "not a dict",
                "rules/b.md": {"hash": "x"},
                "rules/c.md": {"changed_at": "", "hash": "x"},
                "rules/d.md": {"changed_at": 17, "hash": "x"},
            }
        }
    )
    assert len(defects) == 1
    assert "4 provenance entries" in defects[0]
    assert "rules/a.md" in defects[0]


def test_a_non_dict_kind_section_warns_and_names_the_machine(tmp_path, capsys):
    """`provenance` itself is a dict, so the top-level guard does not fire; the
    per-kind value under it is the malformed one."""
    import config_sync

    repo = _repo_with(tmp_path, {"snapshot-file": "not a dict"})

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert any("machine-b" in warning for warning in _warnings_from(repo))


def test_a_non_dict_entry_warns_and_names_the_machine(tmp_path, capsys):
    import config_sync

    repo = _repo_with(tmp_path, {"snapshot-file": {ADDRESS: "not a dict"}})

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    warnings = _warnings_from(repo)
    assert any("machine-b" in warning and ADDRESS in warning for warning in warnings)


def test_an_entry_with_no_changed_at_warns_and_names_the_machine(tmp_path, capsys):
    """The case §9 names explicitly and the narrower implementation missed: the
    entry is a dict and the hash is there, but `changed_at` is not."""
    import config_sync

    repo = _repo_with(tmp_path, {"snapshot-file": {ADDRESS: {"hash": "x"}}})

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    warnings = _warnings_from(repo)
    assert any("machine-b" in warning and ADDRESS in warning for warning in warnings)


def test_a_malformed_entry_still_falls_back_rather_than_aborting(tmp_path, capsys):
    """Warning is additive: the unit falls back to the export timestamp exactly
    as before, and the fold completes."""
    import config_sync

    repo = _repo_with(tmp_path, {"snapshot-file": {ADDRESS: {"hash": "x"}}})
    _record_network_rejection(repo)

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    # EXPORTED_AT is newer than REJECTED_AT, so the fallback resurrects — the
    # pre-provenance behaviour, unchanged by the warning.
    assert ADDRESS in _consolidated_files(repo)


def test_a_wellformed_map_does_not_warn_through_consolidate(tmp_path, capsys):
    import config_sync

    repo = _repo_with(
        tmp_path, {"snapshot-file": {ADDRESS: {"changed_at": OLDER, "hash": "x"}}}
    )

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert _warnings_from(repo) == []


def test_a_snapshot_with_no_machine_id_warns_that_nobody_can_be_prompted(
    tmp_path, capsys
):
    """Withholding attributes to the holding machine. An unattributable snapshot
    contributes no `withheld` entry, so no operator is ever asked about content
    this run took off them -- which must be said, not swallowed."""
    import config_sync

    repo = tmp_path / "repo"
    (repo / "machines").mkdir(parents=True)
    (repo / "consolidated").mkdir(parents=True)
    # Older than REJECTED_AT, so the rejection genuinely withholds and there IS
    # a prompt to lose.
    (repo / "machines" / "anonymous.json").write_text(
        json.dumps({"timestamp": STALE_EXPORT, "files": {ADDRESS: "## Only\nonly\n"}}),
        encoding="utf-8",
    )
    _record_network_rejection(repo)

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    payload = json.loads(
        (repo / "consolidated" / "snapshot.json").read_text(encoding="utf-8")
    )
    assert payload["withheld"] == []
    assert any(
        "machine_id" in warning and ADDRESS in warning
        for warning in payload["provenance_warnings"]
    )


def test_a_snapshot_with_no_machine_id_and_nothing_withheld_stays_silent(
    tmp_path, capsys
):
    """Only a LOST prompt is worth a line. An unattributable snapshot that lost
    nothing costs the operator nothing."""
    import config_sync

    repo = tmp_path / "repo"
    (repo / "machines").mkdir(parents=True)
    (repo / "consolidated").mkdir(parents=True)
    (repo / "machines" / "anonymous.json").write_text(
        json.dumps({"timestamp": EXPORTED_AT, "files": {ADDRESS: "## Only\nonly\n"}}),
        encoding="utf-8",
    )

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    payload = json.loads(
        (repo / "consolidated" / "snapshot.json").read_text(encoding="utf-8")
    )
    assert payload["provenance_warnings"] == []
