"""A local veto withholds content from THIS machine without touching the repo."""

import json

from config_sync_propagators import SnapshotPropagator, SyncContext
from config_sync_rejections import (
    CompositeRejectionPolicy,
    LocalRejectionStore,
    RejectionRecord,
    rejection_id_of,
    section_address,
)

STALE = "## Memory protocol"
DOCUMENT = f"# User Preferences\n\n{STALE}\n\nuse the /memory skill\n"


def _context(tmp_path):
    context = SyncContext(claude_dir=tmp_path / "claude", repo_dir=tmp_path / "repo")
    (context.repo_dir / "consolidated").mkdir(parents=True)
    (context.repo_dir / "consolidated" / "snapshot.json").write_text(
        json.dumps({"files": {"CLAUDE.md": DOCUMENT}}), encoding="utf-8"
    )
    context.claude_dir.mkdir(parents=True, exist_ok=True)
    return context


def _local_policy(tmp_path, address, kind="snapshot-section"):
    store = LocalRejectionStore(tmp_path / "local.json")
    store.record(
        RejectionRecord(
            id=rejection_id_of(kind, address),
            kind=kind,
            address=address,
            scope="local",
            rejected_at="2026-08-03T09:00:00+00:00",
            machine_id="machine-a",
        )
    )
    return CompositeRejectionPolicy([store])


def test_without_a_policy_apply_behaves_exactly_as_before(tmp_path):
    context = _context(tmp_path)
    SnapshotPropagator().apply(context)
    assert STALE in (context.claude_dir / "CLAUDE.md").read_text(encoding="utf-8")


def test_a_locally_rejected_section_is_never_written(tmp_path):
    context = _context(tmp_path)
    policy = _local_policy(tmp_path, section_address("CLAUDE.md", STALE, 0))
    SnapshotPropagator(policy=policy).apply(context)
    written = (context.claude_dir / "CLAUDE.md").read_text(encoding="utf-8")
    assert STALE not in written
    assert "# User Preferences" in written


def test_the_shared_snapshot_is_left_untouched(tmp_path):
    context = _context(tmp_path)
    policy = _local_policy(tmp_path, section_address("CLAUDE.md", STALE, 0))
    SnapshotPropagator(policy=policy).apply(context)
    snapshot = json.loads(
        (context.repo_dir / "consolidated" / "snapshot.json").read_text(
            encoding="utf-8"
        )
    )
    assert STALE in snapshot["files"]["CLAUDE.md"]


def test_removed_addresses_are_reported_for_the_operator(tmp_path):
    context = _context(tmp_path)
    address = section_address("CLAUDE.md", STALE, 0)
    result = SnapshotPropagator(policy=_local_policy(tmp_path, address)).apply(context)
    assert result.rejection_removals == [address]
