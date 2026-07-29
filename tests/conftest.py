"""Shared fixtures. Isolates the engine from the real ~/.claude."""

import subprocess
import sys
from pathlib import Path

import pytest

# Make `import config_sync` resolve to scripts/config_sync.py
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

# Make `import merged_branch` resolve to hooks/merged_branch.py — the hook ships
# in hooks/ because Claude Code loads a plugin's hooks from there, and like
# scripts/ it is a bare directory rather than an installed package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

import config_sync  # noqa: E402
import mutation_gate_prose  # noqa: E402


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


@pytest.fixture
def covered_slice(request):
    """The artifact slice this test declared via @pytest.mark.covers.

    The marker is also what the test READS, so the declaration and the
    assertion cannot drift apart — a guard can no longer window a region other
    than the one it named, which is the bug class the mutation gate exists to
    stop from recurring.
    """
    marker = request.node.get_closest_marker("covers")
    assert marker is not None, "this fixture requires an @pytest.mark.covers marker"
    artifact = Path(__file__).resolve().parents[1] / marker.args[0]
    text = artifact.read_text(encoding="utf-8")
    section = marker.kwargs.get("section")
    if section is None:
        return text
    return mutation_gate_prose.extract_section(text, section)


@pytest.fixture
def git_repo_with_branch(tmp_path):
    """A repo on a feature branch one commit ahead of its default branch."""

    def run(*args):
        return subprocess.run(args, cwd=tmp_path, check=True, capture_output=True)

    run("git", "init", "-q", "-b", "main")
    run("git", "config", "user.email", "t@example.com")
    run("git", "config", "user.name", "T")
    (tmp_path / "base.py").write_text("BASE = 1\n", encoding="utf-8")
    run("git", "add", ".")
    run("git", "commit", "-qm", "base")
    run("git", "checkout", "-qb", "feature")
    (tmp_path / "feature.py").write_text("FEATURE = 1\n", encoding="utf-8")
    run("git", "add", ".")
    run("git", "commit", "-qm", "feature")
    return tmp_path, "main"


# `--covers-manifest` is DELIBERATELY not registered here. It now lives in
# `scripts/mutation_gate_covers_plugin.py` and is loaded by the gate with
# `-p mutation_gate_covers_plugin`, so it works against any audited repo rather
# than only this one. Re-registering it here would collide with that plugin and
# fail the very run it was meant to serve.
