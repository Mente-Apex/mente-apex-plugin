import config_sync


def test_derive_plugin_meta_from_cache_path():
    entry = {
        "installPath": "/Users/x/.claude/plugins/cache/acme-market/cool-plugin/1.2.3",
        "version": "1.2.3",
        "gitCommitSha": "deadbeef",
    }
    meta = config_sync._derive_plugin_meta("cool-plugin@acme-market", entry)
    assert meta["marketplace"] == "acme-market"
    assert meta["name"] == "cool-plugin"
    assert meta["version"] == "1.2.3"
    assert meta["gitCommitSha"] == "deadbeef"


def test_derive_plugin_meta_falls_back_when_no_cache_segment():
    # Dev / linked plugin: installPath has no 'cache' segment — must not crash.
    entry = {"installPath": "/Users/x/dev/my-plugin", "version": "9.9"}
    meta = config_sync._derive_plugin_meta("my-plugin@local", entry)
    assert meta["key"] == "my-plugin@local"
    assert meta["marketplace"] == "local"
    assert meta["name"] == "my-plugin"
    assert meta["version"] == "9.9"
    assert "gitCommitSha" not in meta   # omitted when absent
