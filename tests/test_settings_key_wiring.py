"""Both settings filter points, and the scope boundary between them.

Consolidate writes SHARED state, so it must honour network rejections only.
Apply writes LOCAL files, so it honours both — a private veto that reached the
shared snapshot would impose one machine's taste on the network.
"""

import json

import config_sync
from config_sync_propagators import SnapshotPropagator, SyncContext
from config_sync_rejections import (
    CompositeRejectionPolicy,
    LocalRejectionStore,
    RejectionRecord,
    SharedRejectionStore,
    rejection_id_of,
    settings_key_address,
)

REJECTED_AT = "2026-08-03T09:00:00+00:00"
SETTINGS = {
    "permissions": {"defaultMode": "acceptEdits"},
    "model": "opus",
}
ADDRESS = settings_key_address(("permissions", "defaultMode"))


def _settings_blob(settings=None):
    return json.dumps(settings if settings is not None else SETTINGS)


def _record(scope, machine_id="machine-a"):
    return RejectionRecord(
        id=rejection_id_of("settings-key", ADDRESS),
        kind="settings-key",
        address=ADDRESS,
        scope=scope,
        rejected_at=REJECTED_AT,
        machine_id=machine_id,
    )


def _repo(tmp_path, consolidated_settings=None):
    repo = tmp_path / "repo"
    (repo / "machines").mkdir(parents=True)
    (repo / "consolidated").mkdir(parents=True)
    (repo / "machines" / "machine-a.json").write_text(
        json.dumps(
            {
                "machine_id": "machine-a",
                "timestamp": "2026-08-03T08:00:00+00:00",
                "files": {"settings.json": _settings_blob(consolidated_settings)},
            }
        ),
        encoding="utf-8",
    )
    (repo / "consolidated" / "snapshot.json").write_text(
        json.dumps({"files": {"settings.json": _settings_blob(consolidated_settings)}}),
        encoding="utf-8",
    )
    return repo


def _consolidated_settings(repo):
    payload = json.loads(
        (repo / "consolidated" / "snapshot.json").read_text(encoding="utf-8")
    )
    return json.loads(payload["files"]["settings.json"])


def test_a_network_rejected_key_is_stripped_from_the_consolidated_snapshot(
    tmp_path, capsys
):
    repo = _repo(tmp_path)
    SharedRejectionStore(repo, "machine-a").record(_record("network"))

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert "defaultMode" not in _consolidated_settings(repo)["permissions"]
    assert _consolidated_settings(repo)["model"] == "opus"


def test_a_local_rejected_key_does_not_touch_shared_state(tmp_path, capsys):
    repo = _repo(tmp_path)
    SharedRejectionStore(repo, "machine-a").record(_record("local"))

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert _consolidated_settings(repo)["permissions"]["defaultMode"] == "acceptEdits"


def test_the_stripped_address_is_reported_in_the_rejected_audit_trail(tmp_path, capsys):
    repo = _repo(tmp_path)
    SharedRejectionStore(repo, "machine-a").record(_record("network"))

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    payload = json.loads(
        (repo / "consolidated" / "snapshot.json").read_text(encoding="utf-8")
    )
    assert ADDRESS in payload["rejected"]


def _apply_context(tmp_path):
    context = SyncContext(claude_dir=tmp_path / "claude", repo_dir=tmp_path / "repo")
    (context.repo_dir / "consolidated").mkdir(parents=True)
    (context.repo_dir / "consolidated" / "snapshot.json").write_text(
        json.dumps(
            {
                "timestamp": "2026-08-03T12:00:00+00:00",
                "files": {"settings.json": _settings_blob()},
            }
        ),
        encoding="utf-8",
    )
    context.claude_dir.mkdir(parents=True, exist_ok=True)
    return context


def test_a_locally_rejected_key_is_never_written_at_apply(tmp_path):
    context = _apply_context(tmp_path)
    store = LocalRejectionStore(tmp_path / "local.json")
    store.record(_record("local"))

    result = SnapshotPropagator(policy=CompositeRejectionPolicy([store])).apply(context)

    written = json.loads(
        (context.claude_dir / "settings.json").read_text(encoding="utf-8")
    )
    assert "defaultMode" not in written.get("permissions", {})
    # `rejection_removals` carries RejectionRecord objects, not dicts — phase 1's
    # final review widened it from bare address strings so Step 4e could render
    # the machine and time and call `resolve-rejection <id>`. Only
    # `cmd_propagate_apply` serialises them, via `vars()`.
    assert ADDRESS in [removal.address for removal in result.rejection_removals]


def test_without_a_policy_apply_writes_settings_unchanged(tmp_path):
    context = _apply_context(tmp_path)
    SnapshotPropagator().apply(context)
    written = json.loads(
        (context.claude_dir / "settings.json").read_text(encoding="utf-8")
    )
    assert written["permissions"]["defaultMode"] == "acceptEdits"
