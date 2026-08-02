"""Hook wiring must reach its declared state and stay there.

Three ways it could not:

- A corrupt settings.json read as `{}`, so `hooks-apply` rewrote the file as
  `{"hooks": {...}}` and destroyed everything else in it.
- Two named roots shipping a same-named script under the same event and
  matcher took turns displacing each other through the `by_script` fallback,
  reporting `ok=True` every run and never converging.
- A declaration that dropped its `timeout` could never clear the old value, so
  every run emitted an update and reported success without reaching the
  declared state.
"""

import json

import pytest

import config_sync_hooks
from config_sync_hooks import (
    ClaudeSettingsHost,
    CorruptSettingsError,
    declared_hook,
    plan_hook_wiring,
)


class TestACorruptSettingsFileIsNeverTreatedAsEmpty:
    def test_reading_it_refuses_rather_than_returning_an_empty_dict(self, tmp_path):
        """One trailing comma made `hooks-apply` believe the settings were
        empty and rewrite the file, destroying `permissions`, `model`, `env`
        and `statusLine`."""
        (tmp_path / "settings.json").write_text(
            '{"model": "opus", "permissions": {"allow": ["Bash"]},}', encoding="utf-8"
        )
        host = ClaudeSettingsHost(tmp_path)

        with pytest.raises(CorruptSettingsError, match="not valid JSON"):
            host.read_settings()

    def test_a_missing_file_is_still_an_empty_dict(self, tmp_path):
        """The control: "there is no settings.json yet" is an ordinary state
        with an obvious answer, and must not start raising."""
        assert ClaudeSettingsHost(tmp_path).read_settings() == {}

    def test_the_file_is_left_untouched_by_the_refusal(self, tmp_path):
        original = '{"model": "opus",}'
        settings_path = tmp_path / "settings.json"
        settings_path.write_text(original, encoding="utf-8")

        with pytest.raises(CorruptSettingsError):
            ClaudeSettingsHost(tmp_path).read_settings()

        assert settings_path.read_text(encoding="utf-8") == original

    def test_a_valid_file_still_reads_normally(self, tmp_path):
        (tmp_path / "settings.json").write_text('{"model": "opus"}', encoding="utf-8")

        assert ClaudeSettingsHost(tmp_path).read_settings() == {"model": "opus"}


def _declaration(root_token, command, timeout=None):
    return declared_hook(
        root_token=root_token,
        event="SessionStart",
        matcher="*",
        command=command,
        timeout=timeout,
    )


class TestTwoRootsWithASameNamedScriptBothStayWired:
    """`hook_id` includes the root token; the `by_script` fallback key does
    not. So two such declarations had different ids -- invisible to the
    collision guard -- but the same fallback key, and each run one "updated"
    the other out of existence.
    """

    @staticmethod
    def _settings_with(*registrations):
        """A live settings block holding already-marked registrations."""
        return {
            "hooks": {
                "SessionStart": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": (
                                    f"{command} {config_sync_hooks.marker_for(hook_id)}"
                                ),
                            }
                        ],
                    }
                    for command, hook_id in registrations
                ]
            }
        }

    def test_neither_declaration_rewrites_the_others_registration(self):
        """Starting from settings where ALPHA is ALREADY registered, which is
        what makes the `by_script` fallback fire at all. Starting from `{}`
        never reaches the displacement path, so a test that does proves
        nothing about it."""
        alpha = _declaration("ALPHA", "python3 ${ALPHA}/hooks/guard.py")
        beta = _declaration("BETA", "python3 ${BETA}/hooks/guard.py")
        settings = self._settings_with(
            ("python3 ${ALPHA}/hooks/guard.py", alpha.hook_id)
        )

        plan = plan_hook_wiring([alpha, beta], settings, localize=lambda c: c)

        # BETA must not "update" ALPHA's entry into its own.
        assert [action for action in plan.actions if action.verb == "update"] == []
        registers = [action for action in plan.actions if action.verb == "register"]
        assert [action.hook_id for action in registers] == [beta.hook_id]

    def test_the_ambiguity_is_reported_rather_than_left_silent(self):
        """Refusing to guess leaves the older registration orphaned. The
        operator has to be told, or it fires forever unclaimed."""
        alpha = _declaration("ALPHA", "python3 ${ALPHA}/hooks/guard.py")
        beta = _declaration("BETA", "python3 ${BETA}/hooks/guard.py")
        settings = self._settings_with(("python3 ${ALPHA}/hooks/guard.py", "0" * 12))

        plan = plan_hook_wiring([alpha, beta], settings, localize=lambda c: c)

        assert any("hooks-doctor" in entry for entry in plan.skipped)

    def test_both_are_registered_from_an_empty_settings_block(self):
        declarations = [
            _declaration("ALPHA", "python3 ${ALPHA}/hooks/guard.py"),
            _declaration("BETA", "python3 ${BETA}/hooks/guard.py"),
        ]

        plan = plan_hook_wiring(declarations, {}, localize=lambda command: command)

        registered = [action for action in plan.actions if action.verb == "register"]
        assert len(registered) == 2
        assert len({action.hook_id for action in registered}) == 2

    def test_a_second_run_over_the_result_is_a_no_op(self):
        """Convergence is the whole point: the previous behaviour reported
        ok=True forever while leaving one of the two unwired."""
        declarations = [
            _declaration("ALPHA", "python3 ${ALPHA}/hooks/guard.py"),
            _declaration("BETA", "python3 ${BETA}/hooks/guard.py"),
        ]
        settings = {"hooks": {}}
        first = plan_hook_wiring(
            declarations, settings, localize=lambda command: command
        )
        for action in first.actions:
            settings.setdefault("hooks", {}).setdefault("SessionStart", []).append(
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": (
                                f"{action.detail['command']} "
                                f"{config_sync_hooks.marker_for(action.hook_id)}"
                            ),
                        }
                    ],
                }
            )

        second = plan_hook_wiring(
            declarations, settings, localize=lambda command: command
        )

        assert second.actions == []
        assert len(second.skipped) == 2

    def test_a_single_root_still_uses_the_fallback_to_re_find_a_moved_hook(self):
        """The control: the fallback exists so a registration whose command was
        rewritten is re-found rather than duplicated, and must keep working
        when it is not ambiguous."""
        declaration = _declaration("ALPHA", "${ALPHA}/bin/py ${ALPHA}/hooks/guard.py")
        settings = {
            "hooks": {
                "SessionStart": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": (
                                    "python3 ${ALPHA}/hooks/guard.py "
                                    f"{config_sync_hooks.marker_for('0' * 12)}"
                                ),
                            }
                        ],
                    }
                ]
            }
        }

        plan = plan_hook_wiring(
            [declaration], settings, localize=lambda command: command
        )

        assert [action.verb for action in plan.actions] == ["update"]


class TestADroppedTimeoutIsActuallyCleared:
    def test_the_entry_loses_the_timeout_it_no_longer_declares(self):
        """Setting-only meant the planner compared a surviving `timeout: 10`
        against the declaration's `None`, found them different, and emitted an
        update on every run, forever, without ever reaching declared state."""
        declaration = _declaration("ALPHA", "python3 ${ALPHA}/hooks/guard.py")
        marker = config_sync_hooks.marker_for(declaration.hook_id)
        entry = {
            "type": "command",
            "command": f"python3 ${{ALPHA}}/hooks/guard.py {marker}",
            "timeout": 10,
        }
        settings = {"hooks": {"SessionStart": [{"matcher": "*", "hooks": [entry]}]}}

        plan = plan_hook_wiring(
            [declaration], settings, localize=lambda command: command
        )
        assert [action.verb for action in plan.actions] == ["update"]

        config_sync_hooks._apply_declared_fields(
            entry, plan.actions[0], entry["command"]
        )

        assert "timeout" not in entry

    def test_a_declared_timeout_is_still_written(self):
        declaration = _declaration(
            "ALPHA", "python3 ${ALPHA}/hooks/guard.py", timeout=30
        )
        marker = config_sync_hooks.marker_for(declaration.hook_id)
        entry = {"type": "command", "command": f"cmd {marker}"}
        settings = {"hooks": {"SessionStart": [{"matcher": "*", "hooks": [entry]}]}}
        plan = plan_hook_wiring(
            [declaration], settings, localize=lambda command: command
        )

        config_sync_hooks._apply_declared_fields(
            entry, plan.actions[0], entry["command"]
        )

        assert entry["timeout"] == 30

    def test_a_field_the_declaration_does_not_own_survives(self):
        """`statusMessage` belongs to whoever put it there."""
        declaration = _declaration("ALPHA", "python3 ${ALPHA}/hooks/guard.py")
        marker = config_sync_hooks.marker_for(declaration.hook_id)
        entry = {
            "type": "command",
            "command": f"cmd {marker}",
            "statusMessage": "Checking",
        }
        settings = {"hooks": {"SessionStart": [{"matcher": "*", "hooks": [entry]}]}}
        plan = plan_hook_wiring(
            [declaration], settings, localize=lambda command: command
        )

        config_sync_hooks._apply_declared_fields(
            entry, plan.actions[0], entry["command"]
        )

        assert entry["statusMessage"] == "Checking"


class TestTheShippedHookCommandSurvivesASpaceInThePluginRoot:
    def test_both_plugin_root_references_are_quoted(self):
        """Unquoted, a plugin root containing a space failed with exit 127."""
        hooks_json = json.loads(
            (
                __import__("pathlib")
                .Path(config_sync_hooks.__file__)
                .resolve()
                .parent.parent
                / "hooks"
                / "hooks.json"
            ).read_text(encoding="utf-8")
        )
        command = hooks_json["hooks"]["SessionStart"][0]["hooks"][0]["command"]

        assert '"${CLAUDE_PLUGIN_ROOT}/bin/mente-python"' in command
        assert '"${CLAUDE_PLUGIN_ROOT}/hooks/merged_branch.py"' in command
