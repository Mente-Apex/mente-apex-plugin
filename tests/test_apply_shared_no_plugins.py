import json
import config_sync


def test_apply_shared_ignores_plugins_and_never_writes_registry(claude_home, tmp_path, capsys):
    repo = tmp_path / "repo"
    plugin_dir = repo / "shared" / "plugins" / "foo@bar"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin-meta.json").write_text(json.dumps({
        "key": "foo@bar", "marketplace": "bar", "name": "foo", "version": "1.0"}))
    (plugin_dir / "somefile.txt").write_text("x")

    config_sync.cmd_apply_shared(str(repo))
    payload = json.loads(capsys.readouterr().out)

    assert not any("foo@bar" in entry for entry in payload["installed"])        # plugins no longer installed here
    assert not (claude_home / "plugins" / "installed_plugins.json").exists()    # registry never hand-written
