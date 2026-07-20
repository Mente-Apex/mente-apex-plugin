import json

import config_sync_hooks
import config_sync_roots


def test_named_roots_excludes_home_catch_all():
    registry = config_sync_roots.RootRegistry([
        config_sync_roots.Root("HOME", "/Users/ai"),
        config_sync_roots.Root("MENTE_APEX_MEMORY", "/Users/ai/Projects/mente-apex-memory"),
    ])
    named = registry.named_roots()
    assert [root.token for root in named] == ["MENTE_APEX_MEMORY"]


def test_resolve_command_maps_plugin_root_to_token():
    assert config_sync_hooks.resolve_command(
        "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/protect_brain.py", "MENTE_APEX_MEMORY"
    ) == "python3 ${MENTE_APEX_MEMORY}/hooks/protect_brain.py"


def test_hook_id_is_stable_12_hex_and_marker_round_trips():
    hook_id = config_sync_hooks.hook_id_of(
        "MENTE_APEX_MEMORY", "PreToolUse", "Write|Edit",
        "python3 ${MENTE_APEX_MEMORY}/hooks/protect_brain.py",
    )
    assert len(hook_id) == 12 and all(character in "0123456789abcdef" for character in hook_id)
    # same inputs -> same id
    assert hook_id == config_sync_hooks.hook_id_of(
        "MENTE_APEX_MEMORY", "PreToolUse", "Write|Edit",
        "python3 ${MENTE_APEX_MEMORY}/hooks/protect_brain.py",
    )
    marked = "python3 x.py " + config_sync_hooks.marker_for(hook_id)
    assert config_sync_hooks.registered_hook_ids(
        {"hooks": {"PreToolUse": [{"matcher": "Write|Edit",
                                   "hooks": [{"type": "command", "command": marked}]}]}}
    ) == {hook_id}


def _write_declaration(root_dir, block):
    hooks_dir = root_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    (hooks_dir / "hooks.json").write_text(json.dumps(block))


def test_discover_reads_declaration_and_resolves_token(tmp_path):
    repo = tmp_path / "mem"
    _write_declaration(repo, {"hooks": {"PreToolUse": [
        {"matcher": "Write|Edit", "hooks": [
            {"type": "command",
             "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/protect_brain.py",
             "timeout": 10}]}]}})
    registry = config_sync_roots.RootRegistry([
        config_sync_roots.Root("HOME", str(tmp_path)),
        config_sync_roots.Root("MEM", str(repo)),
    ])

    declarations = config_sync_hooks.discover_declarations(registry)

    assert len(declarations) == 1
    declaration = declarations[0]
    assert declaration.event == "PreToolUse"
    assert declaration.matcher == "Write|Edit"
    assert declaration.command == "python3 ${MEM}/hooks/protect_brain.py"
    assert declaration.timeout == 10
    assert declaration.hook_id == config_sync_hooks.hook_id_of(
        "MEM", "PreToolUse", "Write|Edit", declaration.command)


def test_discover_ignores_missing_and_malformed(tmp_path):
    repo_missing = tmp_path / "nohooks"
    repo_missing.mkdir()
    repo_bad = tmp_path / "bad"
    (repo_bad / "hooks").mkdir(parents=True)
    (repo_bad / "hooks" / "hooks.json").write_text("{ not json")
    registry = config_sync_roots.RootRegistry([
        config_sync_roots.Root("HOME", str(tmp_path)),
        config_sync_roots.Root("NOHOOKS", str(repo_missing)),
        config_sync_roots.Root("BAD", str(repo_bad)),
    ])
    assert config_sync_hooks.discover_declarations(registry) == []
