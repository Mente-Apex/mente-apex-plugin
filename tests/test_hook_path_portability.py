"""Hook-command path portability (issue #65 item #1).

Export rewrites machine-absolute paths in settings.json hook `command` strings
into portable ${TOKEN} sentinels; import expands them back to the importing
machine's real absolute paths. HOME is always available; additional named repo
roots are declared per-machine.
"""
import config_sync
import config_sync_roots


def test_portabilize_replaces_home_prefix_with_token():
    registry = config_sync_roots.RootRegistry([
        config_sync_roots.Root("HOME", "/Users/ai"),
    ])
    command = "python3 /Users/ai/Projects/mem/hooks/protect_brain.py"
    assert registry.portabilize(command) == (
        "python3 ${HOME}/Projects/mem/hooks/protect_brain.py"
    )


def test_portabilize_prefers_the_most_specific_root():
    # A repo root nested under HOME must win over the HOME catch-all,
    # regardless of the order roots were declared in.
    registry = config_sync_roots.RootRegistry([
        config_sync_roots.Root("HOME", "/Users/ai"),
        config_sync_roots.Root("MENTE_APEX_MEMORY", "/Users/ai/Projects/mente-apex-memory"),
    ])
    command = "python3 /Users/ai/Projects/mente-apex-memory/hooks/protect_brain.py"
    assert registry.portabilize(command) == (
        "python3 ${MENTE_APEX_MEMORY}/hooks/protect_brain.py"
    )


def test_portabilize_only_matches_at_a_path_boundary():
    registry = config_sync_roots.RootRegistry([
        config_sync_roots.Root("HOME", "/Users/ai"),
    ])
    # A sibling path that merely starts with the same characters is NOT a match.
    assert registry.portabilize("python3 /Users/aimee/hooks/x.py") == (
        "python3 /Users/aimee/hooks/x.py"
    )
    # The real root — followed by a separator, or at end of string — is rewritten.
    assert registry.portabilize("python3 /Users/ai/hooks/x.py") == "python3 ${HOME}/hooks/x.py"
    assert registry.portabilize("cd /Users/ai") == "cd ${HOME}"


def test_localize_expands_tokens_to_this_machines_paths():
    # The importing machine resolves the same tokens to its own local paths,
    # which may differ from where the exporting machine had them.
    registry = config_sync_roots.RootRegistry([
        config_sync_roots.Root("HOME", "/home/bob"),
        config_sync_roots.Root("MENTE_APEX_MEMORY", "/home/bob/dev/mente-apex-memory"),
    ])
    portable = "python3 ${MENTE_APEX_MEMORY}/hooks/protect_brain.py"
    assert registry.localize(portable) == (
        "python3 /home/bob/dev/mente-apex-memory/hooks/protect_brain.py"
    )


def test_rewrite_leaves_unrelated_shell_vars_and_paths_untouched():
    # Real hooks (e.g. supacode's) carry their own shell vars; a path outside
    # every known root must survive a portabilize/localize round trip verbatim.
    registry = config_sync_roots.RootRegistry([
        config_sync_roots.Root("HOME", "/Users/ai"),
    ])
    command = '[ -n "${SUPACODE_SURFACE_ID:-}" ] && echo "$PPID" > /opt/tool/run.sh'
    assert registry.portabilize(command) == command
    assert registry.localize(command) == command


def test_default_registry_has_home_builtin_and_env_declared_roots():
    registry = config_sync_roots.default_registry(
        home="/Users/ai",
        environ={
            "CONFIG_SYNC_ROOT_MENTE_APEX_MEMORY": "/Users/ai/Projects/mente-apex-memory",
            "PATH": "/usr/bin",  # unrelated env vars are ignored
        },
    )
    assert registry.portabilize(
        "python3 /Users/ai/Projects/mente-apex-memory/hooks/protect_brain.py"
    ) == "python3 ${MENTE_APEX_MEMORY}/hooks/protect_brain.py"
    # HOME is always present with no configuration.
    assert registry.portabilize(
        "bash /Users/ai/.claude/hooks/guard.sh"
    ) == "bash ${HOME}/.claude/hooks/guard.sh"


def _settings_with_hook(command):
    return {
        "model": "opus",
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Write|Edit",
                    "hooks": [{"type": "command", "command": command, "timeout": 10}],
                }
            ]
        },
    }


def test_portabilize_settings_rewrites_every_hook_command_only():
    registry = config_sync_roots.RootRegistry([config_sync_roots.Root("HOME", "/Users/ai")])
    settings = _settings_with_hook("python3 /Users/ai/.claude/hooks/guard.py")

    result = registry.portabilize_settings(settings)

    hook = result["hooks"]["PreToolUse"][0]["hooks"][0]
    assert hook["command"] == "python3 ${HOME}/.claude/hooks/guard.py"
    assert result["model"] == "opus"                 # untouched
    assert settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == (
        "python3 /Users/ai/.claude/hooks/guard.py"   # input not mutated in place
    )


def test_localize_settings_expands_every_hook_command():
    registry = config_sync_roots.RootRegistry([config_sync_roots.Root("HOME", "/home/bob")])
    settings = _settings_with_hook("python3 ${HOME}/.claude/hooks/guard.py")

    result = registry.localize_settings(settings)

    hook = result["hooks"]["PreToolUse"][0]["hooks"][0]
    assert hook["command"] == "python3 /home/bob/.claude/hooks/guard.py"


def test_settings_survive_a_portabilize_localize_round_trip_across_homes():
    exporter = config_sync_roots.RootRegistry([config_sync_roots.Root("HOME", "/Users/ai")])
    importer = config_sync_roots.RootRegistry([config_sync_roots.Root("HOME", "/home/bob")])
    original = _settings_with_hook("python3 /Users/ai/.claude/hooks/guard.py")

    portable = exporter.portabilize_settings(original)
    localized = importer.localize_settings(portable)

    assert localized["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == (
        "python3 /home/bob/.claude/hooks/guard.py"
    )


# --- integration through the config_sync engine (the actual #65 fix) ----------

def test_export_portabilizes_hook_commands_in_snapshot(claude_home, capsys):
    home = claude_home.parent   # fixture: claude_dir = HOME/.claude
    (claude_home / "settings.json").write_text(config_sync.json.dumps(
        _settings_with_hook(f"python3 {home}/.claude/hooks/guard.py")
    ))

    config_sync.cmd_export()
    snapshot = config_sync.json.loads(capsys.readouterr().out)

    settings = config_sync.json.loads(snapshot["files"]["settings.json"])
    command = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert command == "python3 ${HOME}/.claude/hooks/guard.py"


def test_import_localizes_hook_commands_to_this_machine(claude_home, tmp_path):
    home = claude_home.parent
    (claude_home / "settings.json").write_text('{"model":"opus"}')
    snapshot = tmp_path / "snap.json"
    snapshot.write_text(config_sync.json.dumps({"files": {"settings.json": config_sync.json.dumps(
        _settings_with_hook("python3 ${HOME}/.claude/hooks/guard.py")
    )}}))

    config_sync.cmd_import(str(snapshot))

    result = config_sync.json.loads((claude_home / "settings.json").read_text())
    command = result["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert command == f"python3 {home}/.claude/hooks/guard.py"

