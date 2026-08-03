"""Consolidate must be able to forget.

The first test reproduces 2026-08-03 exactly: three machines were clean, and the
consolidated snapshot alone carried the superseded content. Anything that folds
`base_files` in without filtering it will pass every other test here and still
fail this one.
"""

import json

import config_sync
from config_sync_rejections import (
    RejectionRecord,
    SharedRejectionStore,
    rejection_id_of,
    section_address,
)

STALE = "## Memory protocol"
DOCUMENT = f"""# User Preferences

{STALE}

use the /memory skill
"""


def _repo(tmp_path, machine_files, consolidated_files):
    repo = tmp_path / "repo"
    (repo / "machines").mkdir(parents=True)
    (repo / "consolidated").mkdir(parents=True)
    for machine_id, files in machine_files.items():
        (repo / "machines" / f"{machine_id}.json").write_text(
            json.dumps(
                {
                    "machine_id": machine_id,
                    "timestamp": "2026-08-03T08:00:00+00:00",
                    "files": files,
                }
            ),
            encoding="utf-8",
        )
    (repo / "consolidated" / "snapshot.json").write_text(
        json.dumps({"machine_id": "consolidated", "files": consolidated_files}),
        encoding="utf-8",
    )
    return repo


def _reject(
    repo, address, kind="snapshot-section", rejected_at="2026-08-03T09:00:00+00:00"
):
    SharedRejectionStore(repo, "machine-a").record(
        RejectionRecord(
            id=rejection_id_of(kind, address),
            kind=kind,
            address=address,
            scope="network",
            rejected_at=rejected_at,
            machine_id="machine-a",
        )
    )


def _consolidated(repo):
    return json.loads(
        (repo / "consolidated" / "snapshot.json").read_text(encoding="utf-8")
    )


def test_content_carried_only_by_the_prior_consolidated_snapshot_is_stripped(
    tmp_path, capsys
):
    repo = _repo(
        tmp_path,
        machine_files={"machine-a": {"CLAUDE.md": "# User Preferences\n"}},
        consolidated_files={"CLAUDE.md": DOCUMENT},
    )
    _reject(repo, section_address("CLAUDE.md", STALE, 0))

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert STALE not in _consolidated(repo)["files"]["CLAUDE.md"]


def test_an_empty_ledger_changes_nothing(tmp_path, capsys):
    repo = _repo(
        tmp_path,
        machine_files={"machine-a": {"CLAUDE.md": DOCUMENT}},
        consolidated_files={"CLAUDE.md": DOCUMENT},
    )
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()
    assert STALE in _consolidated(repo)["files"]["CLAUDE.md"]


def test_a_machine_re_adding_it_later_wins(tmp_path, capsys):
    repo = _repo(
        tmp_path,
        machine_files={"machine-b": {"CLAUDE.md": DOCUMENT}},
        consolidated_files={},
    )
    (repo / "machines" / "machine-b.json").write_text(
        json.dumps(
            {
                "machine_id": "machine-b",
                "timestamp": "2026-08-03T11:00:00+00:00",
                "files": {"CLAUDE.md": DOCUMENT},
            }
        ),
        encoding="utf-8",
    )
    _reject(
        repo,
        section_address("CLAUDE.md", STALE, 0),
        rejected_at="2026-08-03T09:00:00+00:00",
    )

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert STALE in _consolidated(repo)["files"]["CLAUDE.md"]


def test_a_rejected_whole_file_never_reaches_the_consolidated_snapshot(
    tmp_path, capsys
):
    repo = _repo(
        tmp_path,
        machine_files={"machine-a": {"rules/unwanted.md": "no thanks"}},
        consolidated_files={},
    )
    _reject(repo, "rules/unwanted.md", kind="snapshot-file")

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert "rules/unwanted.md" not in _consolidated(repo)["files"]


def test_a_local_scope_rejection_does_not_touch_shared_state(tmp_path, capsys):
    repo = _repo(
        tmp_path,
        machine_files={"machine-a": {"CLAUDE.md": DOCUMENT}},
        consolidated_files={},
    )
    address = section_address("CLAUDE.md", STALE, 0)
    SharedRejectionStore(repo, "machine-a").record(
        RejectionRecord(
            id=rejection_id_of("snapshot-section", address),
            kind="snapshot-section",
            address=address,
            scope="local",
            rejected_at="2026-08-03T09:00:00+00:00",
            machine_id="machine-a",
        )
    )

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert STALE in _consolidated(repo)["files"]["CLAUDE.md"]


def test_the_removed_address_is_reported_in_both_the_snapshot_and_stdout(
    tmp_path, capsys
):
    repo = _repo(
        tmp_path,
        machine_files={"machine-a": {"CLAUDE.md": "# User Preferences\n"}},
        consolidated_files={"CLAUDE.md": DOCUMENT},
    )
    address = section_address("CLAUDE.md", STALE, 0)
    _reject(repo, address)

    config_sync.cmd_consolidate(str(repo))
    stdout_payload = json.loads(capsys.readouterr().out)

    assert address in _consolidated(repo)["rejected"]
    assert address in stdout_payload["rejected"]


def test_an_address_removed_from_both_base_files_and_an_incoming_snapshot_appears_once(
    tmp_path, capsys
):
    repo = _repo(
        tmp_path,
        machine_files={"machine-a": {"CLAUDE.md": DOCUMENT}},
        consolidated_files={"CLAUDE.md": DOCUMENT},
    )
    address = section_address("CLAUDE.md", STALE, 0)
    _reject(repo, address)

    config_sync.cmd_consolidate(str(repo))
    stdout_payload = json.loads(capsys.readouterr().out)

    assert _consolidated(repo)["rejected"].count(address) == 1
    assert stdout_payload["rejected"].count(address) == 1
