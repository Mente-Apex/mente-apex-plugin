"""The operator-facing surface: reject, list, undo."""

import json

import pytest

import config_sync
from config_sync_rejections import CorruptRejectionLedgerError  # noqa: F401

STALE = "## Memory protocol"
DOCUMENT = f"# User Preferences\n\n{STALE}\n\nuse the /memory skill\n"


@pytest.fixture(autouse=True)
def _isolated_claude_home(claude_home):
    """Every test here goes through `_rejection_policy`, which reads
    `config_sync.CLAUDE_DIR` for its local store. Requesting the repo's
    `claude_home` fixture (tests/conftest.py) redirects that module global —
    and everything else `claude_home` touches — to an isolated throwaway
    directory, so no test can write the operator's real `~/.claude`.
    """
    return claude_home


def _repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "consolidated").mkdir(parents=True)
    (repo / "consolidated" / "snapshot.json").write_text(
        json.dumps({"files": {"CLAUDE.md": DOCUMENT, "rules/a.md": "hi"}}),
        encoding="utf-8",
    )
    return repo


def test_rejecting_a_section_records_it(tmp_path, capsys):
    repo = _repo(tmp_path)
    config_sync.cmd_reject(
        str(repo), "snapshot-section", "CLAUDE.md", "--section", STALE
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "snapshot-section"
    assert payload["scope"] == "network"


def test_scope_defaults_to_network_and_local_is_selectable(
    tmp_path, capsys, claude_home
):
    repo = _repo(tmp_path)
    config_sync.cmd_reject(str(repo), "snapshot-file", "rules/a.md", "--scope", "local")
    assert json.loads(capsys.readouterr().out)["scope"] == "local"

    # Scope routing is the property that keeps a local veto out of the
    # network (CompositeRejectionPolicy.record routes by the record's own
    # scope) — assert it on disk, not just in the printed payload, so a
    # regression that routed "local" into the shared repo would be caught.
    shared_repo_rejections = repo / "rejections"
    assert not shared_repo_rejections.exists() or not any(
        shared_repo_rejections.glob("*.json")
    )

    local_ledger_path = claude_home / "config-sync-rejections.json"
    assert local_ledger_path.exists()
    local_rejections = json.loads(local_ledger_path.read_text(encoding="utf-8"))[
        "rejections"
    ]
    assert [entry["address"] for entry in local_rejections] == ["rules/a.md"]


def test_an_address_matching_nothing_is_refused(tmp_path):
    repo = _repo(tmp_path)
    with pytest.raises(config_sync.UnknownRejectionTargetError):
        config_sync.cmd_reject(str(repo), "snapshot-file", "rules/nope.md")


def test_a_section_heading_matching_nothing_is_refused(tmp_path):
    repo = _repo(tmp_path)
    with pytest.raises(config_sync.UnknownRejectionTargetError):
        config_sync.cmd_reject(
            str(repo), "snapshot-section", "CLAUDE.md", "--section", "## Nope"
        )


def test_an_unknown_kind_is_refused(tmp_path):
    repo = _repo(tmp_path)
    with pytest.raises(ValueError):
        config_sync.cmd_reject(str(repo), "not-a-kind", "CLAUDE.md")


def test_rejections_lists_what_was_recorded(tmp_path, capsys):
    repo = _repo(tmp_path)
    config_sync.cmd_reject(str(repo), "snapshot-file", "rules/a.md")
    capsys.readouterr()
    config_sync.cmd_rejections(str(repo))
    listed = json.loads(capsys.readouterr().out)["rejections"]
    assert [entry["address"] for entry in listed] == ["rules/a.md"]


def test_unreject_removes_it(tmp_path, capsys):
    repo = _repo(tmp_path)
    config_sync.cmd_reject(str(repo), "snapshot-file", "rules/a.md")
    rejection_id = json.loads(capsys.readouterr().out)["id"]
    config_sync.cmd_unreject(str(repo), rejection_id)
    capsys.readouterr()
    config_sync.cmd_rejections(str(repo))
    assert json.loads(capsys.readouterr().out)["rejections"] == []


def test_the_commands_are_registered():
    for name in ("reject", "rejections", "unreject"):
        assert name in config_sync.COMMANDS


SINGLE_SECTION = "## Only\n\nthe only thing here\n"


def _repo_with_single_section_file(tmp_path):
    repo = tmp_path / "repo2"
    (repo / "consolidated").mkdir(parents=True)
    (repo / "consolidated" / "snapshot.json").write_text(
        json.dumps({"files": {"solo.md": SINGLE_SECTION}}), encoding="utf-8"
    )
    return repo


def test_a_rejection_that_would_empty_a_file_is_refused(tmp_path):
    repo = _repo_with_single_section_file(tmp_path)
    with pytest.raises(config_sync.MassRejectionRefusedError):
        config_sync.cmd_reject(
            str(repo), "snapshot-section", "solo.md", "--section", "## Only"
        )


def test_force_overrides_the_mass_rejection_guard(tmp_path, capsys):
    repo = _repo_with_single_section_file(tmp_path)
    config_sync.cmd_reject(
        str(repo), "snapshot-section", "solo.md", "--section", "## Only", "--force"
    )
    assert json.loads(capsys.readouterr().out)["address"]


def test_rejecting_one_of_several_sections_is_not_guarded(tmp_path, capsys):
    repo = _repo(tmp_path)
    config_sync.cmd_reject(
        str(repo), "snapshot-section", "CLAUDE.md", "--section", STALE
    )
    assert json.loads(capsys.readouterr().out)["id"]


def test_an_out_of_range_occurrence_is_refused(tmp_path):
    """`CLAUDE.md` has exactly one `STALE` heading (occurrence 0). Asking for
    occurrence 7 must not silently address something that will never match —
    that is the exact ledger-rot the command's address resolution exists to
    prevent."""
    repo = _repo(tmp_path)
    with pytest.raises(config_sync.UnknownRejectionTargetError):
        config_sync.cmd_reject(
            str(repo),
            "snapshot-section",
            "CLAUDE.md",
            "--section",
            STALE,
            "--occurrence",
            "7",
        )


REPEATED_HEADING_DOCUMENT = "## Notes\n\nalpha\n\n## Notes\n\nbeta\n"


def _repo_with_repeated_heading(tmp_path):
    repo = tmp_path / "repo3"
    (repo / "consolidated").mkdir(parents=True)
    (repo / "consolidated" / "snapshot.json").write_text(
        json.dumps({"files": {"dup.md": REPEATED_HEADING_DOCUMENT}}), encoding="utf-8"
    )
    return repo


def test_rejecting_one_occurrence_of_a_repeated_heading_is_not_guarded(
    tmp_path, capsys
):
    """Rejecting occurrence 0 of a twice-repeated `## Notes` leaves occurrence
    1 ("beta") behind, so the file is not emptied and the guard must not
    fire. The recorded address must target occurrence 0 specifically."""
    repo = _repo_with_repeated_heading(tmp_path)
    config_sync.cmd_reject(
        str(repo),
        "snapshot-section",
        "dup.md",
        "--section",
        "## Notes",
        "--occurrence",
        "0",
    )
    payload = json.loads(capsys.readouterr().out)
    address = json.loads(payload["address"])
    assert address == {"file": "dup.md", "heading": "## Notes", "occurrence": 0}


def test_a_mistyped_option_is_refused(tmp_path):
    """`--scop` (missing the `e`) must not silently leave `scope` at its
    "network" default — a private rejection would then propagate to every
    machine with no sign anything went wrong."""
    repo = _repo(tmp_path)
    with pytest.raises(ValueError):
        config_sync.cmd_reject(
            str(repo), "snapshot-file", "rules/a.md", "--scop", "local"
        )
