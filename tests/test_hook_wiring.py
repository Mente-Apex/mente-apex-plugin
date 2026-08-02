import json

import pytest

import config_sync_hooks
import config_sync_roots


def test_named_roots_excludes_home_catch_all():
    registry = config_sync_roots.RootRegistry(
        [
            config_sync_roots.Root("HOME", "/Users/ai"),
            config_sync_roots.Root(
                "MENTE_APEX_MEMORY", "/Users/ai/Projects/mente-apex-memory"
            ),
        ]
    )
    named = registry.named_roots()
    assert [root.token for root in named] == ["MENTE_APEX_MEMORY"]


def test_resolve_command_maps_plugin_root_to_token():
    assert (
        config_sync_hooks.resolve_command(
            "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/protect_brain.py", "MENTE_APEX_MEMORY"
        )
        == "python3 ${MENTE_APEX_MEMORY}/hooks/protect_brain.py"
    )


def test_hook_id_is_stable_12_hex_and_marker_round_trips():
    hook_id = config_sync_hooks.hook_id_of(
        "MENTE_APEX_MEMORY",
        "PreToolUse",
        "Write|Edit",
        "python3 ${MENTE_APEX_MEMORY}/hooks/protect_brain.py",
    )
    assert len(hook_id) == 12 and all(
        character in "0123456789abcdef" for character in hook_id
    )
    # same inputs -> same id
    assert hook_id == config_sync_hooks.hook_id_of(
        "MENTE_APEX_MEMORY",
        "PreToolUse",
        "Write|Edit",
        "python3 ${MENTE_APEX_MEMORY}/hooks/protect_brain.py",
    )
    marked = "python3 x.py " + config_sync_hooks.marker_for(hook_id)
    assert config_sync_hooks.registered_hook_ids(
        {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Write|Edit",
                        "hooks": [{"type": "command", "command": marked}],
                    }
                ]
            }
        }
    ) == {hook_id}


def _write_declaration(root_dir, block):
    hooks_dir = root_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    (hooks_dir / "hooks.json").write_text(json.dumps(block))


def test_discover_reads_declaration_and_resolves_token(tmp_path):
    repo = tmp_path / "mem"
    _write_declaration(
        repo,
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
        },
    )
    registry = config_sync_roots.RootRegistry(
        [
            config_sync_roots.Root("HOME", str(tmp_path)),
            config_sync_roots.Root("MEM", str(repo)),
        ]
    )

    declarations = config_sync_hooks.discover_declarations(registry)

    assert len(declarations) == 1
    declaration = declarations[0]
    assert declaration.event == "PreToolUse"
    assert declaration.matcher == "Write|Edit"
    assert declaration.command == "python3 ${MEM}/hooks/protect_brain.py"
    assert declaration.timeout == 10
    # Identity keys on the script, not the whole command, so relocating the
    # interpreter later resolves to this same registration.
    assert declaration.hook_id == config_sync_hooks.hook_id_of(
        "MEM",
        "PreToolUse",
        "Write|Edit",
        config_sync_hooks.script_key_of(declaration.command),
    )


def test_discover_ignores_missing_and_malformed(tmp_path):
    repo_missing = tmp_path / "nohooks"
    repo_missing.mkdir()
    repo_bad = tmp_path / "bad"
    (repo_bad / "hooks").mkdir(parents=True)
    (repo_bad / "hooks" / "hooks.json").write_text("{ not json")
    registry = config_sync_roots.RootRegistry(
        [
            config_sync_roots.Root("HOME", str(tmp_path)),
            config_sync_roots.Root("NOHOOKS", str(repo_missing)),
            config_sync_roots.Root("BAD", str(repo_bad)),
        ]
    )
    assert config_sync_hooks.discover_declarations(registry) == []


def test_discover_skips_non_dict_entries_inside_lists(tmp_path):
    # A hooks.json where matcher-group / hook entries are the wrong shape must be
    # skipped entry-by-entry (never fatal), while a valid sibling still resolves.
    repo = tmp_path / "mixed"
    _write_declaration(
        repo,
        {
            "hooks": {
                "PreToolUse": [
                    "oops-a-string",  # non-dict matcher-group
                    {"matcher": "A", "hooks": [42]},  # non-dict hook entry
                    {"matcher": "B", "hooks": "not-a-list"},  # non-list hooks value
                    {
                        "matcher": "Write|Edit",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/ok.py",
                                "timeout": 5,
                            }
                        ],
                    },
                ]
            }
        },
    )
    registry = config_sync_roots.RootRegistry(
        [
            config_sync_roots.Root("HOME", str(tmp_path)),
            config_sync_roots.Root("MIXED", str(repo)),
        ]
    )

    declarations = config_sync_hooks.discover_declarations(registry)

    assert len(declarations) == 1
    declaration = declarations[0]
    assert declaration.matcher == "Write|Edit"
    assert declaration.command == "python3 ${MIXED}/hooks/ok.py"
    assert declaration.timeout == 5


def _declaration(command="python3 ${MEM}/hooks/protect_brain.py"):
    return config_sync_hooks.declared_hook(
        "MEM", "PreToolUse", "Write|Edit", command, timeout=10
    )


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
    marked = (
        declaration.command + " " + config_sync_hooks.marker_for(declaration.hook_id)
    )
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Write|Edit",
                    "hooks": [
                        {"type": "command", "command": marked, "timeout": 10},
                    ],
                }
            ]
        }
    }
    plan = config_sync_hooks.plan_hook_wiring([declaration], settings)
    assert plan.actions == []


def test_plan_ignores_unmarked_hand_added_hook_for_same_script():
    declaration = _declaration()
    # Same script path, but NO marker -> config-sync must not consider it its own.
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Write|Edit",
                    "hooks": [{"type": "command", "command": declaration.command}],
                }
            ]
        }
    }
    plan = config_sync_hooks.plan_hook_wiring([declaration], settings)
    assert len(plan.actions) == 1  # still proposes its own marked registration


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


# --- identity that survives relocation ----------------------------------


def test_script_key_ignores_the_interpreter_prefix():
    """The reported bug: the same guard rewired through a different interpreter
    minted a second hook_id, so the old registration was orphaned rather than
    updated. Identity keys on the script, not the whole command."""
    assert config_sync_hooks.script_key_of(
        "python3 ${MEM}/hooks/protect_brain.py"
    ) == config_sync_hooks.script_key_of(
        "${MEM}/bin/mente-python ${MEM}/hooks/protect_brain.py"
    )


def test_script_key_prefers_the_script_over_a_data_argument():
    assert (
        config_sync_hooks.script_key_of(
            "${HOME}/.claude/hooks/inject.sh ${HOME}/.claude/hooks/directive.txt"
        )
        == "/.claude/hooks/inject.sh"
    )


def test_script_key_falls_back_to_the_whole_command_when_untokenised():
    assert config_sync_hooks.script_key_of("mem hook stop") == "mem hook stop"


def test_script_name_reads_both_the_portable_and_the_localized_form():
    """The live settings.json is always localized, so re-finding a registration
    cannot go through `script_key_of` — it only sees ${TOKEN} paths."""
    assert (
        config_sync_hooks.script_name_of("python3 ${MEM}/hooks/protect_brain.py")
        == config_sync_hooks.script_name_of(
            "/opt/uv/bin/python /abs/mem/hooks/protect_brain.py"
        )
        == "protect_brain.py"
    )


@pytest.mark.parametrize(
    "script, explicit_id",
    [("hooks/old_name.py", "protect-brain"), ("hooks/new_name.py", "protect-brain")],
)
def test_an_explicit_declaration_id_pins_identity_across_a_rename(script, explicit_id):
    """An `id` in hooks.json lets the declaring repo own its hook's identity, so
    even moving the script keeps the same registration."""
    declaration = config_sync_hooks.declared_hook(
        "MEM",
        "PreToolUse",
        "Write|Edit",
        "python3 ${MEM}/" + script,
        explicit_id=explicit_id,
    )
    assert declaration.hook_id == config_sync_hooks.hook_id_of(
        "MEM", "PreToolUse", "Write|Edit", "protect-brain"
    )


def test_discover_reads_an_explicit_id_from_the_declaration(tmp_path):
    repo = tmp_path / "mem"
    _write_declaration(
        repo,
        {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Write|Edit",
                        "hooks": [
                            {
                                "type": "command",
                                "id": "protect-brain",
                                "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/pb.py",
                            }
                        ],
                    }
                ]
            }
        },
    )
    registry = config_sync_roots.RootRegistry(
        [
            config_sync_roots.Root("HOME", str(tmp_path)),
            config_sync_roots.Root("MEM", str(repo)),
        ]
    )

    (declaration,) = config_sync_hooks.discover_declarations(registry)

    assert declaration.hook_id == config_sync_hooks.hook_id_of(
        "MEM", "PreToolUse", "Write|Edit", "protect-brain"
    )


# --- ambiguity is refused, not guessed at --------------------------------


def test_two_declarations_resolving_to_one_script_are_both_refused():
    """They would take turns overwriting each other's registration, run after
    run, leaving one permanently unwired. Refuse both and say what fixes it."""
    declarations = [
        _declaration("${MEM}/hooks/inject.sh ${MEM}/prompts/a.md"),
        _declaration("${MEM}/hooks/inject.sh ${MEM}/prompts/b.md"),
    ]
    assert declarations[0].hook_id == declarations[1].hook_id  # the collision

    plan = config_sync_hooks.plan_hook_wiring(declarations, {"hooks": {}})

    assert plan.actions == []
    assert len(plan.skipped) == 2
    assert all('explicit "id"' in reason for reason in plan.skipped)


def test_an_explicit_id_resolves_the_ambiguity():
    declarations = [
        config_sync_hooks.declared_hook(
            "MEM",
            "PreToolUse",
            "Write|Edit",
            "${MEM}/hooks/inject.sh ${MEM}/prompts/a.md",
            explicit_id="inject-a",
        ),
        config_sync_hooks.declared_hook(
            "MEM",
            "PreToolUse",
            "Write|Edit",
            "${MEM}/hooks/inject.sh ${MEM}/prompts/b.md",
            explicit_id="inject-b",
        ),
    ]
    plan = config_sync_hooks.plan_hook_wiring(declarations, {"hooks": {}})
    assert [action.verb for action in plan.actions] == ["register", "register"]


# --- relocation and migration --------------------------------------------


def _marked(command, hook_id, matcher="Write|Edit", event="PreToolUse", **extra):
    entry = {
        "type": "command",
        "command": command + " " + config_sync_hooks.marker_for(hook_id),
        "timeout": 10,  # what _declaration() declares; overridable via **extra
    }
    entry.update(extra)
    return {"hooks": {event: [{"matcher": matcher, "hooks": [entry]}]}}


def test_a_relocated_command_updates_the_existing_registration():
    original = _declaration("python3 ${MEM}/hooks/protect_brain.py")
    moved = _declaration("${MEM}/bin/mente-python ${MEM}/hooks/protect_brain.py")
    settings = _marked(original.command, original.hook_id)

    plan = config_sync_hooks.plan_hook_wiring([moved], settings)

    assert [action.verb for action in plan.actions] == ["update"]
    assert plan.actions[0].detail["match_hook_id"] == original.hook_id


def test_a_marker_from_the_old_identity_scheme_migrates_even_when_the_command_moved():
    """The case that matters, and the one a legacy-hash carried on the
    declaration could never cover: the plugin update ships the new identity
    scheme AND the relocated command together, so hashing the previous id over
    the *declared* command matches nothing and appends a duplicate instead."""
    old_command = "python3 ${MEM}/hooks/protect_brain.py"
    marker_in_the_wild = config_sync_hooks.hook_id_of(
        "MEM", "PreToolUse", "Write|Edit", old_command  # hashed over the full command
    )
    moved = _declaration("${MEM}/bin/mente-python ${MEM}/hooks/protect_brain.py")
    settings = _marked(old_command, marker_in_the_wild)

    plan = config_sync_hooks.plan_hook_wiring([moved], settings)

    assert [action.verb for action in plan.actions] == ["update"]
    assert plan.actions[0].hook_id == moved.hook_id


def test_an_ambiguous_script_name_is_left_alone_rather_than_guessed_at():
    declaration = _declaration("python3 ${MEM}/hooks/pb.py")
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Write|Edit",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 /one/pb.py # config-sync:aaaaaaaaaaaa",
                        }
                    ],
                },
                {
                    "matcher": "Write|Edit",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 /two/pb.py # config-sync:bbbbbbbbbbbb",
                        }
                    ],
                },
            ]
        }
    }

    plan = config_sync_hooks.plan_hook_wiring([declaration], settings)

    assert [action.verb for action in plan.actions] == ["register"]


def test_a_timeout_change_alone_is_still_an_update():
    declaration = config_sync_hooks.declared_hook(
        "MEM", "PreToolUse", "Write|Edit", "python3 ${MEM}/hooks/pb.py", timeout=120
    )
    settings = _marked(declaration.command, declaration.hook_id, timeout=10)

    plan = config_sync_hooks.plan_hook_wiring([declaration], settings)

    assert [action.verb for action in plan.actions] == ["update"]


# --- the localize seam ----------------------------------------------------


def test_the_declaration_is_localized_before_it_is_compared_and_written():
    """Planning in portable space instead made portabilize-then-localize
    asymmetry look like a change, rewriting some hooks on every single run."""
    declaration = _declaration("python3 ${MEM}/hooks/pb.py")
    localize = lambda command: command.replace("${MEM}", "/abs/mem")  # noqa: E731
    settings = _marked("python3 /abs/mem/hooks/pb.py", declaration.hook_id)

    plan = config_sync_hooks.plan_hook_wiring(
        [declaration], settings, localize=localize
    )

    assert plan.actions == []  # already registered, in the file's own space


def test_execute_writes_the_localized_command():
    declaration = _declaration("python3 ${MEM}/hooks/pb.py")
    localize = lambda command: command.replace("${MEM}", "/abs/mem")  # noqa: E731
    host = FakeSettingsHost({"hooks": {}})

    plan = config_sync_hooks.plan_hook_wiring(
        [declaration], host.read_settings(), localize=localize
    )
    config_sync_hooks.execute_hook_plan(plan, host)

    command = host.settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert command.startswith("python3 /abs/mem/hooks/pb.py # config-sync:")


# --- the executor ---------------------------------------------------------


def test_execute_rewrites_in_place_rather_than_appending():
    original = _declaration("python3 ${MEM}/hooks/protect_brain.py")
    moved = _declaration("${MEM}/bin/mente-python ${MEM}/hooks/protect_brain.py")
    host = FakeSettingsHost(_marked(original.command, original.hook_id))

    plan = config_sync_hooks.plan_hook_wiring([moved], host.read_settings())
    config_sync_hooks.execute_hook_plan(plan, host)

    groups = host.settings["hooks"]["PreToolUse"]
    assert len(groups) == 1 and len(groups[0]["hooks"]) == 1
    assert groups[0]["hooks"][0]["command"] == moved.command + " " + (
        config_sync_hooks.marker_for(moved.hook_id)
    )

    settled = config_sync_hooks.plan_hook_wiring([moved], host.read_settings())
    assert settled.actions == []


def test_an_update_preserves_fields_the_declaration_does_not_own():
    """This plugin's own hooks.json declares a statusMessage. Replacing the whole
    entry silently dropped it."""
    original = _declaration("python3 ${MEM}/hooks/mb.py")
    moved = _declaration("sh ${MEM}/bin/mente-python ${MEM}/hooks/mb.py")
    host = FakeSettingsHost(
        _marked(original.command, original.hook_id, statusMessage="Checking the branch")
    )

    plan = config_sync_hooks.plan_hook_wiring([moved], host.read_settings())
    config_sync_hooks.execute_hook_plan(plan, host)

    entry = host.settings["hooks"]["PreToolUse"][0]["hooks"][0]
    assert entry["statusMessage"] == "Checking the branch"
    assert entry["type"] == "command"


def test_an_update_refuses_to_write_when_the_marker_is_gone():
    """The plan was made against an earlier read. Trusting its indices would
    overwrite whatever now sits at that position."""
    original = _declaration("python3 ${MEM}/hooks/pb.py")
    moved = _declaration("${MEM}/bin/mente-python ${MEM}/hooks/pb.py")
    plan = config_sync_hooks.plan_hook_wiring(
        [moved], _marked(original.command, original.hook_id)
    )

    bystander = {"type": "command", "command": "python3 /repo/someone-elses.py"}
    host = FakeSettingsHost(
        {"hooks": {"PreToolUse": [{"matcher": "Write|Edit", "hooks": [bystander]}]}}
    )
    result = config_sync_hooks.execute_hook_plan(plan, host)

    assert [outcome.ok for outcome in result.outcomes] == [False]
    assert "changed since it was planned" in result.outcomes[0].message
    assert host.writes == 0
    assert host.settings["hooks"]["PreToolUse"][0]["hooks"] == [bystander]


def test_execute_handles_a_register_and_an_update_in_one_plan():
    existing = _declaration("python3 ${MEM}/hooks/pb.py")
    moved = _declaration("${MEM}/bin/py ${MEM}/hooks/pb.py")
    fresh = config_sync_hooks.declared_hook(
        "MEM", "PreToolUse", "Write|Edit", "python3 ${MEM}/hooks/gates.py"
    )
    host = FakeSettingsHost(_marked(existing.command, existing.hook_id))

    plan = config_sync_hooks.plan_hook_wiring([moved, fresh], host.read_settings())
    result = config_sync_hooks.execute_hook_plan(plan, host)

    assert [outcome.ok for outcome in result.outcomes] == [True, True]
    commands = [
        hook["command"]
        for group in host.settings["hooks"]["PreToolUse"]
        for hook in group["hooks"]
    ]
    assert len(commands) == 2
    assert any(command.startswith(moved.command) for command in commands)
    assert any(command.startswith(fresh.command) for command in commands)


def test_execute_writes_marked_registration_and_is_idempotent():
    declaration = _declaration()
    host = FakeSettingsHost({"hooks": {}})

    plan = config_sync_hooks.plan_hook_wiring([declaration], host.read_settings())
    result = config_sync_hooks.execute_hook_plan(plan, host)

    assert [outcome.ok for outcome in result.outcomes] == [True]
    groups = host.settings["hooks"]["PreToolUse"]
    command = groups[0]["hooks"][0]["command"]
    assert command == declaration.command + " " + config_sync_hooks.marker_for(
        declaration.hook_id
    )
    assert groups[0]["hooks"][0]["timeout"] == 10
    assert host.writes == 1

    # Second pass: nothing to do, no extra write.
    plan2 = config_sync_hooks.plan_hook_wiring([declaration], host.read_settings())
    result2 = config_sync_hooks.execute_hook_plan(plan2, host)
    assert result2.outcomes == []
    assert host.writes == 1


# --- a declaration whose script is absent ---------------------------------


class RefuseAll:
    """A CommandChecker that finds nothing runnable."""

    def is_runnable(self, command):
        return False


def test_a_declaration_whose_script_is_missing_is_not_wired():
    """Otherwise apply wires it, prune deletes it as a dead target, and the next
    apply wires it again — a flap with no stable state."""
    plan = config_sync_hooks.plan_hook_wiring(
        [_declaration()], {"hooks": {}}, checker=RefuseAll()
    )

    assert plan.actions == []
    assert "not on this machine" in plan.skipped[0]


def test_a_missing_script_blocks_an_update_too():
    declaration = _declaration()
    moved = _declaration("${MEM}/bin/py ${MEM}/hooks/protect_brain.py")
    settings = _marked(declaration.command, declaration.hook_id)

    plan = config_sync_hooks.plan_hook_wiring([moved], settings, checker=RefuseAll())

    assert plan.actions == []


def test_the_default_checker_makes_no_claim():
    """The planner must stay pure: nothing about it touches a filesystem unless
    a caller injects something that does."""
    assert config_sync_hooks.AssumeRunnable().is_runnable("python3 /nowhere/at/all.py")
    plan = config_sync_hooks.plan_hook_wiring([_declaration()], {"hooks": {}})
    assert len(plan.actions) == 1


def test_the_probing_checker_only_refuses_an_absent_absolute_path(tmp_path):
    import config_sync_hook_doctor

    present = tmp_path / "guard.py"
    present.write_text("")
    checker = config_sync_hook_doctor.ProbingCommandChecker(
        config_sync_hook_doctor.FilesystemProbe()
    )

    assert checker.is_runnable(f"python3 {present}") is True
    assert checker.is_runnable(f"python3 {tmp_path / 'gone.py'}") is False
    # Everything advisory stays runnable — same rule as prune.
    assert checker.is_runnable("definitely-not-a-real-binary --flag") is True
    assert checker.is_runnable(".claude/hooks/guard.sh") is True
    assert checker.is_runnable("$CLAUDE_PROJECT_DIR/hooks/guard.sh") is True


def test_the_probing_checker_satisfies_the_protocol():
    import config_sync_hook_doctor

    checker = config_sync_hook_doctor.ProbingCommandChecker(
        config_sync_hook_doctor.FilesystemProbe()
    )
    assert isinstance(checker, config_sync_hooks.CommandChecker)
    assert isinstance(
        config_sync_hooks.AssumeRunnable(), config_sync_hooks.CommandChecker
    )
