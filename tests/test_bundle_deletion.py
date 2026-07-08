from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import config_sync_propagators as propagators  # noqa: E402


def _iso(text):
    # Small helper so tests read clearly; any ISO-8601 UTC string works.
    return text


def test_previously_exported_is_empty_without_index(tmp_path):
    ledger = propagators.BundleDeletionLedger()
    assert ledger.previously_exported(tmp_path, "machine-a") == set()


def test_record_export_round_trips(tmp_path):
    ledger = propagators.BundleDeletionLedger()
    ledger.record_export(tmp_path, "machine-a", {"skill/foo", "agent/bar"})
    assert ledger.previously_exported(tmp_path, "machine-a") == {"skill/foo", "agent/bar"}


def test_tombstone_write_read_and_clear(tmp_path):
    ledger = propagators.BundleDeletionLedger()
    ledger.tombstone(tmp_path, "skill", "gof", "machine-a", "2026-07-08T00:00:00+00:00")
    tombstone = ledger.tombstone_for(tmp_path, "skill", "gof")
    assert tombstone is not None
    assert tombstone.kind == "skill" and tombstone.name == "gof"
    assert tombstone.machine_id == "machine-a"
    assert [entry.name for entry in ledger.tombstones(tmp_path)] == ["gof"]
    ledger.clear_tombstone(tmp_path, "skill", "gof")
    assert ledger.tombstone_for(tmp_path, "skill", "gof") is None
    assert ledger.tombstones(tmp_path) == []


def test_is_deleted_compares_timestamps(tmp_path):
    ledger = propagators.BundleDeletionLedger()
    ledger.tombstone(tmp_path, "skill", "gof", "machine-a", "2026-07-08T12:00:00+00:00")
    # tombstone newer than the bundle export -> deleted wins
    assert ledger.is_deleted(tmp_path, "skill", "gof", "2026-07-08T11:00:00+00:00") is True
    # bundle re-exported after the tombstone -> not deleted
    assert ledger.is_deleted(tmp_path, "skill", "gof", "2026-07-08T13:00:00+00:00") is False
    # equal timestamps -> not deleted (strict >)
    assert ledger.is_deleted(tmp_path, "skill", "gof", "2026-07-08T12:00:00+00:00") is False
    # missing bundle export ("") -> tombstone wins
    assert ledger.is_deleted(tmp_path, "skill", "gof", "") is True
    # no tombstone -> not deleted
    assert ledger.is_deleted(tmp_path, "agent", "none", "") is False


def test_tombstone_rejects_name_with_separator(tmp_path):
    import pytest
    ledger = propagators.BundleDeletionLedger()
    with pytest.raises(ValueError):
        ledger.tombstone(tmp_path, "skill", "a/b", "machine-a", "2026-07-08T00:00:00+00:00")
