"""Tests for the RemoteResolver seam in cmd_status (#48).

`status` must report the config-sync repo's ACTUAL git remote, not a `remote` key
that setup never writes into config-sync-config.json — that dead field made every
machine print `Remote: unknown` regardless of a working origin.

The resolver is an injected collaborator so the `git remote get-url` subprocess
boundary is substitutable: the high-level status-formatting policy depends on the
`resolve` abstraction, not on git.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import config_sync  # noqa: E402


class _StubResolver:
    """Records the repo path it was asked about and returns a canned URL, so a
    test can assert both WHAT status prints and THAT it queried the right repo."""

    def __init__(self, url):
        self._url = url
        self.asked_for = None

    def resolve(self, repo_path):
        self.asked_for = repo_path
        return self._url


def _write_config(claude_dir):
    """A minimal config-sync-config.json — the same shape setup writes, with NO
    `remote` key — so cmd_status reaches the remote line the way it does live."""
    (claude_dir / "config-sync-config.json").write_text(json.dumps({
        "machine_id": "test-machine",
        "last_sync": "2026-07-07T00:00:00+00:00",
        "repos": {},
    }))


# --- cmd_status uses the injected resolver ---------------------------------

def test_status_reports_injected_remote_url(claude_home, capsys):
    _write_config(claude_home)
    resolver = _StubResolver("git@github-menteapex:menteapex/mente-apex-config.git")

    config_sync.cmd_status(remote_resolver=resolver)

    output = capsys.readouterr().out
    assert "git@github-menteapex:menteapex/mente-apex-config.git" in output
    assert "unknown" not in output               # the dead-field fallback is gone
    assert resolver.asked_for == config_sync.CONFIG_REPO  # queried the repo, not config


def test_status_reports_not_configured_when_no_remote(claude_home, capsys):
    _write_config(claude_home)

    config_sync.cmd_status(remote_resolver=_StubResolver(None))

    output = capsys.readouterr().out
    assert "not configured" in output
    assert "unknown" not in output


# --- GitRemoteResolver against a real repo ---------------------------------

def test_git_remote_resolver_reads_origin(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github-menteapex:menteapex/mente-apex-config.git"],
        cwd=repo, check=True,
    )

    resolved = config_sync.GitRemoteResolver().resolve(repo)

    assert resolved == "git@github-menteapex:menteapex/mente-apex-config.git"


def test_git_remote_resolver_returns_none_without_origin(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)

    assert config_sync.GitRemoteResolver().resolve(repo) is None


def test_git_remote_resolver_returns_none_for_missing_repo(tmp_path):
    assert config_sync.GitRemoteResolver().resolve(tmp_path / "does-not-exist") is None
