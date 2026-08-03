"""A rejected plugin stops being proposed, in the plan and in apply.

The plan is where this belongs: dropping the ACTION means the plugin never gets
installed and never reappears in the next sync's plan, which is the behaviour an
operator who declined it expects.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import config_sync_plugins as plugins  # noqa: E402
import config_sync_propagators as propagators  # noqa: E402
import config_sync_rejections as rejections  # noqa: E402
from config_sync_plugins import PlannedAction  # noqa: E402
from config_sync_rejections import (  # noqa: E402
    CompositeRejectionPolicy,
    LocalRejectionStore,
    NullRejectionPolicy,
    PluginAddressor,
    RejectionRecord,
    rejection_id_of,
)

PLUGIN = "open-memory@open-memory"
REJECTED_AT = "2026-08-03T09:00:00+00:00"


def _policy(tmp_path, scope="local"):
    store = LocalRejectionStore(tmp_path / "local.json")
    store.record(
        RejectionRecord(
            id=rejection_id_of("plugin", PLUGIN),
            kind="plugin",
            address=PLUGIN,
            scope=scope,
            rejected_at=REJECTED_AT,
            machine_id="machine-a",
        )
    )
    return CompositeRejectionPolicy([store])


def test_the_addressor_uses_the_plugin_id_itself():
    addressor = PluginAddressor()
    assert addressor.kind == "plugin"
    assert addressor.identify(PLUGIN) == PLUGIN
    assert addressor.matches(PLUGIN, PLUGIN)
    assert not addressor.matches(PLUGIN, "other@other")


def test_filtering_drops_only_the_rejected_action(tmp_path):
    actions = [
        PlannedAction(verb="install", target=PLUGIN, detail={}),
        PlannedAction(verb="install", target="keep-me@keep-me", detail={}),
    ]
    kept, removed = rejections.filter_plugin_actions(
        actions, _policy(tmp_path), REJECTED_AT
    )
    assert [action.target for action in kept] == ["keep-me@keep-me"]
    assert removed == [PLUGIN]


def test_the_null_policy_keeps_every_action():
    actions = [PlannedAction(verb="install", target=PLUGIN, detail={})]
    kept, removed = rejections.filter_plugin_actions(
        actions, NullRejectionPolicy(), REJECTED_AT
    )
    assert kept == actions
    assert removed == []


def test_an_action_added_later_than_the_rejection_survives(tmp_path):
    actions = [PlannedAction(verb="install", target=PLUGIN, detail={})]
    kept, _removed = rejections.filter_plugin_actions(
        actions, _policy(tmp_path), "2026-08-03T11:00:00+00:00"
    )
    assert [action.target for action in kept] == [PLUGIN]


class _FakeReader:
    def __init__(self, installed=None, marketplaces=None):
        self._installed = installed or {}
        self._marketplaces = marketplaces or {}

    def installed_plugins(self):
        return dict(self._installed)

    def known_marketplaces(self):
        return dict(self._marketplaces)


def _write_manifest(repo_dir, machine_id, marketplaces, plugins_section):
    manifest_dir = repo_dir / "plugins"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / f"{machine_id}.json").write_text(
        json.dumps(
            {
                "machine_id": machine_id,
                "exported_at": "2026-01-01T00:00:00+00:00",
                "marketplaces": marketplaces,
                "plugins": plugins_section,
            }
        )
    )


def test_plan_convergence_with_default_policy_keeps_every_action(tmp_path):
    """The default path (no policy passed) must be untouched — every existing
    caller relies on it."""
    repo_dir = tmp_path / "repo"
    _write_manifest(
        repo_dir,
        "m1",
        marketplaces={"official": {"source": {"source": "github", "repo": "a/b"}}},
        plugins_section={
            "new@official": {
                "marketplace": "official",
                "name": "new",
                "version": "1.0",
            }
        },
    )
    context = propagators.SyncContext(
        claude_dir=tmp_path / ".claude", repo_dir=repo_dir
    )
    reader = _FakeReader(installed={}, marketplaces={})

    plan = plugins.plan_convergence(context, reader)

    assert ("install_plugin", "new@official") in [
        (action.verb, action.target) for action in plan.actions
    ]


def test_plan_convergence_with_a_policy_drops_the_rejected_plugin(tmp_path):
    repo_dir = tmp_path / "repo"
    _write_manifest(
        repo_dir,
        "m1",
        marketplaces={},
        plugins_section={
            PLUGIN: {
                "marketplace": "open-memory",
                "name": "open-memory",
                "version": "1.0",
            }
        },
    )
    context = propagators.SyncContext(
        claude_dir=tmp_path / ".claude", repo_dir=repo_dir
    )
    reader = _FakeReader(installed={}, marketplaces={})

    plan = plugins.plan_convergence(context, reader, policy=_policy(tmp_path))

    assert plan.actions == []
    assert any(
        "rejected in the config-sync ledger" in reason for reason in plan.skipped
    )
