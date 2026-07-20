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


def _declaration(command="python3 ${MEM}/hooks/protect_brain.py"):
    hook_id = config_sync_hooks.hook_id_of("MEM", "PreToolUse", "Write|Edit", command)
    return config_sync_hooks.DeclaredHook(hook_id, "PreToolUse", "Write|Edit", command, 10)


def test_plan_registers_missing_hook():
    declaration = _declaration()
    plan = config_sync_hooks.plan_hook_wiring([declaration], {"hooks": {}})
    assert len(plan.actions) == 1
    action = plan.actions[0]
    assert action.verb == "register"
    assert action.hook_id == declaration.hook_id
    assert action.detail["command"] == declaration.command
    assert action.detail["event"] == "PreToolUse"


def test_plan_is_empty_when_already_registered():
    declaration = _declaration()
    marked = declaration.command + " " + config_sync_hooks.marker_for(declaration.hook_id)
    settings = {"hooks": {"PreToolUse": [
        {"matcher": "Write|Edit", "hooks": [{"type": "command", "command": marked}]}]}}
    plan = config_sync_hooks.plan_hook_wiring([declaration], settings)
    assert plan.actions == []


def test_plan_ignores_unmarked_hand_added_hook_for_same_script():
    declaration = _declaration()
    # Same script path, but NO marker -> config-sync must not consider it its own.
    settings = {"hooks": {"PreToolUse": [
        {"matcher": "Write|Edit",
         "hooks": [{"type": "command", "command": declaration.command}]}]}}
    plan = config_sync_hooks.plan_hook_wiring([declaration], settings)
    assert len(plan.actions) == 1   # still proposes its own marked registration


class FakeSettingsHost:
    def __init__(self, settings=None):
        self.settings = settings if settings is not None else {}
        self.writes = 0

    def read_settings(self):
        import copy
        return copy.deepcopy(self.settings)

    def write_settings(self, settings):
        self.settings = settings
        self.writes += 1


def test_execute_writes_marked_registration_and_is_idempotent():
    declaration = _declaration()
    host = FakeSettingsHost({"hooks": {}})

    plan = config_sync_hooks.plan_hook_wiring([declaration], host.read_settings())
    result = config_sync_hooks.execute_hook_plan(plan, host)

    assert [outcome.ok for outcome in result.outcomes] == [True]
    groups = host.settings["hooks"]["PreToolUse"]
    command = groups[0]["hooks"][0]["command"]
    assert command == declaration.command + " " + config_sync_hooks.marker_for(declaration.hook_id)
    assert groups[0]["hooks"][0]["timeout"] == 10
    assert host.writes == 1

    # Second pass: nothing to do, no extra write.
    plan2 = config_sync_hooks.plan_hook_wiring([declaration], host.read_settings())
    result2 = config_sync_hooks.execute_hook_plan(plan2, host)
    assert result2.outcomes == []
    assert host.writes == 1
