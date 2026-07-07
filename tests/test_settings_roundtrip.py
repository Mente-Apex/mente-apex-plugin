import config_sync


def test_engine_imports_and_scrubs_env():
    # _clean_settings is pure — no filesystem needed
    cleaned = config_sync._clean_settings('{"model": "opus", "env": {"K": "v"}}')
    assert cleaned == {"model": "opus"}
