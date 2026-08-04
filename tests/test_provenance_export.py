"""Export records when each unit last changed, using its own previous snapshot."""

import json

from config_sync_propagators import SnapshotPropagator, SyncContext

MACHINE_FILE = "machines/{machine_id}.json"


def _context(tmp_path):
    context = SyncContext(claude_dir=tmp_path / "claude", repo_dir=tmp_path / "repo")
    context.claude_dir.mkdir(parents=True, exist_ok=True)
    (context.claude_dir / "CLAUDE.md").write_text(
        "## Alpha\nalpha\n\n## Beta\nbeta\n", encoding="utf-8"
    )
    context.repo_dir.mkdir(parents=True, exist_ok=True)
    return context


def _exported(context):
    machine_files = list((context.repo_dir / "machines").glob("*.json"))
    assert len(machine_files) == 1
    return json.loads(machine_files[0].read_text(encoding="utf-8"))


def test_export_writes_a_provenance_map(tmp_path):
    context = _context(tmp_path)
    SnapshotPropagator().export(context)
    snapshot = _exported(context)
    assert "provenance" in snapshot
    assert "CLAUDE.md" in snapshot["provenance"]["snapshot-file"]


def test_export_keeps_its_own_timestamp_field(tmp_path):
    """The mixed-fleet fallback reads it; it must not be removed or repurposed."""
    context = _context(tmp_path)
    SnapshotPropagator().export(context)
    assert _exported(context)["timestamp"]


def test_a_second_export_of_unchanged_content_carries_changed_at_forward(tmp_path):
    context = _context(tmp_path)
    SnapshotPropagator().export(context)
    first = _exported(context)["provenance"]["snapshot-file"]["CLAUDE.md"]["changed_at"]

    SnapshotPropagator().export(context)
    second = _exported(context)["provenance"]["snapshot-file"]["CLAUDE.md"][
        "changed_at"
    ]
    assert second == first


def test_editing_content_restamps_it(tmp_path):
    context = _context(tmp_path)
    SnapshotPropagator().export(context)
    first = _exported(context)["provenance"]["snapshot-file"]["CLAUDE.md"]["changed_at"]

    (context.claude_dir / "CLAUDE.md").write_text(
        "## Alpha\nEDITED\n\n## Beta\nbeta\n", encoding="utf-8"
    )
    SnapshotPropagator().export(context)
    second = _exported(context)["provenance"]["snapshot-file"]["CLAUDE.md"][
        "changed_at"
    ]
    assert second != first


def test_an_unreadable_previous_snapshot_restamps_rather_than_aborting(tmp_path):
    context = _context(tmp_path)
    SnapshotPropagator().export(context)
    machine_file = list((context.repo_dir / "machines").glob("*.json"))[0]
    machine_file.write_text("{not json", encoding="utf-8")

    SnapshotPropagator().export(context)
    assert _exported(context)["provenance"]["snapshot-file"]["CLAUDE.md"]["changed_at"]


def test_the_stamper_is_injectable(tmp_path):
    """The seam: a caller can substitute the stamper without touching export."""

    class _FixedStamper:
        def stamp(self, files, previous, now):
            return {"snapshot-file": {"sentinel": {"changed_at": now, "hash": "x"}}}

    context = _context(tmp_path)
    SnapshotPropagator(stamper=_FixedStamper()).export(context)
    assert "sentinel" in _exported(context)["provenance"]["snapshot-file"]


def test_a_first_export_does_not_warn(tmp_path):
    """No previous snapshot is normal, not degraded."""
    context = _context(tmp_path)
    result = SnapshotPropagator().export(context)
    assert result.warnings == []


def test_an_unreadable_previous_snapshot_warns(tmp_path):
    context = _context(tmp_path)
    SnapshotPropagator().export(context)
    machine_file = list((context.repo_dir / "machines").glob("*.json"))[0]
    machine_file.write_text("{not json", encoding="utf-8")

    result = SnapshotPropagator().export(context)
    assert any("provenance" in warning for warning in result.warnings)
