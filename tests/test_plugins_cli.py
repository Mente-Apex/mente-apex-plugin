import json

import config_sync


class _FakeHost:
    """Implements both ports so it can drive plan (reader) and apply (installer)."""
    def __init__(self):
        self.calls = []

    def installed_plugins(self):
        return {}

    def known_marketplaces(self):
        return {"official": {"source": {"source": "github", "repo": "a/b"}}}

    def add_marketplace(self, name, source):
        import config_sync_plugins as plugins_module
        self.calls.append(("add_marketplace", name))
        return plugins_module.ActionOutcome("add_marketplace", name, ok=True)

    def update_marketplace(self, name):
        import config_sync_plugins as plugins_module
        self.calls.append(("update_marketplace", name))
        return plugins_module.ActionOutcome("update_marketplace", name, ok=True)

    def install_plugin(self, key):
        import config_sync_plugins as plugins_module
        self.calls.append(("install_plugin", key))
        return plugins_module.ActionOutcome("install_plugin", key, ok=True)

    def update_plugin(self, key):
        import config_sync_plugins as plugins_module
        self.calls.append(("update_plugin", key))
        return plugins_module.ActionOutcome("update_plugin", key, ok=True)


def _seed_manifest(repo):
    manifest_dir = repo / "plugins"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "m1.json").write_text(json.dumps({
        "machine_id": "m1", "exported_at": "2026-01-01T00:00:00+00:00",
        "marketplaces": {"official": {"source": {"source": "github", "repo": "a/b"}}},
        "plugins": {"new@official": {"marketplace": "official", "name": "new", "version": "1.0"}},
    }))


def test_cmd_plugins_plan_prints_actions(claude_home, tmp_path, capsys):
    repo = tmp_path / "repo"
    _seed_manifest(repo)

    config_sync.cmd_plugins_plan(str(repo), host=_FakeHost())
    payload = json.loads(capsys.readouterr().out)

    verbs = {(action["verb"], action["target"]) for action in payload["actions"]}
    assert ("update_marketplace", "official") in verbs
    assert ("install_plugin", "new@official") in verbs


def test_cmd_plugins_apply_executes_and_reports(claude_home, tmp_path, capsys):
    repo = tmp_path / "repo"
    _seed_manifest(repo)
    host = _FakeHost()

    config_sync.cmd_plugins_apply(str(repo), host=host)
    payload = json.loads(capsys.readouterr().out)

    assert ("install_plugin", "new@official") in host.calls          # actually executed
    assert all(outcome["ok"] for outcome in payload["outcomes"])
