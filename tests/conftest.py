"""Shared fixtures. Isolates the engine from the real ~/.claude."""

import sys
from pathlib import Path

import pytest

# Make `import config_sync` resolve to scripts/config_sync.py
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import config_sync  # noqa: E402


@pytest.fixture
def claude_home(tmp_path, monkeypatch):
    """Point every engine path global at an isolated throwaway ~/.claude."""
    home = tmp_path / "home"
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True)
    monkeypatch.setattr(config_sync, "HOME", home)
    monkeypatch.setattr(config_sync, "CLAUDE_DIR", claude_dir)
    monkeypatch.setattr(
        config_sync, "CONFIG_FILE", claude_dir / "config-sync-config.json"
    )
    monkeypatch.setattr(config_sync, "CONFIG_REPO", claude_dir / "config-sync-repo")
    monkeypatch.setattr(config_sync, "PLUGINS_DIR", claude_dir / "plugins")
    monkeypatch.setattr(
        config_sync,
        "INSTALLED_PLUGINS_FILE",
        claude_dir / "plugins" / "installed_plugins.json",
    )
    return claude_dir
