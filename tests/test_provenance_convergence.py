"""Two machines, one rejection: the convergence the ledger could not reach.

Machine B still holds content machine A rejected. Before per-content provenance,
B's re-export carried a fresh wall-clock stamp, read as a deliberate re-add, and
resurrected the content on every sync. These walks drive the real export and the
real consolidate end to end.
"""

import json
from datetime import UTC, datetime

import config_sync
from config_sync_propagators import SnapshotPropagator, SyncContext
from config_sync_rejections import (
    RejectionRecord,
    SharedRejectionStore,
    rejection_id_of,
)

CONTENT = "## Alpha\nalpha body\n\n## Beta\nbeta body\n"
FILE_ADDRESS = "CLAUDE.md"


def _machine(tmp_path, repo, name, content=CONTENT):
    claude_dir = tmp_path / name
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "CLAUDE.md").write_text(content, encoding="utf-8")
    return SyncContext(claude_dir=claude_dir, repo_dir=repo)


def _reject_file(repo, address=FILE_ADDRESS, rejected_at=None):
    # `rejected_at` defaults to real "now" at the moment of rejection, not a
    # fixed calendar literal. TimestampedRejectionRule.suppresses compares
    # `source_timestamp <= rejected_at` against a `changed_at` these walks get
    # from the REAL SnapshotPropagator.export, which stamps from the real
    # wall clock. A hardcoded past date only threads the needle -- newer than
    # the export that preceded it, older than any edit that follows -- until
    # the real clock catches up to it; then it stops being newer than
    # anything and every suppression assertion in this file fails, not
    # because the mechanism broke but because the fixture's assumed "today"
    # expired. Anchoring to call-time "now" keeps the walk meaningful
    # indefinitely instead of quietly rotting on a specific date.
    if rejected_at is None:
        rejected_at = datetime.now(UTC).isoformat()
    SharedRejectionStore(repo, "machine-a").record(
        RejectionRecord(
            id=rejection_id_of("snapshot-file", address),
            kind="snapshot-file",
            address=address,
            scope="network",
            rejected_at=rejected_at,
            machine_id="machine-a",
        )
    )


def _consolidated(repo):
    return json.loads(
        (repo / "consolidated" / "snapshot.json").read_text(encoding="utf-8")
    )["files"]


def _repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "consolidated").mkdir(parents=True)
    return repo


def test_an_unchanged_reexport_no_longer_resurrects_rejected_content(tmp_path, capsys):
    """THE HEADLINE. This fails without provenance -- it is the bug."""
    repo = _repo(tmp_path)
    context = _machine(tmp_path, repo, "machine-b")

    SnapshotPropagator().export(context)  # B holds the content
    _reject_file(repo)  # A rejects it
    SnapshotPropagator().export(context)  # B re-exports, untouched
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert FILE_ADDRESS not in _consolidated(repo)


def test_a_genuine_readd_still_overrides_the_rejection(tmp_path, capsys):
    repo = _repo(tmp_path)
    context = _machine(tmp_path, repo, "machine-b")

    SnapshotPropagator().export(context)
    _reject_file(repo)
    (context.claude_dir / "CLAUDE.md").write_text(
        "## Alpha\nDELIBERATELY REWRITTEN\n", encoding="utf-8"
    )
    SnapshotPropagator().export(context)
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert FILE_ADDRESS in _consolidated(repo)


def test_convergence_holds_across_repeated_syncs(tmp_path, capsys):
    """Carry-forward at the walk level: a sliding changed_at would resurrect on
    the second or third sync, not the first."""
    repo = _repo(tmp_path)
    context = _machine(tmp_path, repo, "machine-b")

    SnapshotPropagator().export(context)
    _reject_file(repo)
    for _ in range(3):
        SnapshotPropagator().export(context)
        config_sync.cmd_consolidate(str(repo))
        capsys.readouterr()
        assert FILE_ADDRESS not in _consolidated(repo)


def test_editing_a_sibling_section_does_not_resurrect_a_rejected_section(
    tmp_path, capsys
):
    """The finer-grained case the whole-file mtime approach could not express."""
    from config_sync_rejections import section_address

    repo = _repo(tmp_path)
    context = _machine(tmp_path, repo, "machine-b")
    beta_address = section_address("CLAUDE.md", "## Beta", 0)

    SnapshotPropagator().export(context)
    SharedRejectionStore(repo, "machine-a").record(
        RejectionRecord(
            id=rejection_id_of("snapshot-section", beta_address),
            kind="snapshot-section",
            address=beta_address,
            scope="network",
            rejected_at=datetime.now(UTC).isoformat(),
            machine_id="machine-a",
        )
    )
    (context.claude_dir / "CLAUDE.md").write_text(
        "## Alpha\nEDITED ALPHA\n\n## Beta\nbeta body\n", encoding="utf-8"
    )
    SnapshotPropagator().export(context)
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    merged = _consolidated(repo)["CLAUDE.md"]
    assert "EDITED ALPHA" in merged
    assert "beta body" not in merged


def test_an_unupgraded_machine_still_resurrects_until_it_upgrades(tmp_path, capsys):
    """Mixed fleet, end to end: the fallback is per-machine, not fleet-wide."""
    repo = _repo(tmp_path)
    (repo / "machines").mkdir(parents=True, exist_ok=True)
    (repo / "machines" / "machine-old.json").write_text(
        json.dumps(
            {
                "machine_id": "machine-old",
                "timestamp": "2026-08-09T09:00:00+00:00",
                "files": {"CLAUDE.md": CONTENT},
            }
        ),
        encoding="utf-8",
    )
    _reject_file(repo)

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert FILE_ADDRESS in _consolidated(repo)
