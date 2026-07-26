import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import config_sync_plugins as plugins_module  # noqa: E402
import config_sync_propagators as propagators  # noqa: E402


def _write_registry(claude_dir):
    plugins_dir = claude_dir / "plugins"
    plugins_dir.mkdir(parents=True)
    (plugins_dir / "installed_plugins.json").write_text(json.dumps({
        "version": 2,
        "plugins": {"superpowers@claude-plugins-official": [
            {"scope": "user", "installPath": "/x", "version": "6.1.1"}]},
    }))
    (plugins_dir / "known_marketplaces.json").write_text(json.dumps({
        "claude-plugins-official": {"source": {"source": "github", "repo": "anthropics/claude-plugins-official"}}}))


def test_read_helpers_return_empty_on_missing(tmp_path):
    assert plugins_module._read_installed_plugins(tmp_path) == {}
    assert plugins_module._read_known_marketplaces(tmp_path) == {}


def test_reader_flattens_installed_entries(tmp_path):
    claude_dir = tmp_path / ".claude"
    _write_registry(claude_dir)
    context = propagators.SyncContext(claude_dir=claude_dir, repo_dir=tmp_path / "repo")
    reader = plugins_module.ClaudePluginHost(context)

    installed = reader.installed_plugins()
    assert installed["superpowers@claude-plugins-official"]["version"] == "6.1.1"   # list flattened to entry
    assert "claude-plugins-official" in reader.known_marketplaces()
