"""One rejection walked across every module boundary it touches.

Every other rejection suite is unit-scoped: the stores, the rule, the composite,
the addressors, the CLI, consolidate, apply — each proven alone. The one test
that crossed two modules was also the one whose fixture omitted the consolidated
snapshot's `timestamp`, which is precisely how a defect that made `--scope local`
inert in production survived a green suite.

So this walks the real cycle with production-shaped timestamps, in order:

    reject --scope network
        -> consolidate            (the rejecting machine forgets it)
        -> another machine re-adds it, consolidate    (the convergence limit)
        -> propagate-apply        (withheld locally, reported for Step 4e)
        -> resolve-rejection keep (this machine overrules)
        -> consolidate            (it returns for everyone)

The `claude_home` fixture is mandatory here, not decorative: `cmd_reject`,
`_machine_id` and `cmd_propagate_apply` all read `config_sync.CLAUDE_DIR`, and
without the redirect this test would record rejections in and write files to the
operator's real `~/.claude`.
"""

import json

import pytest

import config_sync
from config_sync_rejections import section_address

STALE = "## Memory protocol"
DOCUMENT = f"# User Preferences\n\n{STALE}\n\nuse the /memory skill\n"

# Production shape: every machine snapshot carries the time its export ran, and
# `cmd_consolidate` restamps the consolidated snapshot with `datetime.now(UTC)`
# on every run — always newer than anything already recorded.
BEFORE_THE_REJECTION = "2026-08-03T08:00:00+00:00"
AFTER_THE_REJECTION = "2999-01-01T00:00:00+00:00"


@pytest.fixture(autouse=True)
def _isolated_claude_home(claude_home):
    return claude_home


def _machine_snapshot(repo, machine_id, files, timestamp):
    (repo / "machines").mkdir(parents=True, exist_ok=True)
    (repo / "machines" / f"{machine_id}.json").write_text(
        json.dumps({"machine_id": machine_id, "timestamp": timestamp, "files": files}),
        encoding="utf-8",
    )


def _consolidated(repo):
    return json.loads(
        (repo / "consolidated" / "snapshot.json").read_text(encoding="utf-8")
    )


def _shared_ledger(repo, machine_id):
    return json.loads(
        (repo / "rejections" / f"{machine_id}.json").read_text(encoding="utf-8")
    )["rejections"]


def test_a_network_rejection_travels_the_whole_sync_cycle(tmp_path, capsys):
    repo = tmp_path / "repo"
    this_machine = config_sync._machine_id()
    address = section_address("CLAUDE.md", STALE, 0)

    # --- Hop 0: a second machine's snapshot seeds the content ------------------
    _machine_snapshot(repo, "machine-b", {"CLAUDE.md": DOCUMENT}, BEFORE_THE_REJECTION)
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()
    assert STALE in _consolidated(repo)["files"]["CLAUDE.md"]
    # The generation timestamp that C1 must never be allowed to consult.
    assert _consolidated(repo)["timestamp"] > BEFORE_THE_REJECTION

    # --- Hop 1: reject it network-wide ---------------------------------------
    config_sync.cmd_reject(
        str(repo), "snapshot-section", "CLAUDE.md", "--section", STALE
    )
    recorded = json.loads(capsys.readouterr().out)
    assert recorded["scope"] == "network"
    assert recorded["address"] == address
    # In the shared repo, so it can be committed and reach other machines.
    assert [entry["id"] for entry in _shared_ledger(repo, this_machine)] == [
        recorded["id"]
    ]

    # --- Hop 2: consolidate strips it ----------------------------------------
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()
    assert STALE not in _consolidated(repo)["files"]["CLAUDE.md"]
    assert address in _consolidated(repo)["rejected"]

    # --- Hop 3: a machine that still holds it re-adds it ----------------------
    # The documented phase-1 convergence limit, asserted rather than wished away:
    # machine-b exports before anyone consolidates, and its export is stamped
    # later than the rejection, so the engine cannot tell an unchanged re-export
    # from a deliberate re-add. Fixing that needs per-content provenance (phase 2).
    _machine_snapshot(repo, "machine-b", {"CLAUDE.md": DOCUMENT}, AFTER_THE_REJECTION)
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()
    assert STALE in _consolidated(repo)["files"]["CLAUDE.md"]

    # --- Hop 4: apply withholds it here and reports it for Step 4e ------------
    # THE hop that would have caught C1. The consolidated snapshot now carries a
    # realistic `timestamp` newer than the rejection; passing it as
    # `source_timestamp` makes every rejection read as stale and writes STALE
    # straight back into the operator's CLAUDE.md.
    config_sync.cmd_propagate_apply(str(repo))
    applied = json.loads(capsys.readouterr().out)

    removals = applied["snapshot"]["rejection_removals"]
    assert [entry["address"] for entry in removals] == [address]
    # Everything Step 4e's prompt and command need, none of which an address has.
    assert removals[0]["id"] == recorded["id"]
    assert removals[0]["machine_id"] == this_machine
    assert removals[0]["rejected_at"] == recorded["rejected_at"]
    assert removals[0]["scope"] == "network"

    local_claude_md = (config_sync.CLAUDE_DIR / "CLAUDE.md").read_text(encoding="utf-8")
    assert STALE not in local_claude_md
    assert "# User Preferences" in local_claude_md
    # Withheld locally only — the shared snapshot is not ours to edit at apply.
    assert STALE in _consolidated(repo)["files"]["CLAUDE.md"]

    # --- Hop 5: this machine overrules the rejection -------------------------
    config_sync.cmd_resolve_rejection(str(repo), recorded["id"], "keep")
    capsys.readouterr()
    revivals = [
        entry
        for entry in _shared_ledger(repo, this_machine)
        if entry["revives"] == recorded["id"]
    ]
    assert len(revivals) == 1
    assert revivals[0]["rejected_at"] > recorded["rejected_at"]
    # The original is not deleted — a revival wins on timestamp, it does not edit
    # the record it overrules.
    assert any(
        entry["id"] == recorded["id"] for entry in _shared_ledger(repo, this_machine)
    )

    # --- Hop 6: it returns for everyone --------------------------------------
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()
    assert STALE in _consolidated(repo)["files"]["CLAUDE.md"]
    assert address not in _consolidated(repo)["rejected"]

    config_sync.cmd_propagate_apply(str(repo))
    reapplied = json.loads(capsys.readouterr().out)
    assert reapplied["snapshot"]["rejection_removals"] == []
    assert STALE in (config_sync.CLAUDE_DIR / "CLAUDE.md").read_text(encoding="utf-8")


def test_remove_withholds_the_content_from_the_next_apply(tmp_path, capsys):
    """The other half of Step 4e, end to end: answering `remove` must actually
    change what the next apply writes. Before this branch it recorded nothing, so
    the operator answered the same prompt on every sync forever."""
    repo = tmp_path / "repo"
    this_machine = config_sync._machine_id()

    _machine_snapshot(
        repo, "machine-b", {"rules/a.md": "unwanted\n"}, "2026-08-03T08:00:00+00:00"
    )
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    config_sync.cmd_reject(str(repo), "snapshot-file", "rules/a.md")
    rejection_id = json.loads(capsys.readouterr().out)["id"]

    # Overrule it first, so the content survives consolidate and reaches apply —
    # the state another machine is in when it is asked to answer.
    config_sync.cmd_resolve_rejection(str(repo), rejection_id, "keep")
    capsys.readouterr()
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()
    config_sync.cmd_propagate_apply(str(repo))
    capsys.readouterr()
    assert (config_sync.CLAUDE_DIR / "rules" / "a.md").exists()

    # Now change our mind: `remove` records a LOCAL rejection, newer than the
    # revival, so the next apply withholds the file.
    config_sync.cmd_resolve_rejection(str(repo), rejection_id, "remove")
    capsys.readouterr()

    local_ledger = json.loads(
        (config_sync.CLAUDE_DIR / "config-sync-rejections.json").read_text(
            encoding="utf-8"
        )
    )["rejections"]
    assert [entry["scope"] for entry in local_ledger] == ["local"]

    # The next sync consolidates before it applies, so the snapshot apply reads
    # is restamped NEWER than the `remove` record. That ordering is what made C1
    # invisible to a test that applied an already-stale snapshot.
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()
    assert _consolidated(repo)["timestamp"] > local_ledger[0]["rejected_at"]

    config_sync.cmd_propagate_apply(str(repo))
    applied = json.loads(capsys.readouterr().out)
    assert [
        entry["address"] for entry in applied["snapshot"]["rejection_removals"]
    ] == ["rules/a.md"]

    # A local veto never reaches shared state: the file is still in the snapshot
    # for every other machine, and nothing local was written into the repo.
    assert "rules/a.md" in _consolidated(repo)["files"]
    assert all(
        entry["scope"] == "network" for entry in _shared_ledger(repo, this_machine)
    )
