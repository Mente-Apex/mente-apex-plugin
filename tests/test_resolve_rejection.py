"""One machine overruling another's rejection, without writing their file."""

import json

import pytest

import config_sync
from config_sync_rejections import (
    RejectionRecord,
    SharedRejectionStore,
    rejection_id_of,
)

ADDRESS = "rules/a.md"
REJECTION_ID = rejection_id_of("snapshot-file", ADDRESS)


@pytest.fixture(autouse=True)
def _isolated_claude_home(claude_home):
    """Every test here goes through `_rejection_policy`, which reads
    `config_sync.CLAUDE_DIR` for its local store, and `_machine_id`, which
    reads/creates `config_sync.CLAUDE_DIR / "config-sync-machine-id"`.
    Requesting the repo's `claude_home` fixture (tests/conftest.py) redirects
    those module globals — and everything else `claude_home` touches — to an
    isolated throwaway directory, so no test can write the operator's real
    `~/.claude`.
    """
    return claude_home


def _repo_with_foreign_rejection(tmp_path):
    repo = tmp_path / "repo"
    SharedRejectionStore(repo, "machine-b").record(
        RejectionRecord(
            id=REJECTION_ID,
            kind="snapshot-file",
            address=ADDRESS,
            scope="network",
            rejected_at="2026-08-03T09:00:00+00:00",
            machine_id="machine-b",
        )
    )
    return repo


def test_keep_writes_a_revival_into_this_machines_own_file(tmp_path, capsys):
    repo = _repo_with_foreign_rejection(tmp_path)
    config_sync.cmd_resolve_rejection(str(repo), REJECTION_ID, "keep")
    capsys.readouterr()
    own = json.loads(
        (repo / "rejections" / f"{config_sync._machine_id()}.json").read_text(
            encoding="utf-8"
        )
    )
    assert own["rejections"][0]["revives"] == REJECTION_ID


def test_keep_leaves_the_other_machines_file_untouched(tmp_path, capsys):
    repo = _repo_with_foreign_rejection(tmp_path)
    before = (repo / "rejections" / "machine-b.json").read_text(encoding="utf-8")
    config_sync.cmd_resolve_rejection(str(repo), REJECTION_ID, "keep")
    capsys.readouterr()
    assert (repo / "rejections" / "machine-b.json").read_text(
        encoding="utf-8"
    ) == before


def test_remove_records_the_local_decision_without_a_revival(tmp_path, capsys):
    repo = _repo_with_foreign_rejection(tmp_path)
    config_sync.cmd_resolve_rejection(str(repo), REJECTION_ID, "remove")
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "remove"
    assert not (repo / "rejections" / f"{config_sync._machine_id()}.json").exists()


def test_an_unknown_decision_is_refused(tmp_path):
    repo = _repo_with_foreign_rejection(tmp_path)
    with pytest.raises(ValueError):
        config_sync.cmd_resolve_rejection(str(repo), REJECTION_ID, "maybe")


def test_an_unknown_rejection_id_is_refused(tmp_path):
    repo = _repo_with_foreign_rejection(tmp_path)
    with pytest.raises(config_sync.UnknownRejectionTargetError):
        config_sync.cmd_resolve_rejection(str(repo), "notarealid00", "keep")


def test_the_command_is_registered():
    assert "resolve-rejection" in config_sync.COMMANDS
