import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import config_sync_plugins as plugins_module  # noqa: E402
import config_sync_propagators as propagators  # noqa: E402


def _host(tmp_path):
    context = propagators.SyncContext(
        claude_dir=tmp_path / ".claude", repo_dir=tmp_path / "repo"
    )
    return plugins_module.ClaudePluginHost(context)


class _Completed:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_add_marketplace_github_source_uses_repo_spec(tmp_path, monkeypatch):
    seen = {}

    def fake_run(arguments, **kwargs):
        seen["arguments"] = arguments
        return _Completed(returncode=0)

    monkeypatch.setattr(plugins_module.subprocess, "run", fake_run)
    outcome = _host(tmp_path).add_marketplace(
        "official", {"source": "github", "repo": "anthropics/x"}
    )
    assert outcome.ok is True
    assert seen["arguments"] == [
        "claude",
        "plugin",
        "marketplace",
        "add",
        "anthropics/x",
    ]


def test_add_marketplace_git_source_uses_url_spec(tmp_path, monkeypatch):
    seen = {}

    def fake_run(arguments, **kwargs):
        seen["arguments"] = arguments
        return _Completed(returncode=0)

    monkeypatch.setattr(plugins_module.subprocess, "run", fake_run)
    outcome = _host(tmp_path).add_marketplace(
        "m", {"source": "git", "url": "https://h/r.git"}
    )
    assert outcome.ok is True
    assert seen["arguments"][-1] == "https://h/r.git"


def test_add_marketplace_missing_spec_does_not_shell_out(tmp_path, monkeypatch):
    called = {"ran": False}

    def fake_run(arguments, **kwargs):
        called["ran"] = True
        return _Completed(returncode=0)

    monkeypatch.setattr(plugins_module.subprocess, "run", fake_run)
    outcome = _host(tmp_path).add_marketplace("m", {"source": "github"})  # no repo key
    assert outcome.ok is False and outcome.message == "no source spec"
    assert called["ran"] is False  # never shelled out


def test_run_reports_missing_cli(tmp_path, monkeypatch):
    def fake_run(arguments, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(plugins_module.subprocess, "run", fake_run)
    outcome = _host(tmp_path).install_plugin("x@official")
    assert outcome.ok is False and outcome.message == "claude CLI not found"


def test_run_reports_timeout(tmp_path, monkeypatch):
    def fake_run(arguments, **kwargs):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=180)

    monkeypatch.setattr(plugins_module.subprocess, "run", fake_run)
    outcome = _host(tmp_path).update_plugin("x@official")
    assert outcome.ok is False and "timed out" in outcome.message


def test_install_plugin_success_path(tmp_path, monkeypatch):
    def fake_run(arguments, **kwargs):
        return _Completed(returncode=0, stdout="installed")

    monkeypatch.setattr(plugins_module.subprocess, "run", fake_run)
    outcome = _host(tmp_path).install_plugin("x@official")
    assert outcome.ok is True
    assert outcome.verb == "install_plugin" and outcome.target == "x@official"
