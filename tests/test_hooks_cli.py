import json
import os
from pathlib import Path

import pytest

import config_sync
import config_sync_hooks
import config_sync_roots


def test_engine_ignores_ambient_root_declarations(root_environ, monkeypatch):
    """Regression guard for the isolation fixture in conftest.

    Asserting that `os.environ` is clean would be the wrong guard: with the
    fixture deleted it passes in CI, where nothing is declared, and fails only
    on machines that really use the feature — exactly the backwards failure mode
    the fixture exists to remove. So declare a root in the *real* process
    environment and assert the engine does not see it.
    """
    monkeypatch.setenv(config_sync_roots.ROOT_ENV_PREFIX + "AMBIENT", "/tmp/ambient")
    assert config_sync_roots.ROOT_ENV_PREFIX + "AMBIENT" in os.environ

    tokens = [root.token for root in config_sync._root_registry().named_roots()]
    assert tokens == [], f"ambient declaration reached the engine: {tokens}"

    # The injected dict is the only channel a test declares roots through.
    root_environ[config_sync_roots.ROOT_ENV_PREFIX + "DECLARED"] = "/tmp/declared"
    assert [root.token for root in config_sync._root_registry().named_roots()] == [
        "DECLARED"
    ]


def _declare_memory_hook(tmp_path, root_environ, with_script=True):
    """A named-root repo shipping a hooks/hooks.json, declared via env var.

    The script itself exists by default, because a repo that declares a hook it
    does not ship is the exceptional case — and the wiring now declines to wire
    one, so a fixture that omitted it would silently test nothing.
    """
    repo = tmp_path / "mem"
    (repo / "hooks").mkdir(parents=True)
    if with_script:
        (repo / "hooks" / "protect_brain.py").write_text("")
    (repo / "hooks" / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Write|Edit",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/protect_brain.py",
                                    "timeout": 10,
                                }
                            ],
                        }
                    ]
                }
            }
        )
    )
    root_environ["CONFIG_SYNC_ROOT_MEM"] = str(repo)
    return repo


def test_hooks_plan_then_apply_is_idempotent(
    claude_home, tmp_path, root_environ, capsys
):
    _declare_memory_hook(tmp_path, root_environ)
    (claude_home / "settings.json").write_text('{"model":"opus"}')

    config_sync.cmd_hooks_plan()
    plan = json.loads(capsys.readouterr().out)
    assert len(plan["actions"]) == 1 and plan["actions"][0]["verb"] == "register"

    config_sync.cmd_hooks_apply()
    apply_output = json.loads(capsys.readouterr().out)
    assert (
        len(apply_output["outcomes"]) == 1 and apply_output["outcomes"][0]["ok"] is True
    )

    written = json.loads((claude_home / "settings.json").read_text())
    command = written["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert command.startswith(
        f"python3 {tmp_path / 'mem'}/hooks/protect_brain.py # config-sync:"
    )
    assert written["model"] == "opus"  # untouched

    # Second apply: no actions, settings unchanged.
    config_sync.cmd_hooks_apply()
    second = json.loads(capsys.readouterr().out)
    assert second["outcomes"] == []


def test_wired_hook_survives_export_import_portably(
    claude_home, tmp_path, root_environ, capsys
):
    _declare_memory_hook(tmp_path, root_environ)  # CONFIG_SYNC_ROOT_MEM -> tmp/mem
    (claude_home / "settings.json").write_text('{"model":"opus"}')
    config_sync.cmd_hooks_apply()
    capsys.readouterr()

    config_sync.cmd_export()
    snapshot = json.loads(capsys.readouterr().out)
    exported = json.loads(snapshot["files"]["settings.json"])
    exported_command = exported["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    # HOME (the claude_home tmp path) is tokenised; MEM stays a token too.
    assert "${MEM}/hooks/protect_brain.py" in exported_command
    assert "# config-sync:" in exported_command

    # Import the snapshot back; MEM still resolves via the same env var here.
    snap_file = tmp_path / "snap.json"
    snap_file.write_text(json.dumps(snapshot))
    config_sync.cmd_import(str(snap_file))
    capsys.readouterr()

    reimported = json.loads((claude_home / "settings.json").read_text())
    reimported_command = reimported["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert reimported_command.startswith(
        f"python3 {tmp_path / 'mem'}/hooks/protect_brain.py"
    )
    # Marker preserved -> a re-plan sees it as already registered (no double-wire).
    assert config_sync_hooks.registered_hook_ids(reimported)


def _settings_with(claude_home, *commands):
    (claude_home / "settings.json").write_text(
        json.dumps(
            {
                "model": "opus",
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Write|Edit",
                            "hooks": [{"type": "command", "command": command}],
                        }
                        for command in commands
                    ]
                },
            }
        )
    )


def test_hooks_doctor_reports_a_dead_target_and_leaves_settings_alone(
    claude_home, tmp_path, capsys
):
    live = tmp_path / "live.py"
    live.write_text("")
    _settings_with(
        claude_home,
        f"python3 {live}",
        f"python3 {tmp_path / 'gone.py'} # config-sync:0123456789ab",
    )
    before = (claude_home / "settings.json").read_text()

    config_sync.cmd_hooks_doctor()
    report = json.loads(capsys.readouterr().out)

    assert report["summary"]["total"] == 2
    assert report["summary"]["healthy"] == 1
    assert report["summary"]["repairable"] == 1
    (finding,) = report["findings"]
    assert finding["findings"] == ["missing-target"]
    assert finding["missing_targets"] == [str(tmp_path / "gone.py")]
    assert finding["managed"] is True
    assert (claude_home / "settings.json").read_text() == before  # read-only


def test_hooks_doctor_counts_shell_fragments_as_unchecked_not_broken(
    claude_home, capsys
):
    _settings_with(claude_home, '[ -n "$X" ] && printf y > /dev/tty || true')

    config_sync.cmd_hooks_doctor()
    report = json.loads(capsys.readouterr().out)

    assert report["summary"]["unchecked"] == 1
    assert report["summary"]["repairable"] == 0
    assert report["findings"] == []


def test_hooks_prune_removes_its_own_dead_hook_and_spares_the_hand_added_one(
    claude_home, tmp_path, capsys
):
    _settings_with(
        claude_home,
        f"python3 {tmp_path / 'gone_a.py'}",  # hand-added
        f"python3 {tmp_path / 'gone_b.py'} # config-sync:0123456789ab",
    )

    config_sync.cmd_hooks_prune()
    result = json.loads(capsys.readouterr().out)

    assert len(result["removed"]) == 1
    assert "gone_b.py" in result["removed"][0]["command"]
    assert any("not config-sync's" in reason for reason in result["skipped"])

    written = json.loads((claude_home / "settings.json").read_text())
    commands = [
        hook["command"]
        for group in written["hooks"]["PreToolUse"]
        for hook in group["hooks"]
    ]
    assert commands == [f"python3 {tmp_path / 'gone_a.py'}"]
    assert written["model"] == "opus"  # untouched


def test_hooks_prune_can_be_widened_to_hand_added_hooks(claude_home, tmp_path, capsys):
    _settings_with(claude_home, f"python3 {tmp_path / 'gone_a.py'}")

    config_sync.cmd_hooks_prune("--include-unmanaged")
    capsys.readouterr()

    written = json.loads((claude_home / "settings.json").read_text())
    assert "PreToolUse" not in written.get("hooks", {})


def test_hooks_prune_rejects_an_unknown_flag(claude_home, capsys):
    _settings_with(claude_home, "python3 /gone.py")
    with pytest.raises(SystemExit) as exit_info:
        config_sync.cmd_hooks_prune("--force")
    assert exit_info.value.code == 1
    assert "--force" in capsys.readouterr().err


def test_hooks_prune_writes_nothing_when_the_block_is_healthy(
    claude_home, tmp_path, capsys
):
    live = tmp_path / "live.py"
    live.write_text("")
    _settings_with(claude_home, f"python3 {live}")
    before = (claude_home / "settings.json").read_text()

    config_sync.cmd_hooks_prune()
    result = json.loads(capsys.readouterr().out)

    assert result["removed"] == []
    assert (claude_home / "settings.json").read_text() == before


def test_hooks_doctor_separates_what_prune_would_actually_remove(
    claude_home, tmp_path, capsys
):
    """`repairable` counts hand-added entries too, which the default run skips.
    Gating the consent prompt on it promised removals that never happened."""
    _settings_with(
        claude_home,
        f"python3 {tmp_path / 'gone_a.py'}",  # broken, hand-added
        f"python3 {tmp_path / 'gone_b.py'} # config-sync:0123456789ab",
    )

    config_sync.cmd_hooks_doctor()
    report = json.loads(capsys.readouterr().out)

    assert report["summary"]["repairable"] == 2
    assert report["summary"]["prunable_by_default"] == 1


def test_hooks_doctor_never_condemns_a_command_it_cannot_expand(claude_home, capsys):
    """`$CLAUDE_PROJECT_DIR/...` is the idiom Claude Code's own hook docs
    recommend, and `${CONFIG_SYNC_ROOT_*}/...` is a string config-sync writes
    itself when a token arrives from a machine whose root is undeclared here.
    Both read as missing before, and both were pruned."""
    _settings_with(
        claude_home,
        "$CLAUDE_PROJECT_DIR/.claude/hooks/check.sh",
        "${CONFIG_SYNC_ROOT_MEM}/hooks/protect_brain.py # config-sync:0123456789ab",
    )

    config_sync.cmd_hooks_doctor()
    report = json.loads(capsys.readouterr().out)

    assert report["summary"]["unchecked"] == 2
    assert report["summary"]["prunable_by_default"] == 0

    config_sync.cmd_hooks_prune()
    assert json.loads(capsys.readouterr().out)["removed"] == []


def test_hooks_prune_backs_up_settings_before_deleting(claude_home, tmp_path, capsys):
    _settings_with(
        claude_home, f"python3 {tmp_path / 'gone.py'} # config-sync:0123456789ab"
    )
    before = json.loads((claude_home / "settings.json").read_text())

    config_sync.cmd_hooks_prune()
    result = json.loads(capsys.readouterr().out)

    backup = result["backup"]
    assert backup is not None
    assert json.loads(Path(backup).read_text()) == before
    assert (
        "PreToolUse"
        not in json.loads((claude_home / "settings.json").read_text())["hooks"]
    )


def test_hooks_prune_writes_no_backup_when_it_removes_nothing(
    claude_home, tmp_path, capsys
):
    live = tmp_path / "live.py"
    live.write_text("")
    _settings_with(claude_home, f"python3 {live}")

    config_sync.cmd_hooks_prune()
    result = json.loads(capsys.readouterr().out)

    assert result["backup"] is None
    assert not list(claude_home.glob("settings.json.pre-prune-*"))


def test_a_relocated_declaration_updates_rather_than_duplicating(
    claude_home, tmp_path, root_environ, capsys
):
    """End-to-end for the reported bug: wire a hook, then have the repo change
    the interpreter in front of the same script. The registration must move, not
    multiply."""
    repo = _declare_memory_hook(tmp_path, root_environ)
    (claude_home / "settings.json").write_text('{"model":"opus"}')
    config_sync.cmd_hooks_apply()
    capsys.readouterr()

    (repo / "bin").mkdir()
    (repo / "bin" / "py").write_text("")  # the relocated interpreter must exist too
    (repo / "hooks" / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Write|Edit",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "sh ${CLAUDE_PLUGIN_ROOT}/bin/py "
                                    "${CLAUDE_PLUGIN_ROOT}/hooks/protect_brain.py",
                                    "timeout": 10,
                                }
                            ],
                        }
                    ]
                }
            }
        )
    )

    config_sync.cmd_hooks_plan()
    assert [
        action["verb"] for action in json.loads(capsys.readouterr().out)["actions"]
    ] == ["update"]

    config_sync.cmd_hooks_apply()
    capsys.readouterr()

    written = json.loads((claude_home / "settings.json").read_text())
    commands = [
        hook["command"]
        for group in written["hooks"]["PreToolUse"]
        for hook in group["hooks"]
    ]
    assert len(commands) == 1
    assert commands[0].startswith(f"sh {repo}/bin/py {repo}/hooks/protect_brain.py")

    # And it settles.
    config_sync.cmd_hooks_plan()
    assert json.loads(capsys.readouterr().out)["actions"] == []


def test_apply_then_prune_then_apply_leaves_a_dead_declaration_deleted(
    claude_home, tmp_path, root_environ, capsys
):
    """The flap: the repo declares a hook whose script does not exist. Apply
    used to wire it, prune deleted it as a dead target, and the next apply wired
    it straight back."""
    _declare_memory_hook(tmp_path, root_environ, with_script=False)
    (claude_home / "settings.json").write_text('{"model":"opus"}')
    assert not (tmp_path / "mem" / "hooks" / "protect_brain.py").exists()

    config_sync.cmd_hooks_apply()
    first = json.loads(capsys.readouterr().out)
    assert first["outcomes"] == []
    assert any("not on this machine" in reason for reason in first["skipped"])

    config_sync.cmd_hooks_prune()
    assert json.loads(capsys.readouterr().out)["removed"] == []

    config_sync.cmd_hooks_apply()
    assert json.loads(capsys.readouterr().out)["outcomes"] == []
    assert "hooks" not in json.loads((claude_home / "settings.json").read_text())


def test_the_declaration_is_wired_as_soon_as_its_script_appears(
    claude_home, tmp_path, root_environ, capsys
):
    """Refusing to wire is a pause, not a verdict — the next apply after the repo
    is properly checked out picks it up."""
    repo = _declare_memory_hook(tmp_path, root_environ, with_script=False)
    (claude_home / "settings.json").write_text('{"model":"opus"}')

    config_sync.cmd_hooks_apply()
    assert json.loads(capsys.readouterr().out)["outcomes"] == []

    (repo / "hooks" / "protect_brain.py").write_text("")

    config_sync.cmd_hooks_apply()
    result = json.loads(capsys.readouterr().out)

    assert [outcome["ok"] for outcome in result["outcomes"]] == [True]
