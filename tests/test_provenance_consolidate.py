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
