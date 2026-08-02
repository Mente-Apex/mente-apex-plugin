"""Diagnosis of the live hooks block — staleness and duplication (doctor/prune).

The bug this covers: config-sync's wiring only ever added, so a hook whose target
moved was never re-matched and its old registration survived forever. Once the
old path disappeared, every tool call in every project printed a hook error. The
doctor is the read side of that problem; prune is the gated write side.

Prune deletes from the user's global settings.json, so most of what follows is
about what it must REFUSE to delete. The probe is injected rather than hitting
the real filesystem: these tests must state which paths exist, not inherit
whatever the machine happens to have.
"""

import os

import pytest

import config_sync_hook_doctor as doctor
import config_sync_hooks


class FakeProbe:
    """A TargetProbe over a declared set of existing paths and PATH entries.

    Applies the same expanduser/realpath normalisation as FilesystemProbe. A fake
    that skipped it would answer differently from production for exactly the
    inputs `_is_absolute` admits (`~/...`) and `_exact_key` relies on (two
    spellings of one file), so a green suite would prove nothing about them.
    """

    def __init__(self, existing=(), on_path=(), links=None):
        self._existing = {os.path.expanduser(path) for path in existing}
        self._on_path = set(on_path)
        self._links = {
            os.path.expanduser(source): os.path.expanduser(target)
            for source, target in dict(links or {}).items()
        }

    def locate(self, target):
        if "/" in target:
            expanded = os.path.expanduser(target)
            return expanded if expanded in self._existing else None
        return f"/usr/bin/{target}" if target in self._on_path else None

    def resolve(self, target):
        expanded = os.path.normpath(os.path.expanduser(target))
        return self._links.get(expanded, expanded)


def _settings(*commands, event="PreToolUse", matcher="Write|Edit"):
    return {
        "hooks": {
            event: [
                {"matcher": matcher, "hooks": [{"type": "command", "command": command}]}
                for command in commands
            ]
        }
    }


def test_the_fake_probe_answers_like_the_real_one(tmp_path):
    """LSP guard. If these two ever disagree, every test below is theatre."""
    real_file = tmp_path / "real.py"
    real_file.write_text("")
    real = doctor.FilesystemProbe()
    fake = FakeProbe(existing={str(real_file)}, on_path={"python3"})

    for target in (str(real_file), str(tmp_path / "gone.py"), "python3", "no-such-bin"):
        assert (real.locate(target) is None) == (fake.locate(target) is None), target
    for target in (str(real_file), f"{tmp_path}/sub/../real.py", "~"):
        assert real.resolve(target) == fake.resolve(target), target


# --- command analysis -----------------------------------------------------


def test_an_interpreter_and_its_script_are_the_probeable_targets():
    shape = doctor.analyse_command("/opt/py/bin/python /Users/ai/hooks/guard.py")
    assert shape.probeable == ("/opt/py/bin/python", "/Users/ai/hooks/guard.py")


def test_a_data_argument_is_never_probed():
    """`--log /var/log/claude.log` names a file the hook CREATES. Probing it
    reported the whole hook as broken and prune deleted a working guard."""
    shape = doctor.analyse_command(
        "python3 /h/guard.py --log /var/log/claude-hooks.log"
    )
    assert shape.probeable == ("python3", "/h/guard.py")


def test_a_non_interpreter_program_contributes_no_script():
    shape = doctor.analyse_command("/usr/local/bin/graphify hook-guard read")
    assert shape.probeable == ("/usr/local/bin/graphify",)


def test_arguments_are_kept_in_the_identity_even_though_they_are_not_probed():
    first = doctor.analyse_command("graphify hook-guard search")
    second = doctor.analyse_command("graphify hook-guard read")
    assert first.probeable == second.probeable == ("graphify",)
    assert first.tokens != second.tokens


@pytest.mark.parametrize(
    "command",
    [
        '[ -n "${X:-}" ] && { printf y > /dev/tty; } || true',
        "$CLAUDE_PROJECT_DIR/.claude/hooks/check.sh",
        "${CONFIG_SYNC_ROOT_MEM}/hooks/protect_brain.py",
        "$HOME/bin/guard.sh",
        'python3 "unclosed',
        "",
    ],
)
def test_a_command_we_cannot_statically_resolve_is_opaque(command):
    """Opaque means "no claim made", and nothing is ever deleted on the strength
    of it. `$CLAUDE_PROJECT_DIR/...` is the idiom Claude Code's own hook docs
    recommend, and `${CONFIG_SYNC_ROOT_*}/...` is a string config-sync writes
    itself — both read as missing before `$` was treated as unresolvable, and
    both were pruned."""
    assert doctor.analyse_command(command).opaque is True


def test_the_marker_is_stripped_before_the_command_is_parsed():
    """A discriminating input: with the marker left on, this parses as the
    program `#`, which does not exist, which is a definitive finding, which
    prunes. Stripping is what makes it opaque instead."""
    assert doctor.analyse_command("# config-sync:abc123abc123").opaque is True
    assert doctor.analyse_command(
        "python3 /r/x.py # config-sync:abc123abc123"
    ).tokens == ("python3", "/r/x.py")


# --- staleness ------------------------------------------------------------


def test_a_missing_absolute_script_is_definitive():
    (diagnosis,) = doctor.diagnose(
        _settings("python3 /gone/hooks/protect_brain.py"),
        FakeProbe(on_path={"python3"}),
    )
    assert diagnosis.findings == (doctor.MISSING_TARGET,)
    assert diagnosis.missing_targets == ("/gone/hooks/protect_brain.py",)
    assert diagnosis.repairable is True


def test_a_missing_absolute_interpreter_is_definitive():
    (diagnosis,) = doctor.diagnose(
        _settings("/gone/bin/python /repo/hooks/x.py"),
        FakeProbe(existing={"/repo/hooks/x.py"}),
    )
    assert diagnosis.missing_targets == ("/gone/bin/python",)


def test_a_program_absent_from_this_path_is_advisory_not_definitive():
    """The hook runs in a shell whose PATH is not this process's. Deleting a
    hook because *we* could not find `mem` is not a defensible basis for an
    irreversible edit."""
    (diagnosis,) = doctor.diagnose(_settings("mem hook session-start"), FakeProbe())
    assert diagnosis.findings == (doctor.MISSING_ON_PATH,)
    assert diagnosis.repairable is False


def test_a_relative_program_path_is_advisory():
    """Hooks execute with cwd = the project dir; the doctor's cwd is wherever it
    was invoked. It cannot know, so it must not delete."""
    (diagnosis,) = doctor.diagnose(_settings(".claude/hooks/guard.sh"), FakeProbe())
    assert diagnosis.findings == (doctor.UNRESOLVABLE,)
    assert diagnosis.repairable is False


def test_a_glob_is_advisory():
    (diagnosis,) = doctor.diagnose(_settings("/opt/hooks/*.sh"), FakeProbe())
    assert diagnosis.findings == (doctor.UNRESOLVABLE,)


def test_a_tilde_path_is_expanded_before_it_is_judged(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "guard.sh").write_text("")
    probe = FakeProbe(existing={str(tmp_path / "guard.sh")})
    (diagnosis,) = doctor.diagnose(_settings("~/guard.sh"), probe)
    assert diagnosis.findings == ()


def test_a_fully_present_hook_has_no_findings():
    (diagnosis,) = doctor.diagnose(
        _settings("python3 /repo/hooks/x.py"),
        FakeProbe(existing={"/repo/hooks/x.py"}, on_path={"python3"}),
    )
    assert diagnosis.findings == ()


# --- duplication ----------------------------------------------------------


def test_the_same_invocation_twice_is_a_definitive_duplicate():
    settings = _settings(
        "python3 /repo/hooks/x.py",
        "python3 /repo/hooks/x.py # config-sync:aaaaaaaaaaaa",
    )
    probe = FakeProbe(existing={"/repo/hooks/x.py"}, on_path={"python3"})

    first, second = doctor.diagnose(settings, probe)

    assert first.findings == ()  # the first occurrence is the one kept
    assert second.findings == (doctor.DUPLICATE_COMMAND,)
    assert second.duplicate_of == first.site


def test_two_spellings_of_one_file_are_a_definitive_duplicate():
    settings = _settings("python3 /repo/hooks/x.py", "python3 /link/x.py")
    probe = FakeProbe(
        existing={"/repo/hooks/x.py", "/link/x.py"},
        on_path={"python3"},
        links={"/link/x.py": "/repo/hooks/x.py"},
    )

    _, second = doctor.diagnose(settings, probe)

    assert doctor.DUPLICATE_COMMAND in second.findings


def test_the_same_program_with_different_arguments_is_not_a_duplicate():
    """`graphify hook-guard search` and `... read` are two different guards.
    Keying the duplicate check on paths alone made them look like one, and
    prune deleted the second."""
    settings = _settings(
        "/bin/graphify hook-guard search", "/bin/graphify hook-guard read"
    )
    probe = FakeProbe(existing={"/bin/graphify"})

    assert all(
        diagnosis.findings == () for diagnosis in doctor.diagnose(settings, probe)
    )


def test_two_installs_of_the_same_script_name_are_advisory_only():
    """The reported symptom: protect_brain.py wired from several install
    locations, so the guard runs several times per Write. Different files, so
    name-based and never definitive."""
    settings = _settings(
        "python3 /Users/ai/Projects/mem/hooks/protect_brain.py",
        "python3 /Users/ai/.claude/mem/hooks/protect_brain.py",
    )
    probe = FakeProbe(
        existing={
            "/Users/ai/Projects/mem/hooks/protect_brain.py",
            "/Users/ai/.claude/mem/hooks/protect_brain.py",
        },
        on_path={"python3"},
    )

    first, second = doctor.diagnose(settings, probe)

    assert second.findings == (doctor.DUPLICATE_SCRIPT,)
    assert second.repairable is False
    assert second.duplicate_of == first.site


def test_an_explicit_interpreter_does_not_hide_a_same_script_duplicate():
    settings = _settings(
        "python3 /Users/ai/Projects/mem/hooks/protect_brain.py",
        "/opt/uv/bin/python /Users/ai/.claude/mem/hooks/protect_brain.py",
    )
    probe = FakeProbe(
        existing={
            "/Users/ai/Projects/mem/hooks/protect_brain.py",
            "/Users/ai/.claude/mem/hooks/protect_brain.py",
            "/opt/uv/bin/python",
        },
        on_path={"python3"},
    )

    _, second = doctor.diagnose(settings, probe)

    assert doctor.DUPLICATE_SCRIPT in second.findings


def test_an_exact_duplicate_behind_a_soft_duplicate_is_still_definitive():
    """Entry 2 is byte-identical to entry 1. Recording the exact key only on the
    else-branch meant entry 1 never entered the index, so entry 2 came back as a
    mere advisory and prune left a real duplicate in place."""
    settings = _settings("python3 /a/x.py", "python3 /b/x.py", "python3 /b/x.py")
    probe = FakeProbe(existing={"/a/x.py", "/b/x.py"}, on_path={"python3"})

    first, second, third = doctor.diagnose(settings, probe)

    assert first.findings == ()
    assert second.findings == (doctor.DUPLICATE_SCRIPT,)
    assert doctor.DUPLICATE_COMMAND in third.findings
    assert third.duplicate_of == second.site


def test_a_soft_duplicate_needs_the_same_event_and_matcher():
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Write",
                    "hooks": [{"type": "command", "command": "python3 /a/x.py"}],
                },
                {
                    "matcher": "Read",
                    "hooks": [{"type": "command", "command": "python3 /b/x.py"}],
                },
            ]
        }
    }
    probe = FakeProbe(existing={"/a/x.py", "/b/x.py"}, on_path={"python3"})

    assert all(
        diagnosis.findings == () for diagnosis in doctor.diagnose(settings, probe)
    )


def test_managed_and_unmanaged_entries_are_distinguished():
    settings = _settings(
        "python3 /repo/hooks/x.py",
        "python3 /repo/hooks/y.py # config-sync:0123456789ab",
    )
    probe = FakeProbe(
        existing={"/repo/hooks/x.py", "/repo/hooks/y.py"}, on_path={"python3"}
    )

    unmanaged, managed = doctor.diagnose(settings, probe)

    assert unmanaged.managed is False and unmanaged.hook_id is None
    assert managed.managed is True and managed.hook_id == "0123456789ab"


# --- pruning --------------------------------------------------------------


def test_prune_defaults_to_config_sync_owned_entries_only():
    settings = _settings(
        "python3 /gone/a.py",  # broken, but hand-added
        "python3 /gone/b.py # config-sync:0123456789ab",  # broken and ours
    )
    probe = FakeProbe(on_path={"python3"})

    plan = doctor.plan_hook_pruning(doctor.diagnose(settings, probe))

    assert [action.site.command for action in plan.actions] == [
        "python3 /gone/b.py # config-sync:0123456789ab"
    ]
    assert any("not config-sync's" in reason for reason in plan.skipped)


def test_prune_can_be_widened_to_the_unmanaged_entry():
    settings = _settings(
        "python3 /repo/keep.py",
        "python3 /gone/a.py",
    )
    probe = FakeProbe(existing={"/repo/keep.py"}, on_path={"python3"})

    plan = doctor.plan_hook_pruning(
        doctor.diagnose(settings, probe), include_unmanaged=True
    )

    assert [action.site.command for action in plan.actions] == ["python3 /gone/a.py"]


def test_prune_never_removes_an_advisory_finding():
    settings = _settings(
        "python3 /a/x.py # config-sync:0123456789ab",
        "python3 /b/x.py # config-sync:ba9876543210",
        "mem hook stop # config-sync:cccccccccccc",
        ".claude/hooks/rel.sh # config-sync:dddddddddddd",
    )
    probe = FakeProbe(existing={"/a/x.py", "/b/x.py"}, on_path={"python3"})

    plan = doctor.plan_hook_pruning(
        doctor.diagnose(settings, probe), include_unmanaged=True
    )

    assert plan.actions == []


def test_prune_reports_only_the_finding_that_justified_the_removal():
    """An advisory finding riding along on the same entry did not cause the
    deletion and must not be reported as if it had."""
    settings = _settings(
        "python3 /a/x.py",
        "python3 /gone/x.py # config-sync:0123456789ab",
    )
    probe = FakeProbe(existing={"/a/x.py"}, on_path={"python3"})

    diagnoses = doctor.diagnose(settings, probe)
    assert doctor.DUPLICATE_SCRIPT in diagnoses[1].findings  # rides along

    (action,) = doctor.plan_hook_pruning(diagnoses).actions
    assert action.reason == doctor.MISSING_TARGET


class FakeSettingsHost:
    def __init__(self, settings):
        self.settings = settings
        self.writes = 0

    def read_settings(self):
        import copy

        return copy.deepcopy(self.settings)

    def write_settings(self, settings):
        self.settings = settings
        self.writes += 1


def test_execute_removes_the_entry_and_collapses_the_emptied_group():
    settings = _settings(
        "python3 /repo/x.py",
        "python3 /gone/b.py # config-sync:0123456789ab",
    )
    probe = FakeProbe(existing={"/repo/x.py"}, on_path={"python3"})
    host = FakeSettingsHost(settings)

    plan = doctor.plan_hook_pruning(doctor.diagnose(host.read_settings(), probe))
    result = doctor.execute_prune_plan(plan, host)

    groups = host.settings["hooks"]["PreToolUse"]
    assert len(groups) == 1
    assert groups[0]["hooks"][0]["command"] == "python3 /repo/x.py"
    assert [outcome.ok for outcome in result.outcomes] == [True]
    assert host.writes == 1


def test_execute_removes_an_emptied_event_key_entirely():
    host = FakeSettingsHost(_settings("python3 /gone/b.py # config-sync:0123456789ab"))
    probe = FakeProbe(on_path={"python3"})

    doctor.execute_prune_plan(
        doctor.plan_hook_pruning(doctor.diagnose(host.read_settings(), probe)), host
    )

    assert "PreToolUse" not in host.settings["hooks"]


def test_execute_leaves_untouched_events_and_empty_groups_alone():
    """Sweeping the whole block also deleted an operator's deliberately-empty
    placeholder group and an unrelated event key — neither of which this command
    was asked to touch."""
    settings = _settings("python3 /gone/b.py # config-sync:0123456789ab")
    settings["hooks"]["PreToolUse"].append(
        {"matcher": "KEEP", "hooks": [], "note": "placeholder"}
    )
    settings["hooks"]["Untouched"] = [{"matcher": "", "hooks": []}]
    host = FakeSettingsHost(settings)
    probe = FakeProbe(on_path={"python3"})

    doctor.execute_prune_plan(
        doctor.plan_hook_pruning(doctor.diagnose(host.read_settings(), probe)), host
    )

    assert host.settings["hooks"]["Untouched"] == [{"matcher": "", "hooks": []}]
    assert host.settings["hooks"]["PreToolUse"] == [
        {"matcher": "KEEP", "hooks": [], "note": "placeholder"}
    ]


def test_execute_removes_several_entries_from_one_group_without_index_drift():
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Write",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 /gone/a.py # config-sync:0123456789ab",
                        },
                        {"type": "command", "command": "python3 /repo/keep.py"},
                        {
                            "type": "command",
                            "command": "python3 /gone/c.py # config-sync:ba9876543210",
                        },
                    ],
                }
            ]
        }
    }
    host = FakeSettingsHost(settings)
    probe = FakeProbe(existing={"/repo/keep.py"}, on_path={"python3"})

    doctor.execute_prune_plan(
        doctor.plan_hook_pruning(doctor.diagnose(host.read_settings(), probe)), host
    )

    remaining = host.settings["hooks"]["PreToolUse"][0]["hooks"]
    assert [hook["command"] for hook in remaining] == ["python3 /repo/keep.py"]


def test_execute_refuses_to_delete_when_the_file_moved_underneath_it():
    """The plan addresses by position, but positions came from the planner's
    read. If another writer inserts an entry in between, deleting blind removes
    the newcomer and leaves the dead hook."""
    settings = _settings("python3 /gone/b.py # config-sync:0123456789ab")
    probe = FakeProbe(on_path={"python3"})
    plan = doctor.plan_hook_pruning(doctor.diagnose(settings, probe))

    intruder = {"type": "command", "command": "python3 /repo/newcomer.py"}
    moved = _settings("python3 /gone/b.py # config-sync:0123456789ab")
    moved["hooks"]["PreToolUse"].insert(
        0, {"matcher": "Write|Edit", "hooks": [intruder]}
    )
    host = FakeSettingsHost(moved)

    result = doctor.execute_prune_plan(plan, host)

    assert [outcome.ok for outcome in result.outcomes] == [False]
    assert "changed since it was diagnosed" in result.outcomes[0].message
    assert host.writes == 0
    assert intruder in host.settings["hooks"]["PreToolUse"][0]["hooks"]


def test_execute_is_a_no_op_when_there_is_nothing_to_prune():
    host = FakeSettingsHost(_settings("python3 /repo/x.py"))
    probe = FakeProbe(existing={"/repo/x.py"}, on_path={"python3"})

    result = doctor.execute_prune_plan(
        doctor.plan_hook_pruning(doctor.diagnose(host.read_settings(), probe)), host
    )

    assert result.outcomes == []
    assert host.writes == 0


def test_the_backing_up_host_snapshots_once_before_the_first_write(tmp_path):
    inner = FakeSettingsHost({"model": "opus"})
    backup = tmp_path / "settings.bak.json"
    host = config_sync_hooks.BackingUpSettingsHost(inner, backup)

    assert not backup.exists()  # reads alone never snapshot
    host.read_settings()
    assert not backup.exists()

    host.write_settings({"model": "sonnet"})
    import json as json_module

    assert json_module.loads(backup.read_text()) == {"model": "opus"}

    host.write_settings({"model": "haiku"})
    assert json_module.loads(backup.read_text()) == {"model": "opus"}  # not re-taken
