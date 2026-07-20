import config_sync_roots


def test_named_roots_excludes_home_catch_all():
    registry = config_sync_roots.RootRegistry([
        config_sync_roots.Root("HOME", "/Users/ai"),
        config_sync_roots.Root("MENTE_APEX_MEMORY", "/Users/ai/Projects/mente-apex-memory"),
    ])
    named = registry.named_roots()
    assert [root.token for root in named] == ["MENTE_APEX_MEMORY"]
