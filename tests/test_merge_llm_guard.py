import config_sync


def test_smart_merge_defaults_to_structured_no_subprocess(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("subprocess.run must not be called by default")

    monkeypatch.setattr(config_sync.subprocess, "run", _boom)
    monkeypatch.delenv(config_sync.LLM_MERGE_ENV, raising=False)

    merged, strategy = config_sync._smart_merge_text("# S\n- a\n", "# S\n- b\n", context="CLAUDE.md")
    assert strategy == "section-union"
    assert "- a" in merged and "- b" in merged


def test_smart_merge_uses_llm_when_opted_in(monkeypatch):
    monkeypatch.setenv(config_sync.LLM_MERGE_ENV, "1")
    monkeypatch.setattr(config_sync.shutil, "which", lambda name: "/usr/bin/claude")

    class _Result:
        returncode = 0
        stdout = "MERGED BY LLM"

    monkeypatch.setattr(config_sync.subprocess, "run", lambda *a, **k: _Result())

    merged, strategy = config_sync._smart_merge_text("a", "b", context="CLAUDE.md")
    assert strategy == "llm-merge"
    assert merged == "MERGED BY LLM"


def test_llm_budget_caps_invocations(monkeypatch):
    monkeypatch.setenv(config_sync.LLM_MERGE_ENV, "1")
    monkeypatch.setattr(config_sync.shutil, "which", lambda name: "/usr/bin/claude")
    calls = {"count": 0}

    class _Result:
        returncode = 0
        stdout = "LLM"

    def _run(*args, **kwargs):
        calls["count"] += 1
        return _Result()

    monkeypatch.setattr(config_sync.subprocess, "run", _run)

    budget = config_sync._LlmMergeBudget(1)
    files_base = {"a.md": "x1", "b.md": "y1"}
    files_override = {"a.md": "x2", "b.md": "y2"}
    config_sync._merge_snapshot_files(files_base, files_override, budget=budget)

    assert calls["count"] == 1   # only one LLM merge allowed; the other falls back
