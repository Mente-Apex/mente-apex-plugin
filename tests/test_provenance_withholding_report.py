"""Consolidate withholds upstream — the machine that held the content must be told.

Phase 3 made `cmd_consolidate` subtract rejected content from every incoming
machine snapshot, so it never reaches `consolidated/snapshot.json` at all. That
closed the resurrection bug and silently closed the Step 4e prompt with it:
`SnapshotPropagator.apply` had nothing left to filter, `rejection_removals` came
back empty, and the operator whose machine still held the content was never
asked. Once that machine re-exports its post-apply disk, the content is
recoverable only from git history.

These walks cover the `withheld` report that carries the withholding from
consolidate on one machine to apply on another, and the escape hatch it revives.
"""

import json

import pytest

import config_sync
from config_sync_propagators import SnapshotPropagator, SyncContext
from config_sync_rejections import (
    CompositeRejectionPolicy,
    RejectionRecord,
    SharedRejectionStore,
    rejection_id_of,
    section_address,
    settings_key_address,
)

STALE = "## Memory protocol"
DOCUMENT = f"# User Preferences\n\n{STALE}\n\nuse the /memory skill\n"

# Two fixtures whose ORDER is the fixture, not their calendar value: an export
# stamped before a rejection is what makes the rejection read as fresher intent
# and the content get withheld. Nothing here is compared against "now", so
# neither literal can rot the way an absolute "must still be in the future"
# date would.
EXPORTED_AT = "2026-08-03T08:00:00+00:00"
REJECTED_AT = "2026-08-03T09:00:00+00:00"

SECTION_ADDRESS = section_address("CLAUDE.md", STALE, 0)
SETTINGS_ADDRESS = settings_key_address(("model",))


def _repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "consolidated").mkdir(parents=True)
    return repo


def _machine_snapshot(repo, machine_id, files, timestamp=EXPORTED_AT):
    (repo / "machines").mkdir(parents=True, exist_ok=True)
    (repo / "machines" / f"{machine_id}.json").write_text(
        json.dumps({"machine_id": machine_id, "timestamp": timestamp, "files": files}),
        encoding="utf-8",
    )


def _reject(repo, kind, address, rejecting_machine="machine-a"):
    SharedRejectionStore(repo, rejecting_machine).record(
        RejectionRecord(
            id=rejection_id_of(kind, address),
            kind=kind,
            address=address,
            scope="network",
            rejected_at=REJECTED_AT,
            machine_id=rejecting_machine,
        )
    )


def _consolidated(repo):
    return json.loads(
        (repo / "consolidated" / "snapshot.json").read_text(encoding="utf-8")
    )


# ---------------------------------------------------------------------------
# Layer 1 — consolidate records the withholding, with its machine attribution
# ---------------------------------------------------------------------------


def test_a_withheld_section_is_recorded_against_the_machine_that_held_it(
    tmp_path, capsys
):
    repo = _repo(tmp_path)
    _machine_snapshot(repo, "machine-b", {"CLAUDE.md": DOCUMENT})
    _reject(repo, "snapshot-section", SECTION_ADDRESS)

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    # The document, not stdout: this is the only channel that survives to the
    # apply running on another machine.
    assert _consolidated(repo)["withheld"] == [
        {"machine_id": "machine-b", "address": SECTION_ADDRESS}
    ]
    # And the content really is still withheld — a report, not a resurrection.
    assert STALE not in _consolidated(repo)["files"]["CLAUDE.md"]


def test_a_withheld_settings_key_is_recorded_against_the_machine_that_held_it(
    tmp_path, capsys
):
    repo = _repo(tmp_path)
    _machine_snapshot(
        repo, "machine-b", {"settings.json": json.dumps({"model": "opus", "env": {}})}
    )
    _reject(repo, "settings-key", SETTINGS_ADDRESS)

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert _consolidated(repo)["withheld"] == [
        {"machine_id": "machine-b", "address": SETTINGS_ADDRESS}
    ]
    assert "model" not in json.loads(_consolidated(repo)["files"]["settings.json"])


def test_each_holder_of_the_same_address_is_named_separately(tmp_path, capsys):
    """Two machines held it, so two operators have a recovery window."""
    repo = _repo(tmp_path)
    _machine_snapshot(repo, "machine-b", {"CLAUDE.md": DOCUMENT})
    _machine_snapshot(repo, "machine-c", {"CLAUDE.md": DOCUMENT})
    _reject(repo, "snapshot-section", SECTION_ADDRESS)

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert _consolidated(repo)["withheld"] == [
        {"machine_id": "machine-b", "address": SECTION_ADDRESS},
        {"machine_id": "machine-c", "address": SECTION_ADDRESS},
    ]
    # `rejected` stays the flat, deduped audit trail it has always been.
    assert _consolidated(repo)["rejected"] == [SECTION_ADDRESS]


def test_the_same_holder_is_named_once_across_repeated_consolidates(tmp_path, capsys):
    """`withheld` is rebuilt from the machine snapshots every run, so a fleet
    that syncs daily must not accumulate one entry per sync forever."""
    repo = _repo(tmp_path)
    _machine_snapshot(repo, "machine-b", {"CLAUDE.md": DOCUMENT})
    _reject(repo, "snapshot-section", SECTION_ADDRESS)

    for _ in range(3):
        config_sync.cmd_consolidate(str(repo))
        capsys.readouterr()
        assert _consolidated(repo)["withheld"] == [
            {"machine_id": "machine-b", "address": SECTION_ADDRESS}
        ]


def test_a_withholding_from_the_prior_consolidated_snapshot_names_nobody(
    tmp_path, capsys
):
    """The ratchet's own removals have no holder to attribute them to.

    `base_files` is the previous consolidated snapshot: consolidate knows the
    address it took out of it, but not which machine's disk still carries it.
    Reporting it against every machine would prompt operators who never held it,
    so it stays in `rejected` — the audit trail — and out of `withheld`.
    """
    repo = _repo(tmp_path)
    (repo / "consolidated" / "snapshot.json").write_text(
        json.dumps({"timestamp": EXPORTED_AT, "files": {"CLAUDE.md": DOCUMENT}}),
        encoding="utf-8",
    )
    _reject(repo, "snapshot-section", SECTION_ADDRESS)

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert _consolidated(repo)["rejected"] == [SECTION_ADDRESS]
    assert _consolidated(repo)["withheld"] == []


def test_the_withholding_report_is_echoed_on_stdout(tmp_path, capsys):
    """Parity with `rejected`, `merge_log` and `provenance_warnings`: every other
    key consolidate reports reaches stdout as well as the file, and a report the
    operator can only find by opening `consolidated/snapshot.json` is not one
    they will find. The skill does not read this output today -- Step 3 runs
    `consolidate` and consumes nothing from it -- so this pins the shape, not a
    consumer."""
    repo = _repo(tmp_path)
    _machine_snapshot(repo, "machine-b", {"CLAUDE.md": DOCUMENT})
    _reject(repo, "snapshot-section", SECTION_ADDRESS)

    config_sync.cmd_consolidate(str(repo))

    assert json.loads(capsys.readouterr().out)["withheld"] == [
        {"machine_id": "machine-b", "address": SECTION_ADDRESS}
    ]


# ---------------------------------------------------------------------------
# Layer 2 — apply tells the machine that held it, and only that machine
# ---------------------------------------------------------------------------


def _applying_machine(tmp_path, repo, machine_id):
    claude_dir = tmp_path / machine_id
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "config-sync-machine-id").write_text(machine_id, encoding="utf-8")
    return SyncContext(claude_dir=claude_dir, repo_dir=repo)


def _network_policy(repo, machine_id):
    return CompositeRejectionPolicy([SharedRejectionStore(repo, machine_id)])


def _consolidated_with_withholding(repo, withheld):
    (repo / "consolidated" / "snapshot.json").write_text(
        json.dumps(
            {
                "timestamp": REJECTED_AT,
                "files": {"CLAUDE.md": "# User Preferences\n"},
                "withheld": withheld,
            }
        ),
        encoding="utf-8",
    )


def test_the_machine_that_held_the_content_is_told(tmp_path):
    repo = _repo(tmp_path)
    _reject(repo, "snapshot-section", SECTION_ADDRESS)
    _consolidated_with_withholding(
        repo, [{"machine_id": "machine-b", "address": SECTION_ADDRESS}]
    )
    context = _applying_machine(tmp_path, repo, "machine-b")

    result = SnapshotPropagator(policy=_network_policy(repo, "machine-b")).apply(
        context
    )

    # The whole ledger record, exactly as the pre-branch prompt received it:
    # `id` is what `resolve-rejection` takes, the rest is what the prompt shows.
    assert [record.address for record in result.rejection_removals] == [SECTION_ADDRESS]
    assert result.rejection_removals[0].id == rejection_id_of(
        "snapshot-section", SECTION_ADDRESS
    )
    assert result.rejection_removals[0].machine_id == "machine-a"
    assert result.rejection_removals[0].scope == "network"
    assert result.rejection_removals[0].rejected_at == REJECTED_AT


def test_a_whole_file_withholding_is_reported_too(tmp_path):
    """Its recovery window never closes — apply never deletes, so this machine's
    copy of the file survives and stays a live source for `keep` — but the
    operator is still owed the news that the network retired it, exactly as they
    were told before consolidate started withholding upstream."""
    repo = _repo(tmp_path)
    _reject(repo, "snapshot-file", "rules/team.md")
    _consolidated_with_withholding(
        repo, [{"machine_id": "machine-b", "address": "rules/team.md"}]
    )
    context = _applying_machine(tmp_path, repo, "machine-b")
    (context.claude_dir / "rules").mkdir(parents=True, exist_ok=True)
    (context.claude_dir / "rules" / "team.md").write_text("held\n", encoding="utf-8")

    result = SnapshotPropagator(policy=_network_policy(repo, "machine-b")).apply(
        context
    )

    assert [record.address for record in result.rejection_removals] == ["rules/team.md"]
    # The asymmetry the prompt has to explain: nothing was deleted here.
    assert (context.claude_dir / "rules" / "team.md").exists()


def test_a_machine_that_never_held_the_content_is_not_told(tmp_path):
    """The other half of the attribution. Reporting to every machine would put a
    prompt in front of an operator with nothing to answer and nothing to lose."""
    repo = _repo(tmp_path)
    _reject(repo, "snapshot-section", SECTION_ADDRESS)
    _consolidated_with_withholding(
        repo, [{"machine_id": "machine-b", "address": SECTION_ADDRESS}]
    )
    context = _applying_machine(tmp_path, repo, "machine-c")

    result = SnapshotPropagator(policy=_network_policy(repo, "machine-c")).apply(
        context
    )

    assert result.rejection_removals == []


def test_the_machine_that_recorded_the_rejection_is_not_prompted_about_it(tmp_path):
    """A rejection withholds, it never deletes — so the rejecting machine is
    still holding the content it just rejected, and would otherwise be asked to
    reconsider its own decision on its very next apply."""
    repo = _repo(tmp_path)
    _reject(repo, "snapshot-section", SECTION_ADDRESS, rejecting_machine="machine-a")
    _consolidated_with_withholding(
        repo, [{"machine_id": "machine-a", "address": SECTION_ADDRESS}]
    )
    context = _applying_machine(tmp_path, repo, "machine-a")

    result = SnapshotPropagator(policy=_network_policy(repo, "machine-a")).apply(
        context
    )

    assert result.rejection_removals == []


def test_a_withholding_already_reported_by_the_local_filter_is_not_doubled(tmp_path):
    """The two report paths can name the same address: another machine's copy
    can survive consolidate with fresher provenance while this machine's is
    withheld, so the content is in `files` AND in `withheld`. One prompt, not
    two."""
    repo = _repo(tmp_path)
    _reject(repo, "snapshot-section", SECTION_ADDRESS)
    (repo / "consolidated" / "snapshot.json").write_text(
        json.dumps(
            {
                "timestamp": REJECTED_AT,
                "files": {"CLAUDE.md": DOCUMENT},
                "withheld": [{"machine_id": "machine-b", "address": SECTION_ADDRESS}],
            }
        ),
        encoding="utf-8",
    )
    context = _applying_machine(tmp_path, repo, "machine-b")

    result = SnapshotPropagator(policy=_network_policy(repo, "machine-b")).apply(
        context
    )

    assert [record.address for record in result.rejection_removals] == [SECTION_ADDRESS]


def test_a_consolidated_snapshot_without_the_key_still_applies(tmp_path):
    """A snapshot written by an engine older than this change. Provenance
    degrades: no report, no crash."""
    repo = _repo(tmp_path)
    (repo / "consolidated" / "snapshot.json").write_text(
        json.dumps({"timestamp": REJECTED_AT, "files": {"CLAUDE.md": DOCUMENT}}),
        encoding="utf-8",
    )
    context = _applying_machine(tmp_path, repo, "machine-b")

    result = SnapshotPropagator(policy=_network_policy(repo, "machine-b")).apply(
        context
    )

    assert result.rejection_removals == []
    assert (context.claude_dir / "CLAUDE.md").read_text(encoding="utf-8") == DOCUMENT


@pytest.mark.parametrize(
    "malformed",
    [
        "not a list",
        [None, 7, "CLAUDE.md"],
        [{"machine_id": "machine-b"}],
        [{"address": SECTION_ADDRESS}],
        [{"machine_id": "machine-b", "address": ["not", "a", "string"]}],
    ],
)
def test_a_malformed_withholding_report_degrades_rather_than_aborting(
    tmp_path, malformed
):
    """One machine writing a bad `withheld` key must not stop every other machine
    from applying its config. The rejection ledger fails closed; a *report* does
    not."""
    repo = _repo(tmp_path)
    _reject(repo, "snapshot-section", SECTION_ADDRESS)
    _consolidated_with_withholding(repo, malformed)
    context = _applying_machine(tmp_path, repo, "machine-b")

    result = SnapshotPropagator(policy=_network_policy(repo, "machine-b")).apply(
        context
    )

    assert result.rejection_removals == []
    assert result.applied == ["CLAUDE.md"]


# ---------------------------------------------------------------------------
# Layer 3 — the end-to-end walk: the escape hatch is alive again
# ---------------------------------------------------------------------------

ALPHA_AND_BETA = "## Alpha\nalpha body\n\n## Beta\nbeta body\n"
ALPHA_ONLY = "## Alpha\nalpha body\n"
BETA_ADDRESS = section_address("CLAUDE.md", "## Beta", 0)


def _live_machine(tmp_path, repo, machine_id, document):
    """A machine with a real ~/.claude of its own and a real CLAUDE.md on disk."""
    claude_dir = tmp_path / machine_id
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "config-sync-machine-id").write_text(machine_id, encoding="utf-8")
    (claude_dir / "CLAUDE.md").write_text(document, encoding="utf-8")
    return SyncContext(claude_dir=claude_dir, repo_dir=repo)


def _export(context):
    import config_sync_propagators as propagators_module

    propagators_module.SnapshotPropagator().export(context)


def _apply(context):
    """Apply through the real composition root, so the policy is the production
    composite rather than one this test picked."""
    import config_sync_propagators as propagators_module

    results = propagators_module.run_apply(
        context, propagators_module.apply_propagators(context)
    )
    return next(result for result in results if result.propagator == "snapshot")


def test_step_4e_can_still_keep_a_section_the_network_rejected(
    tmp_path, capsys, monkeypatch
):
    """THE WALK. Real export, real consolidate, real apply, real resolve-rejection.

    Without the withholding report, machine B's operator is never told that
    `## Beta` was taken away, answers nothing, re-exports its stripped disk, and
    the section is gone from every source the network has.
    """
    repo = _repo(tmp_path)
    machine_a = _live_machine(tmp_path, repo, "machine-a", ALPHA_ONLY)
    machine_b = _live_machine(tmp_path, repo, "machine-b", ALPHA_AND_BETA)

    # --- Round 1: the contested section is shared network-wide ---------------
    _export(machine_a)
    _export(machine_b)
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()
    _apply(machine_b)
    assert "## Beta" in _consolidated(repo)["files"]["CLAUDE.md"]

    # --- Machine A rejects it for the whole network --------------------------
    with monkeypatch.context() as as_machine_a:
        as_machine_a.setattr(config_sync, "CLAUDE_DIR", machine_a.claude_dir)
        config_sync.cmd_reject(
            str(repo), "snapshot-section", "CLAUDE.md", "--section", "## Beta"
        )
        rejection = json.loads(capsys.readouterr().out)
    assert rejection["scope"] == "network"

    # --- Round 2: the first sync after the rejection -------------------------
    # B re-exports unchanged, so per-content provenance reads it as no fresher
    # than the rejection and consolidate withholds it. B's disk is rewritten
    # without it, and `machines/machine-b.json` is now the last live source.
    _export(machine_b)
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()
    assert "## Beta" not in _consolidated(repo)["files"]["CLAUDE.md"]

    applied = _apply(machine_b)
    assert "## Beta" not in (machine_b.claude_dir / "CLAUDE.md").read_text(
        encoding="utf-8"
    )

    # --- Step 4e: B's operator is told, and can answer -----------------------
    reported = [
        record for record in applied.rejection_removals if record.scope == "network"
    ]
    assert [record.address for record in reported] == [BETA_ADDRESS]
    assert reported[0].id == rejection["id"]

    with monkeypatch.context() as as_machine_b:
        as_machine_b.setattr(config_sync, "CLAUDE_DIR", machine_b.claude_dir)
        config_sync.cmd_resolve_rejection(str(repo), reported[0].id, "keep")
        capsys.readouterr()

    # --- The answer takes effect at the next consolidate ---------------------
    # Before B's next export, which is the deadline: `keep` revives from
    # `machines/machine-b.json`, and B's next export would overwrite it with the
    # stripped disk.
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()
    assert "## Beta" in _consolidated(repo)["files"]["CLAUDE.md"]

    _apply(machine_b)
    assert "## Beta" in (machine_b.claude_dir / "CLAUDE.md").read_text(encoding="utf-8")

    # --- Round 3: and it survives the sync that used to destroy it -----------
    _export(machine_b)
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()
    assert "## Beta" in _consolidated(repo)["files"]["CLAUDE.md"]
    assert BETA_ADDRESS not in _consolidated(repo)["rejected"]
