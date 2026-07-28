"""Shared fixtures. Isolates the engine from the real ~/.claude."""

import sys
from pathlib import Path

import pytest

# Make `import config_sync` resolve to scripts/config_sync.py
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import config_sync  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_root_declarations(monkeypatch):
    """Point the engine's environment at an isolated dict, like `claude_home`
    does for every path global.

    Named roots are declared through CONFIG_SYNC_ROOT_* variables, so a machine
    that really declares one leaks it into every test. This repo's author
    declares CONFIG_SYNC_ROOT_MENTE_APEX_MEMORY, and that repo ships its own
    hooks/hooks.json — so a test declaring a single throwaway root saw the real
    repo's hooks discovered alongside it, planned four registrations instead of
    one, and tokenised the wrong command on export.

    Substituting `config_sync.ENVIRON` rather than scrubbing `os.environ` uses
    the seam the engine already exposes: `default_registry` takes `environ`
    injected precisely so tests need not touch process globals. Tests declare
    roots by writing to this dict via the `root_environ` fixture.

    Autouse because of the failure mode: an ambient declaration makes the suite
    green wherever nobody uses the feature and red only on the machines that do.
    """
    isolated_environ = {}
    monkeypatch.setattr(config_sync, "ENVIRON", isolated_environ)
    return isolated_environ


@pytest.fixture
def root_environ(isolated_root_declarations):
    """The dict a test writes CONFIG_SYNC_ROOT_* declarations into."""
    return isolated_root_declarations


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
