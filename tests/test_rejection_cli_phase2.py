"""Rejecting a settings key, a plugin, and one hook registration from the CLI."""

import json

import pytest

import config_sync


@pytest.fixture(autouse=True)
def _isolated_claude_home(claude_home):
    """Never let a test read or write the operator's real ~/.claude.

    `config_sync.CLAUDE_DIR` is a module-level global computed at import time, so
    monkeypatching `pathlib.Path.home` does not reach it — this fixture does.
    """
    return claude_home


SETTINGS = {
    "permissions": {"defaultMode": "acceptEdits"},
    "enabledPlugins": {"open-memory@open-memory": True},
    "model": "opus",
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
    },
}

TWIN_SETTINGS = {
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": "python3 /one/place/enforce_gates.py",
                    },
                    {
                        "type": "command",
                        "command": "python3 /other/place/enforce_gates.py",
                    },
                ],
            }
        ]
    }
}


def _repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "consolidated").mkdir(parents=True)
    (repo / "consolidated" / "snapshot.json").write_text(
        json.dumps({"files": {"settings.json": json.dumps(SETTINGS)}}),
        encoding="utf-8",
    )
    return repo


def _live_settings(claude_home):
    (claude_home / "settings.json").write_text(json.dumps(SETTINGS), encoding="utf-8")


def test_rejecting_a_settings_key_records_the_key_path(tmp_path, capsys):
    repo = _repo(tmp_path)
    config_sync.cmd_reject(
        str(repo), "settings-key", "-", "--key", "permissions", "--key", "defaultMode"
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "settings-key"
    assert json.loads(payload["address"]) == ["permissions", "defaultMode"]


def test_a_settings_key_that_is_absent_is_refused(tmp_path):
    repo = _repo(tmp_path)
    with pytest.raises(config_sync.UnknownRejectionTargetError):
        config_sync.cmd_reject(str(repo), "settings-key", "-", "--key", "notThere")


def test_rejecting_a_plugin_records_its_id(tmp_path, capsys):
    repo = _repo(tmp_path)
    config_sync.cmd_reject(str(repo), "plugin", "open-memory@open-memory")
    assert json.loads(capsys.readouterr().out)["address"] == "open-memory@open-memory"


def test_a_plugin_that_is_not_enabled_anywhere_is_refused(tmp_path):
    repo = _repo(tmp_path)
    with pytest.raises(config_sync.UnknownRejectionTargetError):
        config_sync.cmd_reject(str(repo), "plugin", "never-heard-of@it")


def test_rejecting_a_hook_records_its_address_and_tier(tmp_path, capsys, claude_home):
    repo = _repo(tmp_path)
    _live_settings(claude_home)
    config_sync.cmd_reject(
        str(repo),
        "hook-registration",
        "enforce_gates.py",
        "--event",
        "PreToolUse",
        "--matcher",
        "Bash",
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["address"] == "hooks/PreToolUse/Bash/enforce_gates.py"
    assert payload["tier"] == "2"


def test_a_hook_matching_nothing_is_refused(tmp_path, claude_home):
    repo = _repo(tmp_path)
    _live_settings(claude_home)
    with pytest.raises(config_sync.UnknownRejectionTargetError):
        config_sync.cmd_reject(
            str(repo),
            "hook-registration",
            "nope.py",
            "--event",
            "PreToolUse",
            "--matcher",
            "Bash",
        )


def test_a_hook_rejection_without_an_event_is_refused(tmp_path, claude_home):
    repo = _repo(tmp_path)
    _live_settings(claude_home)
    with pytest.raises(ValueError):
        config_sync.cmd_reject(str(repo), "hook-registration", "enforce_gates.py")


def test_the_new_options_are_in_the_known_vocabulary(tmp_path):
    """Phase 1 made an unrecognised flag fail closed — these must be recognised."""
    repo = _repo(tmp_path)
    config_sync.cmd_reject(str(repo), "settings-key", "-", "--key", "model")


def test_a_mistyped_new_option_is_still_refused(tmp_path):
    repo = _repo(tmp_path)
    with pytest.raises(ValueError):
        config_sync.cmd_reject(str(repo), "settings-key", "-", "--kye", "model")


def test_a_script_name_matching_two_registrations_is_refused(tmp_path, claude_home):
    """Never guess between two matches — the rule `registrations_by_script` states
    outright. Both are addressable at tier 3, but the CLI cannot know which copy
    the operator meant, and rejecting the wrong one silently is worse."""
    repo = _repo(tmp_path)
    (claude_home / "settings.json").write_text(
        json.dumps(TWIN_SETTINGS), encoding="utf-8"
    )
    with pytest.raises(config_sync.UnknownRejectionTargetError) as refusal:
        config_sync.cmd_reject(
            str(repo),
            "hook-registration",
            "enforce_gates.py",
            "--event",
            "PreToolUse",
            "--matcher",
            "Bash",
        )
    assert "hooks-doctor" in str(refusal.value)


def test_an_exact_hash_subject_addresses_one_of_two_twins(
    tmp_path, capsys, claude_home
):
    """The discriminator the refusal points at: take the `#<hash>` suffix and use
    it as the subject. Resolution then lands on tier 3, as it must."""
    from config_sync_hooks import hook_sites
    from config_sync_rejection_hooks import HOOK_TIER_EXACT, hook_address_at_tier

    repo = _repo(tmp_path)
    (claude_home / "settings.json").write_text(
        json.dumps(TWIN_SETTINGS), encoding="utf-8"
    )
    first_site = hook_sites(TWIN_SETTINGS)[0]
    suffix = hook_address_at_tier(first_site, HOOK_TIER_EXACT).rsplit("/", 1)[1]

    config_sync.cmd_reject(
        str(repo),
        "hook-registration",
        suffix,
        "--event",
        "PreToolUse",
        "--matcher",
        "Bash",
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["tier"] == "3"
    assert payload["address"].endswith(suffix)


def test_rejecting_a_whole_synced_config_file_is_refused(tmp_path):
    """settings.json, CLAUDE.md and keybindings.json are the files the whole sync
    exists to carry — rejecting one wholesale is almost never what was meant."""
    repo = tmp_path / "repo3"
    (repo / "consolidated").mkdir(parents=True)
    (repo / "consolidated" / "snapshot.json").write_text(
        json.dumps({"files": {"settings.json": json.dumps(SETTINGS)}}), encoding="utf-8"
    )
    with pytest.raises(config_sync.MassRejectionRefusedError):
        config_sync.cmd_reject(str(repo), "snapshot-file", "settings.json")


def test_force_overrides_the_synced_config_file_guard(tmp_path, capsys):
    repo = tmp_path / "repo4"
    (repo / "consolidated").mkdir(parents=True)
    (repo / "consolidated" / "snapshot.json").write_text(
        json.dumps({"files": {"settings.json": json.dumps(SETTINGS)}}), encoding="utf-8"
    )
    config_sync.cmd_reject(str(repo), "snapshot-file", "settings.json", "--force")
    assert json.loads(capsys.readouterr().out)["address"] == "settings.json"


def test_rejecting_an_ordinary_file_is_not_guarded(tmp_path, capsys):
    repo = tmp_path / "repo5"
    (repo / "consolidated").mkdir(parents=True)
    (repo / "consolidated" / "snapshot.json").write_text(
        json.dumps({"files": {"rules/a.md": "hi"}}), encoding="utf-8"
    )
    config_sync.cmd_reject(str(repo), "snapshot-file", "rules/a.md")
    assert json.loads(capsys.readouterr().out)["address"] == "rules/a.md"
