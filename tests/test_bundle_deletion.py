import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import config_sync_propagators as propagators  # noqa: E402


def test_previously_exported_is_empty_without_index(tmp_path):
    ledger = propagators.BundleDeletionLedger()
    assert ledger.previously_exported(tmp_path, "machine-a") == set()


def test_record_export_round_trips(tmp_path):
    ledger = propagators.BundleDeletionLedger()
    ledger.record_export(tmp_path, "machine-a", {"skill/foo", "agent/bar"})
    assert ledger.previously_exported(tmp_path, "machine-a") == {
        "skill/foo",
        "agent/bar",
    }


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
    assert (
        ledger.is_deleted(tmp_path, "skill", "gof", "2026-07-08T11:00:00+00:00") is True
    )
    # bundle re-exported after the tombstone -> not deleted
    assert (
        ledger.is_deleted(tmp_path, "skill", "gof", "2026-07-08T13:00:00+00:00")
        is False
    )
    # equal timestamps -> not deleted (strict >)
    assert (
        ledger.is_deleted(tmp_path, "skill", "gof", "2026-07-08T12:00:00+00:00")
        is False
    )
    # missing bundle export ("") -> tombstone wins
    assert ledger.is_deleted(tmp_path, "skill", "gof", "") is True
    # no tombstone -> not deleted
    assert ledger.is_deleted(tmp_path, "agent", "none", "") is False


def test_tombstone_rejects_name_with_separator(tmp_path):
    import pytest

    ledger = propagators.BundleDeletionLedger()
    with pytest.raises(ValueError):
        ledger.tombstone(
            tmp_path, "skill", "a/b", "machine-a", "2026-07-08T00:00:00+00:00"
        )


def _write_skill(claude_dir, name, files):
    skill_dir = claude_dir / "skills" / name
    for relative_path, content in files.items():
        target = skill_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return skill_dir


def _write_agent_file(claude_dir, name, text):
    agents_dir = claude_dir / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    agent_path = agents_dir / name
    agent_path.write_text(text)
    return agent_path


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
    assert not (
        context.repo_dir / "bundles" / "skills" / "gof"
    ).exists()  # bundle pruned
    assert (
        propagators.BundleDeletionLedger().tombstone_for(
            context.repo_dir, "skill", "gof"
        )
        is not None
    )


def test_export_reexport_supersedes_tombstone(tmp_path):
    context = _context(tmp_path)
    ledger = propagators.BundleDeletionLedger()
    ledger.tombstone(
        context.repo_dir, "skill", "gof", "machine-b", "2000-01-01T00:00:00+00:00"
    )
    _write_skill(context.claude_dir, "gof", {"SKILL.md": "# gof back"})

    propagators.ContentBundlePropagator().export(context)

    assert (
        ledger.tombstone_for(context.repo_dir, "skill", "gof") is None
    )  # re-add cleared it
    assert (context.repo_dir / "bundles" / "skills" / "gof").exists()


def test_first_export_tombstones_nothing(tmp_path):
    context = _context(tmp_path)
    _write_skill(context.claude_dir, "keep", {"SKILL.md": "# keep"})
    result = propagators.ContentBundlePropagator().export(context)
    assert result.tombstoned == []


def test_apply_does_not_resurrect_a_tombstoned_bundle(tmp_path):
    context = _context(tmp_path)
    # A repo bundle exists but a newer tombstone retires it; skill is absent locally.
    bundle_dir = context.repo_dir / "bundles" / "skills" / "gof"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "SKILL.md").write_text("# gof")
    (bundle_dir / propagators.MANIFEST_NAME).write_text(
        '{"name":"gof","kind":"skill","is_dir":true,"content_hash":"x","exported_at":"2000-01-01T00:00:00+00:00"}'
    )
    propagators.BundleDeletionLedger().tombstone(
        context.repo_dir, "skill", "gof", "machine-b", "2026-07-08T00:00:00+00:00"
    )

    result = propagators.ContentBundlePropagator().apply(context)

    assert not (context.claude_dir / "skills" / "gof").exists()  # not resurrected
    assert "skill/gof" not in result.applied


def test_apply_proposes_deletion_for_locally_present_tombstoned_skill(tmp_path):
    context = _context(tmp_path)
    _write_skill(
        context.claude_dir, "gof", {"SKILL.md": "# gof"}
    )  # still present locally
    propagators.BundleDeletionLedger().tombstone(
        context.repo_dir, "skill", "gof", "machine-b", "2026-07-08T00:00:00+00:00"
    )

    result = propagators.ContentBundlePropagator().apply(context)

    assert [
        (deletion.kind, deletion.name, deletion.machine_id)
        for deletion in result.deletions
    ] == [("skill", "gof", "machine-b")]
    assert (context.claude_dir / "skills" / "gof").exists()  # apply removed nothing


def test_resolve_deletion_remove_deletes_local_bundle(tmp_path):
    context = _context(tmp_path)
    _write_skill(context.claude_dir, "gof", {"SKILL.md": "# gof"})
    propagators.resolve_deletion(context, "skill", "gof", "remove")
    assert not (context.claude_dir / "skills" / "gof").exists()


def test_resolve_deletion_keep_leaves_local_bundle(tmp_path):
    context = _context(tmp_path)
    _write_skill(context.claude_dir, "gof", {"SKILL.md": "# gof"})
    propagators.resolve_deletion(context, "skill", "gof", "keep")
    assert (context.claude_dir / "skills" / "gof").exists()


def test_resolve_deletion_rejects_unknown_decision(tmp_path):
    import pytest

    context = _context(tmp_path)
    with pytest.raises(ValueError):
        propagators.resolve_deletion(context, "skill", "gof", "maybe")


def test_resolve_deletion_remove_deletes_a_file_agent(tmp_path):
    context = _context(tmp_path)
    _write_agent_file(context.claude_dir, "reviewer.md", "# reviewer")
    propagators.resolve_deletion(context, "agent", "reviewer.md", "remove")
    assert not (context.claude_dir / "agents" / "reviewer.md").exists()


def test_agent_file_round_trip(tmp_path):
    repo_dir = tmp_path / "repo"
    machine_a = tmp_path / "a"
    machine_b = tmp_path / "b"
    for home, machine_id in [(machine_a, "machine-a"), (machine_b, "machine-b")]:
        home.mkdir(parents=True)
        (home / "config-sync-machine-id").write_text(machine_id)
    context_a = propagators.SyncContext(claude_dir=machine_a, repo_dir=repo_dir)
    context_b = propagators.SyncContext(claude_dir=machine_b, repo_dir=repo_dir)
    bundle_propagator = propagators.ContentBundlePropagator()

    _write_agent_file(machine_a, "reviewer.md", "# reviewer")
    bundle_propagator.export(context_a)
    bundle_propagator.apply(context_b)
    assert (machine_b / "agents" / "reviewer.md").is_file()  # installed as a file

    (machine_a / "agents" / "reviewer.md").unlink()  # delete the agent locally
    export_result = bundle_propagator.export(context_a)
    assert "agent/reviewer.md" in export_result.tombstoned

    apply_result = bundle_propagator.apply(context_b)
    assert [deletion.name for deletion in apply_result.deletions] == ["reviewer.md"]
    assert (machine_b / "agents" / "reviewer.md").exists()  # not removed until consent
    propagators.resolve_deletion(context_b, "agent", "reviewer.md", "remove")
    assert not (machine_b / "agents" / "reviewer.md").exists()


def test_apply_suppresses_conflict_when_newer_tombstone_exists(tmp_path):
    context = _context(tmp_path)
    # A repo bundle exported in the past, whose local copy differs (would be a conflict)...
    bundle_dir = context.repo_dir / "bundles" / "skills" / "gof"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "SKILL.md").write_text("# gof repo version")
    (bundle_dir / propagators.MANIFEST_NAME).write_text(
        '{"name":"gof","kind":"skill","is_dir":true,"content_hash":"repohash",'
        '"exported_at":"2000-01-01T00:00:00+00:00"}'
    )
    _write_skill(context.claude_dir, "gof", {"SKILL.md": "# gof local DIFFERENT"})
    # ...but a newer tombstone retires it.
    propagators.BundleDeletionLedger().tombstone(
        context.repo_dir, "skill", "gof", "machine-b", "2026-07-08T00:00:00+00:00"
    )

    result = propagators.ContentBundlePropagator().apply(context)

    assert result.conflicts == []  # conflict suppressed
    assert "skill/gof (tombstoned)" in result.skipped
    assert [deletion.name for deletion in result.deletions] == [
        "gof"
    ]  # proposed as a deletion instead


def test_two_machine_round_trip(tmp_path):
    # Shared repo; machine A deletes a skill, machine B applies + consents to remove.
    repo_dir = tmp_path / "repo"
    machine_a = tmp_path / "a"
    machine_b = tmp_path / "b"
    for home, machine_id in [(machine_a, "machine-a"), (machine_b, "machine-b")]:
        home.mkdir(parents=True)
        (home / "config-sync-machine-id").write_text(machine_id)

    context_a = propagators.SyncContext(claude_dir=machine_a, repo_dir=repo_dir)
    context_b = propagators.SyncContext(claude_dir=machine_b, repo_dir=repo_dir)
    bundle_propagator = propagators.ContentBundlePropagator()

    # A creates gof and exports; B applies (installs gof).
    _write_skill(machine_a, "gof", {"SKILL.md": "# gof"})
    bundle_propagator.export(context_a)
    bundle_propagator.apply(context_b)
    assert (machine_b / "skills" / "gof").exists()

    # A deletes gof and re-exports -> tombstone + prune.
    import shutil

    shutil.rmtree(machine_a / "skills" / "gof")
    export_result = bundle_propagator.export(context_a)
    assert "skill/gof" in export_result.tombstoned

    # B applies -> proposes the deletion (does not remove); consent removes it.
    apply_result = bundle_propagator.apply(context_b)
    assert [deletion.name for deletion in apply_result.deletions] == ["gof"]
    assert (machine_b / "skills" / "gof").exists()  # still there until consent
    propagators.resolve_deletion(context_b, "skill", "gof", "remove")
    assert not (machine_b / "skills" / "gof").exists()  # gone after consent
