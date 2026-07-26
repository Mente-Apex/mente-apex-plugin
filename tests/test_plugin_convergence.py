import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import config_sync_plugins as plugins_module  # noqa: E402
import config_sync_propagators as propagators  # noqa: E402


class _FakeReader:
    def __init__(self, installed=None, marketplaces=None):
        self._installed = installed or {}
        self._marketplaces = marketplaces or {}

    def installed_plugins(self):
        return dict(self._installed)

    def known_marketplaces(self):
        return dict(self._marketplaces)


def _write_manifest(repo_dir, machine_id, marketplaces, plugins):
    manifest_dir = repo_dir / "plugins"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / f"{machine_id}.json").write_text(
        json.dumps(
            {
                "machine_id": machine_id,
                "exported_at": "2026-01-01T00:00:00+00:00",
                "marketplaces": marketplaces,
                "plugins": plugins,
            }
        )
    )


def _verbs(plan):
    return [(action.verb, action.target) for action in plan.actions]


def test_plan_installs_absent_updates_present_and_registers_marketplace(tmp_path):
    repo_dir = tmp_path / "repo"
    _write_manifest(
        repo_dir,
        "m1",
        marketplaces={"official": {"source": {"source": "github", "repo": "a/b"}}},
        plugins={
            "new@official": {
                "marketplace": "official",
                "name": "new",
                "version": "1.0",
            },
            "have@official": {
                "marketplace": "official",
                "name": "have",
                "version": "2.0",
            },
        },
    )
    context = propagators.SyncContext(
        claude_dir=tmp_path / ".claude", repo_dir=repo_dir
    )
    reader = _FakeReader(
        installed={"have@official": {"version": "1.9"}}, marketplaces={}
    )  # marketplace absent

    plan = plugins_module.plan_convergence(context, reader)
    verbs = _verbs(plan)

    assert (
        "add_marketplace",
        "official",
    ) in verbs  # not registered locally + source known
    assert ("update_marketplace", "official") in verbs  # always refresh (the #22 fix)
    assert ("install_plugin", "new@official") in verbs  # absent → install
    assert ("update_plugin", "have@official") in verbs  # present → converge to latest
    assert not any(verb.startswith("uninstall") for verb, _ in verbs)  # never uninstall


def test_plan_never_uninstalls_local_only_plugin(tmp_path):
    repo_dir = tmp_path / "repo"
    _write_manifest(
        repo_dir, "m1", marketplaces={}, plugins={}
    )  # manifest desires nothing
    context = propagators.SyncContext(
        claude_dir=tmp_path / ".claude", repo_dir=repo_dir
    )
    reader = _FakeReader(
        installed={"local-only@official": {"version": "1.0"}},
        marketplaces={"official": {"source": {"source": "github", "repo": "a/b"}}},
    )

    plan = plugins_module.plan_convergence(context, reader)
    assert plan.actions == []


def test_plan_skips_plugin_when_marketplace_source_unknown(tmp_path):
    repo_dir = tmp_path / "repo"
    _write_manifest(
        repo_dir,
        "m1",
        marketplaces={"ghost": {"source": None}},  # unregistered + no source
        plugins={"x@ghost": {"marketplace": "ghost", "name": "x", "version": "1"}},
    )
    context = propagators.SyncContext(
        claude_dir=tmp_path / ".claude", repo_dir=repo_dir
    )
    reader = _FakeReader(installed={}, marketplaces={})

    plan = plugins_module.plan_convergence(context, reader)
    assert plan.actions == []
    assert any("ghost" in reason for reason in plan.skipped)


def test_plan_unions_across_multiple_manifests(tmp_path):
    repo_dir = tmp_path / "repo"
    official = {"source": {"source": "github", "repo": "a/b"}}
    _write_manifest(
        repo_dir,
        "m1",
        marketplaces={"official": official},
        plugins={
            "alpha@official": {
                "marketplace": "official",
                "name": "alpha",
                "version": "1.0",
            }
        },
    )
    _write_manifest(
        repo_dir,
        "m2",
        marketplaces={"official": official},
        plugins={
            "beta@official": {
                "marketplace": "official",
                "name": "beta",
                "version": "1.0",
            }
        },
    )
    context = propagators.SyncContext(
        claude_dir=tmp_path / ".claude", repo_dir=repo_dir
    )
    reader = _FakeReader(installed={}, marketplaces={"official": official})

    verbs = _verbs(plugins_module.plan_convergence(context, reader))
    assert ("install_plugin", "alpha@official") in verbs  # from m1
    assert (
        "install_plugin",
        "beta@official",
    ) in verbs  # from m2 — union across machines


def test_plan_skips_malformed_manifest_without_crashing(tmp_path):
    repo_dir = tmp_path / "repo"
    manifest_dir = repo_dir / "plugins"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "bad.json").write_text(
        json.dumps({"marketplaces": None, "plugins": None})
    )
    (manifest_dir / "arr.json").write_text(json.dumps([1, 2, 3]))  # top-level array
    (manifest_dir / "badval.json").write_text(
        json.dumps(  # per-entry non-dict value
            {"marketplaces": {"official": "not-a-dict"}, "plugins": {}}
        )
    )
    official = {"source": {"source": "github", "repo": "a/b"}}
    _write_manifest(
        repo_dir,
        "m1",
        marketplaces={"official": official},
        plugins={
            "alpha@official": {
                "marketplace": "official",
                "name": "alpha",
                "version": "1.0",
            }
        },
    )
    context = propagators.SyncContext(
        claude_dir=tmp_path / ".claude", repo_dir=repo_dir
    )
    reader = _FakeReader(installed={}, marketplaces={"official": official})

    verbs = _verbs(plugins_module.plan_convergence(context, reader))  # must NOT raise
    assert (
        "install_plugin",
        "alpha@official",
    ) in verbs  # good manifest still processed


class _FakeInstaller:
    def __init__(self, fail_targets=None):
        self.calls = []
        self._fail_targets = set(fail_targets or [])

    def _outcome(self, verb, target):
        self.calls.append((verb, target))
        ok = target not in self._fail_targets
        return plugins_module.ActionOutcome(
            verb, target, ok=ok, message="" if ok else "boom"
        )

    def add_marketplace(self, name, source):
        return self._outcome("add_marketplace", name)

    def update_marketplace(self, name):
        return self._outcome("update_marketplace", name)

    def install_plugin(self, key):
        return self._outcome("install_plugin", key)

    def update_plugin(self, key):
        return self._outcome("update_plugin", key)


def test_execute_plan_runs_each_action_and_preserves_skips():
    plan = plugins_module.MarketplacePlan(
        actions=[
            plugins_module.PlannedAction(
                "add_marketplace",
                "official",
                {"source": {"source": "github", "repo": "a/b"}},
            ),
            plugins_module.PlannedAction("install_plugin", "new@official"),
        ],
        skipped=["plugin z@ghost: marketplace ghost unavailable"],
    )
    installer = _FakeInstaller()
    context = propagators.SyncContext(claude_dir=Path("/x"), repo_dir=Path("/y"))

    result = plugins_module.execute_plan(context, plan, installer)

    assert installer.calls == [
        ("add_marketplace", "official"),
        ("install_plugin", "new@official"),
    ]
    assert all(outcome.ok for outcome in result.outcomes)
    assert result.skipped == ["plugin z@ghost: marketplace ghost unavailable"]


def test_execute_plan_captures_failure_without_aborting():
    plan = plugins_module.MarketplacePlan(
        actions=[
            plugins_module.PlannedAction("install_plugin", "bad@official"),
            plugins_module.PlannedAction("install_plugin", "good@official"),
        ]
    )
    installer = _FakeInstaller(fail_targets={"bad@official"})
    context = propagators.SyncContext(claude_dir=Path("/x"), repo_dir=Path("/y"))

    result = plugins_module.execute_plan(context, plan, installer)

    outcomes = {outcome.target: outcome.ok for outcome in result.outcomes}
    assert outcomes == {
        "bad@official": False,
        "good@official": True,
    }  # continues past failure
