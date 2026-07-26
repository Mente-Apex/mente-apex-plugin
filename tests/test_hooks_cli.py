import json

import config_sync
import config_sync_hooks


def _declare_memory_hook(tmp_path, monkeypatch):
    """A named-root repo shipping a hooks/hooks.json, declared via env var."""
    repo = tmp_path / "mem"
    (repo / "hooks").mkdir(parents=True)
    (repo / "hooks" / "hooks.json").write_text(json.dumps({"hooks": {"PreToolUse": [
        {"matcher": "Write|Edit", "hooks": [
            {"type": "command",
             "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/protect_brain.py",
             "timeout": 10}]}]}}))
    monkeypatch.setenv("CONFIG_SYNC_ROOT_MEM", str(repo))
    return repo


def test_hooks_plan_then_apply_is_idempotent(claude_home, tmp_path, monkeypatch, capsys):
    _declare_memory_hook(tmp_path, monkeypatch)
    (claude_home / "settings.json").write_text('{"model":"opus"}')

    config_sync.cmd_hooks_plan()
    plan = json.loads(capsys.readouterr().out)
    assert len(plan["actions"]) == 1 and plan["actions"][0]["verb"] == "register"

    config_sync.cmd_hooks_apply()
    apply_output = json.loads(capsys.readouterr().out)
    assert len(apply_output["outcomes"]) == 1 and apply_output["outcomes"][0]["ok"] is True

    written = json.loads((claude_home / "settings.json").read_text())
    command = written["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert command.startswith(f"python3 {tmp_path / 'mem'}/hooks/protect_brain.py # config-sync:")
    assert written["model"] == "opus"   # untouched

    # Second apply: no actions, settings unchanged.
    config_sync.cmd_hooks_apply()
    second = json.loads(capsys.readouterr().out)
    assert second["outcomes"] == []


def test_wired_hook_survives_export_import_portably(claude_home, tmp_path, monkeypatch, capsys):
    _declare_memory_hook(tmp_path, monkeypatch)   # CONFIG_SYNC_ROOT_MEM -> tmp/mem
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
    assert reimported_command.startswith(f"python3 {tmp_path / 'mem'}/hooks/protect_brain.py")
    # Marker preserved -> a re-plan sees it as already registered (no double-wire).
    assert config_sync_hooks.registered_hook_ids(reimported)
