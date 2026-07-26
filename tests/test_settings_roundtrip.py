import config_sync


def test_engine_imports_and_scrubs_env():
    # _clean_settings is pure — no filesystem needed
    cleaned = config_sync._clean_settings('{"model": "opus", "env": {"K": "v"}}')
    assert cleaned == {"model": "opus"}


def test_import_preserves_local_env_and_apikeyhelper(claude_home, tmp_path):
    settings = claude_home / "settings.json"
    settings.write_text(
        '{"model":"opus","apiKeyHelper":"/bin/helper",'
        '"env":{"ANTHROPIC_API_KEY":"sk-live"},"permissions":{"allow":[]}}'
    )
    # A snapshot as export would produce it: settings.json scrubbed of env/secrets.
    scrubbed = config_sync._clean_settings(settings.read_text())
    snapshot = tmp_path / "snap.json"
    snapshot.write_text(
        config_sync.json.dumps(
            {"files": {"settings.json": config_sync.json.dumps(scrubbed)}}
        )
    )

    config_sync.cmd_import(str(snapshot))

    result = config_sync.json.loads(settings.read_text())
    assert result["env"] == {"ANTHROPIC_API_KEY": "sk-live"}  # preserved
    assert result["apiKeyHelper"] == "/bin/helper"  # preserved
    assert result["model"] == "opus"  # applied from snapshot


def test_merge_import_settings_overlays_without_dropping_secrets():
    incoming = {"model": "sonnet", "permissions": {"allow": ["Bash"]}}
    local = {"model": "opus", "env": {"K": "v"}, "apiKeyHelper": "/h"}
    merged = config_sync._merge_import_settings(incoming, local)
    assert merged == {
        "model": "sonnet",
        "permissions": {"allow": ["Bash"]},
        "env": {"K": "v"},
        "apiKeyHelper": "/h",
    }
