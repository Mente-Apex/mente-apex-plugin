import config_sync


def _seed_orphan_and_stale(claude_home):
    """settings.json with an orphaned enabledPlugins entry + a stale cache dir."""
    (claude_home / "settings.json").write_text(config_sync.json.dumps({
        "model": "opus",
        "enabledPlugins": {"ghost@deadmkt": True, "real@keepmkt": True},
    }))
    plugins = claude_home / "plugins"
    (plugins).mkdir()
    (plugins / "installed_plugins.json").write_text(config_sync.json.dumps({
        "version": 2, "plugins": {"real@keepmkt": [{"version": "1.0"}]},
    }))
    (plugins / "cache" / "deadmkt").mkdir(parents=True)   # stale — no installed plugin @deadmkt
    (plugins / "cache" / "keepmkt").mkdir(parents=True)   # live — real@keepmkt
    return claude_home / "settings.json", plugins / "cache" / "deadmkt"


def test_export_does_not_mutate_disk(claude_home, capsys):
    settings, stale_cache = _seed_orphan_and_stale(claude_home)
    before = settings.read_text()

    config_sync.cmd_export()
    capsys.readouterr()   # swallow the printed snapshot

    assert settings.read_text() == before          # settings.json untouched
    assert stale_cache.exists()                     # stale cache dir NOT pruned


def test_reconcile_cleans_settings_and_prunes_cache(claude_home, capsys):
    settings, stale_cache = _seed_orphan_and_stale(claude_home)

    config_sync.cmd_reconcile()
    capsys.readouterr()

    result = config_sync.json.loads(settings.read_text())
    assert "ghost@deadmkt" not in result["enabledPlugins"]   # orphan dropped
    assert "real@keepmkt" in result["enabledPlugins"]         # live kept
    assert not stale_cache.exists()                            # stale cache pruned
