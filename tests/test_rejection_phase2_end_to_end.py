"""One walk per new kind, across every module boundary.

Production-shaped on purpose: the consolidated snapshot carries a `timestamp`
that is STRICTLY NEWER than the rejection, because `cmd_consolidate` regenerates
it on every run. A filter that passed that timestamp as `source_timestamp` would
never suppress anything — which is exactly the defect that survived nine
unit-level suites in phase 1.
"""

import copy
import json

import pytest

import config_sync
import config_sync_hook_doctor
import config_sync_hooks
import config_sync_plugins
from config_sync_hooks import HookSite
from config_sync_rejection_hooks import HookRegistrationAddressor

REJECTED_AT = "2026-08-03T09:00:00+00:00"
CONSOLIDATED_AT = "2026-08-03T12:00:00+00:00"

SETTINGS = {
    "permissions": {"defaultMode": "acceptEdits"},
    "enabledPlugins": {"open-memory@open-memory": True},
    "model": "opus",
}


@pytest.fixture(autouse=True)
def _isolated_claude_home(claude_home):
    return claude_home


def _repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "machines").mkdir(parents=True)
    (repo / "consolidated").mkdir(parents=True)
    (repo / "machines" / "machine-a.json").write_text(
        json.dumps(
            {
                "machine_id": "machine-a",
                "timestamp": "2026-08-03T08:00:00+00:00",
                "files": {"settings.json": json.dumps(SETTINGS)},
            }
        ),
        encoding="utf-8",
    )
    (repo / "consolidated" / "snapshot.json").write_text(
        json.dumps(
            {
                "timestamp": CONSOLIDATED_AT,
                "files": {"settings.json": json.dumps(SETTINGS)},
            }
        ),
        encoding="utf-8",
    )
    return repo


def _consolidated(repo):
    return json.loads(
        (repo / "consolidated" / "snapshot.json").read_text(encoding="utf-8")
    )


def _settings_in(repo):
    return json.loads(_consolidated(repo)["files"]["settings.json"])


REJECTED_PLUGIN = "open-memory@open-memory"
SIBLING_PLUGIN = "keep-me@open-memory"


def _declare_plugins_in_repo(repo):
    """The repo's desired plugin state: the one the operator rejects, plus a
    sibling from the same marketplace that must survive the filter."""
    manifest_dir = repo / "plugins"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "machine-a.json").write_text(
        json.dumps(
            {
                "machine_id": "machine-a",
                "exported_at": "2026-08-03T08:00:00+00:00",
                "marketplaces": {
                    "open-memory": {
                        "source": {"source": "github", "repo": "example/open-memory"}
                    }
                },
                "plugins": {
                    REJECTED_PLUGIN: {"marketplace": "open-memory", "version": "1.0"},
                    SIBLING_PLUGIN: {"marketplace": "open-memory", "version": "1.0"},
                },
            }
        ),
        encoding="utf-8",
    )


def _install_plugin_registry(claude_home):
    """The live registry `ClaudePluginHost` reads: the marketplace is already
    known, nothing is installed yet, so both plugins are genuinely plannable."""
    plugins_dir = claude_home / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    (plugins_dir / "known_marketplaces.json").write_text(
        json.dumps(
            {"open-memory": {"source": {"source": "github", "repo": "e/open-memory"}}}
        ),
        encoding="utf-8",
    )
    (plugins_dir / "installed_plugins.json").write_text(
        json.dumps({"plugins": {}}), encoding="utf-8"
    )


def _real_plugin_plan(repo):
    """The production composition root for `plugins-plan`, verbatim: the real
    host reading the real registry, and the real COMPOSITE policy over the real
    on-disk ledger — plugins-plan writes LOCAL state, so both scopes apply."""
    _propagators, context = config_sync._sync_context(str(repo))
    return config_sync_plugins.plan_convergence(
        context,
        config_sync_plugins.ClaudePluginHost(context),
        policy=config_sync.local_rejection_policy(context),
    )


def _install_targets(plan):
    return [action.target for action in plan.actions if action.verb == "install_plugin"]


def test_a_settings_key_walks_from_reject_to_a_stripped_consolidated_snapshot(
    tmp_path, capsys
):
    repo = _repo(tmp_path)

    # Hop 1 — the operator rejects it network-wide.
    config_sync.cmd_reject(
        str(repo),
        "settings-key",
        "-",
        "--key",
        "permissions",
        "--key",
        "defaultMode",
        "--scope",
        "network",
    )
    recorded = json.loads(capsys.readouterr().out)
    assert recorded["scope"] == "network"

    # Hop 2 — the record landed in the SHARED repo, not the local ledger.
    assert list((repo / "rejections").glob("*.json"))

    # Hop 3 — consolidate strips it, and says so in the audit trail.
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()
    assert "defaultMode" not in _settings_in(repo)["permissions"]
    assert recorded["address"] in _consolidated(repo)["rejected"]

    # Hop 4 — the precondition that makes hop 3 meaningful: the snapshot's own
    # timestamp is NEWER than the rejection, so a generation-time comparison
    # would have let the key through.
    assert _consolidated(repo)["timestamp"] > recorded["rejected_at"]

    # Hop 5 — its siblings survived.
    assert _settings_in(repo)["model"] == "opus"

    # Hop 6 — unreject puts it back on the next consolidate.
    config_sync.cmd_unreject(str(repo), recorded["id"])
    capsys.readouterr()
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()
    assert _settings_in(repo)["permissions"]["defaultMode"] == "acceptEdits"


def test_a_plugin_rejection_is_withheld_by_the_real_planner_and_reversible(
    tmp_path, capsys, claude_home
):
    repo = _repo(tmp_path)
    _declare_plugins_in_repo(repo)
    _install_plugin_registry(claude_home)

    # Hop 1 — the operator rejects one of the two declared plugins.
    config_sync.cmd_reject(str(repo), "plugin", REJECTED_PLUGIN)
    recorded = json.loads(capsys.readouterr().out)

    # Hop 2 — it is visible to the ledger query.
    config_sync.cmd_rejections(str(repo))
    listed = json.loads(capsys.readouterr().out)["rejections"]
    assert [entry["address"] for entry in listed] == [REJECTED_PLUGIN]
    assert [entry["kind"] for entry in listed] == ["plugin"]

    # Hop 3 — the precondition that makes the rest meaningful: the regenerated
    # consolidated snapshot is STRICTLY NEWER than the rejection, so a filter
    # comparing against generation time would suppress nothing.
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()
    assert _consolidated(repo)["timestamp"] > recorded["rejected_at"]

    # Hop 4 — the real `plan_convergence` never proposes the rejected plugin...
    plan = _real_plugin_plan(repo)
    assert REJECTED_PLUGIN not in _install_targets(plan)

    # Hop 5 — ...while its non-rejected sibling from the same marketplace
    # survives. The filter is surgical, not an emptied plan.
    assert _install_targets(plan) == [SIBLING_PLUGIN]

    # Hop 6 — and the operator is told why.
    assert any(
        f"{REJECTED_PLUGIN}: rejected in the config-sync ledger" in reason
        for reason in plan.skipped
    )

    # Hop 7 — unreject puts it back into the very next real plan.
    config_sync.cmd_unreject(str(repo), recorded["id"])
    capsys.readouterr()
    config_sync.cmd_rejections(str(repo))
    assert json.loads(capsys.readouterr().out)["rejections"] == []
    assert sorted(_install_targets(_real_plugin_plan(repo))) == sorted(
        [REJECTED_PLUGIN, SIBLING_PLUGIN]
    )


def test_a_hook_rejection_survives_an_interpreter_change_and_is_withheld_by_wiring(
    tmp_path, capsys, claude_home
):
    repo = _repo(tmp_path)
    (claude_home / "settings.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python3 /abs/scripts/enforce_gates.py",
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    config_sync.cmd_reject(
        str(repo),
        "hook-registration",
        "enforce_gates.py",
        "--event",
        "PreToolUse",
        "--matcher",
        "Bash",
    )
    recorded = json.loads(capsys.readouterr().out)
    assert recorded["tier"] == "2"

    # The whole reason tier 2 exists: the same registration, reinstalled under a
    # different interpreter and a different directory, is still the same hook.
    reinstalled = HookSite(
        event="PreToolUse",
        group_index=0,
        hook_index=0,
        matcher="Bash",
        command="/new/uv/bin/python /somewhere/else/enforce_gates.py",
    )
    assert HookRegistrationAddressor().matches(
        recorded["address"], int(recorded["tier"]), reinstalled
    )

    # The precondition that makes the rest meaningful: the regenerated
    # consolidated snapshot is STRICTLY NEWER than the rejection, so a filter
    # comparing against generation time would suppress nothing.
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()
    assert _consolidated(repo)["timestamp"] > recorded["rejected_at"]

    # The real declarations: the rejected script, and a sibling that must
    # survive. Both are real files, so the real command checker passes them.
    scripts_dir = tmp_path / "declared-scripts"
    scripts_dir.mkdir()
    rejected_script = scripts_dir / "enforce_gates.py"
    sibling_script = scripts_dir / "keep_me.py"
    rejected_script.write_text("", encoding="utf-8")
    sibling_script.write_text("", encoding="utf-8")
    rejected_declaration = config_sync_hooks.declared_hook(
        "REPO", "PreToolUse", "Bash", str(rejected_script)
    )
    sibling_declaration = config_sync_hooks.declared_hook(
        "REPO", "PreToolUse", "Bash", str(sibling_script)
    )

    # The live settings block already carries the rejected registration.
    live_settings = json.loads(
        (claude_home / "settings.json").read_text(encoding="utf-8")
    )
    settings_before = copy.deepcopy(live_settings)

    # Drive the REAL planner through the production composition root: the
    # composite policy over the real on-disk ledger (hook wiring writes LOCAL
    # state, so both scopes are correct) and the real probing checker.
    _propagators, context = config_sync._sync_context(str(repo))
    plan = config_sync_hooks.plan_hook_wiring(
        [rejected_declaration, sibling_declaration],
        live_settings,
        checker=config_sync_hook_doctor.ProbingCommandChecker(
            config_sync_hook_doctor.FilesystemProbe()
        ),
        policy=config_sync.local_rejection_policy(context),
    )

    # The rejected declaration is never planned...
    planned_hook_ids = [action.hook_id for action in plan.actions]
    assert rejected_declaration.hook_id not in planned_hook_ids

    # ...while its non-rejected sibling still is. Surgical, not an empty plan.
    assert planned_hook_ids == [sibling_declaration.hook_id]

    # And the operator is told why.
    assert any(
        "rejected in the config-sync ledger" in reason and recorded["address"] in reason
        for reason in plan.skipped
    )

    # Withholding semantics: a rejection never DELETES a registration already on
    # disk — that is `hooks-prune`'s job. The block comes back untouched.
    assert live_settings == settings_before
