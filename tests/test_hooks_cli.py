import json
import os

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


def _declare_memory_hook(tmp_path, root_environ):
    """A named-root repo shipping a hooks/hooks.json, declared via env var."""
    repo = tmp_path / "mem"
    (repo / "hooks").mkdir(parents=True)
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
