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


def _write_skill(claude_dir, name, files):
    skill_dir = claude_dir / "skills" / name
    for relative_path, content in files.items():
        target = skill_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return skill_dir


def _context(tmp_path):
    claude_dir = tmp_path / "claude"
    repo_dir = tmp_path / "repo"
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "config-sync-machine-id").write_text("machine-a")
    return propagators.SyncContext(claude_dir=claude_dir, repo_dir=repo_dir)


def test_export_tombstones_and_prunes_a_deleted_skill(tmp_path):
    context = _context(tmp_path)
    skill_dir = _write_skill(context.claude_dir, "gof", {"SKILL.md": "# gof"})
    bundle_propagator = propagators.ContentBundlePropagator()

    bundle_propagator.export(context)  # first export: records index, writes bundle
    assert (context.repo_dir / "bundles" / "skills" / "gof").exists()

    import shutil
    shutil.rmtree(skill_dir)  # user deletes the skill locally
    result = bundle_propagator.export(context)  # second export: should detect deletion

    assert "skill/gof" in result.tombstoned
    assert not (context.repo_dir / "bundles" / "skills" / "gof").exists()  # bundle pruned
    assert propagators.BundleDeletionLedger().tombstone_for(context.repo_dir, "skill", "gof") is not None


def test_export_reexport_supersedes_tombstone(tmp_path):
    context = _context(tmp_path)
    ledger = propagators.BundleDeletionLedger()
    ledger.tombstone(context.repo_dir, "skill", "gof", "machine-b", "2000-01-01T00:00:00+00:00")
    _write_skill(context.claude_dir, "gof", {"SKILL.md": "# gof back"})

    propagators.ContentBundlePropagator().export(context)

    assert ledger.tombstone_for(context.repo_dir, "skill", "gof") is None  # re-add cleared it
    assert (context.repo_dir / "bundles" / "skills" / "gof").exists()


def test_first_export_tombstones_nothing(tmp_path):
    context = _context(tmp_path)
    _write_skill(context.claude_dir, "keep", {"SKILL.md": "# keep"})
    result = propagators.ContentBundlePropagator().export(context)
    assert result.tombstoned == []
