"""One walk per new kind, across every module boundary.

Production-shaped on purpose: the consolidated snapshot carries a `timestamp`
that is STRICTLY NEWER than the rejection, because `cmd_consolidate` regenerates
it on every run. A filter that passed that timestamp as `source_timestamp` would
never suppress anything — which is exactly the defect that survived nine
unit-level suites in phase 1.
"""

import json

import pytest

import config_sync
from config_sync_hooks import HookSite
from config_sync_rejection_hooks import HookRegistrationAddressor

REJECTED_AT = "2026-08-03T09:00:00+00:00"
CONSOLIDATED_AT = "2026-08-03T12:00:00+00:00"

SETTINGS = {
    "permissions": {"defaultMode": "acceptEdits"},
    "enabledPlugins": {"open-memory@open-memory": True},
    "model": "opus",
}


@pytest.fixture(autouse=True)
def _isolated_claude_home(claude_home):
    return claude_home


def _repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "machines").mkdir(parents=True)
    (repo / "consolidated").mkdir(parents=True)
    (repo / "machines" / "machine-a.json").write_text(
        json.dumps(
            {
                "machine_id": "machine-a",
                "timestamp": "2026-08-03T08:00:00+00:00",
                "files": {"settings.json": json.dumps(SETTINGS)},
            }
        ),
        encoding="utf-8",
    )
    (repo / "consolidated" / "snapshot.json").write_text(
        json.dumps(
            {
                "timestamp": CONSOLIDATED_AT,
                "files": {"settings.json": json.dumps(SETTINGS)},
            }
        ),
        encoding="utf-8",
    )
    return repo


def _consolidated(repo):
    return json.loads(
        (repo / "consolidated" / "snapshot.json").read_text(encoding="utf-8")
    )


def _settings_in(repo):
    return json.loads(_consolidated(repo)["files"]["settings.json"])


def test_a_settings_key_walks_from_reject_to_a_stripped_consolidated_snapshot(
    tmp_path, capsys
):
    repo = _repo(tmp_path)

    # Hop 1 — the operator rejects it network-wide.
    config_sync.cmd_reject(
        str(repo),
        "settings-key",
        "-",
        "--key",
        "permissions",
        "--key",
        "defaultMode",
        "--scope",
        "network",
    )
    recorded = json.loads(capsys.readouterr().out)
    assert recorded["scope"] == "network"

    # Hop 2 — the record landed in the SHARED repo, not the local ledger.
    assert list((repo / "rejections").glob("*.json"))

    # Hop 3 — consolidate strips it, and says so in the audit trail.
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()
    assert "defaultMode" not in _settings_in(repo)["permissions"]
    assert recorded["address"] in _consolidated(repo)["rejected"]

    # Hop 4 — the precondition that makes hop 3 meaningful: the snapshot's own
    # timestamp is NEWER than the rejection, so a generation-time comparison
    # would have let the key through.
    assert _consolidated(repo)["timestamp"] > REJECTED_AT

    # Hop 5 — its siblings survived.
    assert _settings_in(repo)["model"] == "opus"

    # Hop 6 — unreject puts it back on the next consolidate.
    config_sync.cmd_unreject(str(repo), recorded["id"])
    capsys.readouterr()
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()
    assert _settings_in(repo)["permissions"]["defaultMode"] == "acceptEdits"


def test_a_plugin_rejection_is_visible_to_rejections_and_reversible(tmp_path, capsys):
    repo = _repo(tmp_path)

    config_sync.cmd_reject(str(repo), "plugin", "open-memory@open-memory")
    recorded = json.loads(capsys.readouterr().out)

    config_sync.cmd_rejections(str(repo))
    listed = json.loads(capsys.readouterr().out)["rejections"]
    assert [entry["address"] for entry in listed] == ["open-memory@open-memory"]
    assert [entry["kind"] for entry in listed] == ["plugin"]

    config_sync.cmd_unreject(str(repo), recorded["id"])
    capsys.readouterr()
    config_sync.cmd_rejections(str(repo))
    assert json.loads(capsys.readouterr().out)["rejections"] == []


def test_a_hook_rejection_records_its_tier_and_survives_an_interpreter_change(
    tmp_path, capsys, claude_home
):
    repo = _repo(tmp_path)
    (claude_home / "settings.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python3 /abs/scripts/enforce_gates.py",
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    config_sync.cmd_reject(
        str(repo),
        "hook-registration",
        "enforce_gates.py",
        "--event",
        "PreToolUse",
        "--matcher",
        "Bash",
    )
    recorded = json.loads(capsys.readouterr().out)
    assert recorded["tier"] == "2"

    # The whole reason tier 2 exists: the same registration, reinstalled under a
    # different interpreter and a different directory, is still the same hook.
    reinstalled = HookSite(
        event="PreToolUse",
        group_index=0,
        hook_index=0,
        matcher="Bash",
        command="/new/uv/bin/python /somewhere/else/enforce_gates.py",
    )
    assert HookRegistrationAddressor().matches(
        recorded["address"], int(recorded["tier"]), reinstalled
    )
