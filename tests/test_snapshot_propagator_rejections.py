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

# Production-shaped, and deliberately NEWER than every rejection recorded here.
# `cmd_consolidate` restamps this field with `datetime.now(UTC)` on every run, so
# in production it is always newer than any rejection. A fixture that omitted it
# made `filter_snapshot_files` take its `if not source_timestamp` branch, and the
# local-scope tests below passed for a reason production never reproduces.
CONSOLIDATED_AT = "2026-08-03T12:00:00+00:00"
REJECTED_AT = "2026-08-03T09:00:00+00:00"


def _context(tmp_path):
    context = SyncContext(claude_dir=tmp_path / "claude", repo_dir=tmp_path / "repo")
    (context.repo_dir / "consolidated").mkdir(parents=True)
    (context.repo_dir / "consolidated" / "snapshot.json").write_text(
        json.dumps({"timestamp": CONSOLIDATED_AT, "files": {"CLAUDE.md": DOCUMENT}}),
        encoding="utf-8",
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
            rejected_at=REJECTED_AT,
            machine_id="machine-a",
        )
    )
    return CompositeRejectionPolicy([store])


def test_without_a_policy_apply_behaves_exactly_as_before(tmp_path):
    context = _context(tmp_path)
    SnapshotPropagator().apply(context)
    # Byte-identical, not merely "contains": the no-policy path must not rewrite
    # a single character of the snapshot's content, and a substring check would
    # miss a stray newline introduced by an accidental parse/rejoin round trip.
    assert (context.claude_dir / "CLAUDE.md").read_text(encoding="utf-8") == DOCUMENT


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


def test_a_rejection_older_than_the_snapshots_timestamp_still_suppresses(tmp_path):
    """The consolidated snapshot's `timestamp` is its GENERATION time, restamped
    to now on every `consolidate` run — never content provenance. Were it passed
    as `source_timestamp`, every local rejection would look stale and `--scope
    local` would suppress nothing in production. `REJECTED_AT` is deliberately
    three hours older than `CONSOLIDATED_AT` here, so this test fails the moment
    anyone reconnects the field.
    """
    context = _context(tmp_path)
    assert REJECTED_AT < CONSOLIDATED_AT
    address = section_address("CLAUDE.md", STALE, 0)
    result = SnapshotPropagator(policy=_local_policy(tmp_path, address)).apply(context)
    assert result.rejection_removals == [address]
    assert STALE not in (context.claude_dir / "CLAUDE.md").read_text(encoding="utf-8")
