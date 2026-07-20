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
