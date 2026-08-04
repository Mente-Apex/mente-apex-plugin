"""Export records when each unit last changed, using its own previous snapshot."""

import contextlib
import json

from config_sync_propagators import SnapshotPropagator, SyncContext


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


def test_a_previous_snapshot_with_null_provenance_warns(tmp_path):
    """`null` is a VALUE, not an absent key -- export never writes it, so its
    presence is a defect (hand-edit or bug) and must warn like any other
    malformed map, not be treated as a first export."""
    context = _context(tmp_path)
    SnapshotPropagator().export(context)
    machine_file = list((context.repo_dir / "machines").glob("*.json"))[0]
    payload = json.loads(machine_file.read_text(encoding="utf-8"))
    payload["provenance"] = None
    machine_file.write_text(json.dumps(payload), encoding="utf-8")

    result = SnapshotPropagator().export(context)
    assert any("provenance" in warning for warning in result.warnings)


def test_a_previous_snapshot_that_is_not_a_json_object_warns(tmp_path):
    """A snapshot whose JSON top level is a list or a scalar is not a shape
    export ever writes, so it is a defect rather than an un-upgraded machine --
    and an unpinned warn path is how a warning silently disappears in a later
    refactor."""
    context = _context(tmp_path)
    SnapshotPropagator().export(context)
    machine_file = list((context.repo_dir / "machines").glob("*.json"))[0]
    machine_file.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    result = SnapshotPropagator().export(context)
    assert any("provenance" in warning for warning in result.warnings)


def test_a_previous_snapshot_that_is_not_a_json_object_restamps(tmp_path):
    """Degrades rather than aborting, like every other malformed shape here."""
    context = _context(tmp_path)
    SnapshotPropagator().export(context)
    machine_file = list((context.repo_dir / "machines").glob("*.json"))[0]
    machine_file.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    SnapshotPropagator().export(context)
    assert _exported(context)["provenance"]["snapshot-file"]["CLAUDE.md"]["changed_at"]


# ---------------------------------------------------------------------------
# The snapshot is written atomically: consolidate reads every machines/*.json
# with a bare json.loads, so a half-written one aborts the whole network.
# ---------------------------------------------------------------------------


def test_an_interrupted_export_leaves_the_previous_snapshot_intact(
    tmp_path, monkeypatch
):
    """A crash between writing the bytes and publishing them must not destroy
    the snapshot already on disk -- it is the last live source a
    `resolve-rejection ... keep` can revive from, and the file every other
    machine's consolidate parses."""
    import config_sync_propagators as propagators

    context = _context(tmp_path)
    SnapshotPropagator().export(context)
    machine_file = list((context.repo_dir / "machines").glob("*.json"))[0]
    before = machine_file.read_text(encoding="utf-8")

    def _explode(source, destination):
        raise OSError("interrupted")

    monkeypatch.setattr(propagators.os, "replace", _explode)
    (context.claude_dir / "CLAUDE.md").write_text("## Alpha\nNEW\n", encoding="utf-8")

    # Tolerated, not asserted: whether the interruption surfaces as an exception
    # is not the claim. The claim is that the published file survives it, which
    # is what fails against a straight `write_text` onto the live path.
    with contextlib.suppress(OSError):
        SnapshotPropagator().export(context)

    assert machine_file.read_text(encoding="utf-8") == before
    assert "NEW" not in machine_file.read_text(encoding="utf-8")


def test_the_snapshot_is_published_through_an_atomic_replace(tmp_path, monkeypatch):
    """Pins the mechanism, not just the outcome: a future rewrite that goes back
    to writing the live path directly has to fail here."""
    import config_sync_propagators as propagators

    replaced = []
    monkeypatch.setattr(
        propagators.os,
        "replace",
        lambda source, destination: replaced.append((str(source), str(destination))),
    )

    context = _context(tmp_path)
    SnapshotPropagator().export(context)

    assert len(replaced) == 1
    source, destination = replaced[0]
    assert source.endswith(".json.tmp")
    assert destination.endswith(".json")


def test_a_completed_export_leaves_no_temp_file_behind(tmp_path):
    context = _context(tmp_path)
    SnapshotPropagator().export(context)
    assert list((context.repo_dir / "machines").glob("*.tmp")) == []


def test_a_leftover_temp_file_is_not_mistaken_for_a_machine_snapshot(tmp_path, capsys):
    """The temp name ends in `.json.tmp`, not `.json`: a crash between write and
    replace must not leave a file `cmd_consolidate`'s `machines/*.json` glob
    folds in as if it were a real machine."""
    import config_sync

    context = _context(tmp_path)
    SnapshotPropagator().export(context)
    machines_dir = context.repo_dir / "machines"
    (machines_dir / "half-written.json.tmp").write_text("{truncated", encoding="utf-8")
    (context.repo_dir / "consolidated").mkdir(parents=True, exist_ok=True)

    config_sync.cmd_consolidate(str(context.repo_dir))
    capsys.readouterr()

    consolidated = json.loads(
        (context.repo_dir / "consolidated" / "snapshot.json").read_text(
            encoding="utf-8"
        )
    )
    assert "CLAUDE.md" in consolidated["files"]


def test_a_previous_snapshot_with_a_malformed_kind_section_warns(tmp_path):
    """Spec §9's export row. `provenance` itself is a dict, so the top-level
    guard does not fire, but nothing under `snapshot-file` is usable and every
    unit of that kind re-stamps as now.

    Export is the ONLY end that ever sees this: it consumes the previous
    snapshot and immediately overwrites `machines/<id>.json` with a freshly
    stamped, well-formed map, so the consolidate-side scan never meets the
    defect. Silence here means nobody is told at either end."""
    context = _context(tmp_path)
    SnapshotPropagator().export(context)
    machine_file = list((context.repo_dir / "machines").glob("*.json"))[0]
    payload = json.loads(machine_file.read_text(encoding="utf-8"))
    payload["provenance"] = {"snapshot-file": "not a dict"}
    machine_file.write_text(json.dumps(payload), encoding="utf-8")

    result = SnapshotPropagator().export(context)
    assert any("snapshot-file" in warning for warning in result.warnings)


def test_a_previous_entry_with_no_changed_at_warns(tmp_path):
    """The other half of §9's malformed row: the entry is a dict and its hash is
    intact, but `changed_at` is gone, so the unit cannot carry forward."""
    context = _context(tmp_path)
    SnapshotPropagator().export(context)
    machine_file = list((context.repo_dir / "machines").glob("*.json"))[0]
    payload = json.loads(machine_file.read_text(encoding="utf-8"))
    for entry in payload["provenance"]["snapshot-file"].values():
        entry.pop("changed_at")
    machine_file.write_text(json.dumps(payload), encoding="utf-8")

    result = SnapshotPropagator().export(context)
    assert any("changed_at" in warning for warning in result.warnings)


def test_a_partly_malformed_previous_map_is_still_used_for_its_intact_units(tmp_path):
    """Warning is additive, not a bail-out: only the defective units re-stamp.
    A section whose entry is untouched still carries its `changed_at` forward,
    so a warning does not itself become a resurrection."""
    context = _context(tmp_path)
    SnapshotPropagator().export(context)
    first = _exported(context)["provenance"]
    carried_section = next(iter(first["snapshot-section"]))
    original_changed_at = first["snapshot-section"][carried_section]["changed_at"]

    machine_file = list((context.repo_dir / "machines").glob("*.json"))[0]
    payload = json.loads(machine_file.read_text(encoding="utf-8"))
    payload["provenance"]["snapshot-file"] = "not a dict"
    machine_file.write_text(json.dumps(payload), encoding="utf-8")

    result = SnapshotPropagator().export(context)
    assert result.warnings
    after = _exported(context)["provenance"]
    assert after["snapshot-section"][carried_section]["changed_at"] == (
        original_changed_at
    )
