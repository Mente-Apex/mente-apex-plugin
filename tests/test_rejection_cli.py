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


def _main_exit_code(monkeypatch, capsys, *argv):
    """Drive the real entry point and return its exit status.

    Nothing else in the suite drives `main()`, which is why its except tuple
    could omit `ValueError` unnoticed: every sibling test calls `cmd_*` directly
    and sees the exception, never the exit status an operator gets.
    """
    monkeypatch.setattr(config_sync.sys, "argv", ["config_sync.py", *argv])
    with pytest.raises(SystemExit) as exit_info:
        config_sync.main()
    return exit_info.value.code, capsys.readouterr().err


def test_a_phase_2_kind_exits_2_with_a_message_not_a_traceback(
    tmp_path, monkeypatch, capsys
):
    """`plugin` passes the `REJECTION_KINDS` check — phase 2 kinds are named
    there deliberately — and is then refused by `_resolve_rejection_address`
    with a bare `ValueError`. That is a refusal, so it must exit 2 like every
    other refusal, not 1 with a stack trace."""
    repo = _repo(tmp_path)
    code, stderr = _main_exit_code(
        monkeypatch, capsys, "reject", str(repo), "plugin", "foo@bar"
    )
    assert code == 2
    assert "phase 1" in stderr


def test_a_missing_subject_exits_2_rather_than_raising_indexerror(
    tmp_path, monkeypatch, capsys
):
    """`reject` is variadic, so the arity check in `main` does not run and a
    missing subject reaches `args[1]`."""
    repo = _repo(tmp_path)
    code, stderr = _main_exit_code(
        monkeypatch, capsys, "reject", str(repo), "snapshot-file"
    )
    assert code == 2
    assert stderr.startswith("Error: ")


def test_a_non_numeric_occurrence_exits_2(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path)
    code, stderr = _main_exit_code(
        monkeypatch,
        capsys,
        "reject",
        str(repo),
        "snapshot-section",
        "CLAUDE.md",
        "--section",
        STALE,
        "--occurrence",
        "second",
    )
    assert code == 2
    assert stderr.startswith("Error: ")


def test_a_working_command_still_exits_0_through_main(tmp_path, monkeypatch, capsys):
    """The refusal path must not swallow success: `main` returns normally when
    nothing raised, so the operator's shell sees 0."""
    repo = _repo(tmp_path)
    monkeypatch.setattr(
        config_sync.sys, "argv", ["config_sync.py", "rejections", str(repo)]
    )
    config_sync.main()
    assert json.loads(capsys.readouterr().out) == {"rejections": []}


def test_a_mistyped_option_is_refused(tmp_path):
    """`--scop` (missing the `e`) must not silently leave `scope` at its
    "network" default — a private rejection would then propagate to every
    machine with no sign anything went wrong."""
    repo = _repo(tmp_path)
    with pytest.raises(ValueError):
        config_sync.cmd_reject(
            str(repo), "snapshot-file", "rules/a.md", "--scop", "local"
        )


def test_a_flag_shaped_option_value_is_a_value_not_an_option(tmp_path, capsys):
    """A reason may legitimately start with `--`. Scanning every token for a
    leading `--` refused it as an unknown option, leaving the operator no way to
    pass a perfectly ordinary string. Only a token in flag position is a flag."""
    repo = _repo(tmp_path)
    config_sync.cmd_reject(
        str(repo), "snapshot-file", "rules/a.md", "--reason", "--needs-follow-up"
    )
    assert json.loads(capsys.readouterr().out)["reason"] == "--needs-follow-up"


def test_an_option_missing_its_value_is_refused(tmp_path):
    """A trailing `--scope` with nothing after it must not fall through to the
    "network" default — the same silent-propagation failure `--scop` has."""
    repo = _repo(tmp_path)
    with pytest.raises(ValueError):
        config_sync.cmd_reject(str(repo), "snapshot-file", "rules/a.md", "--scope")


def test_a_stray_positional_after_the_subject_is_refused(tmp_path):
    """Previously ignored, because only `--`-prefixed tokens were checked. A
    token the command cannot account for means the operator meant something the
    command is not doing."""
    repo = _repo(tmp_path)
    with pytest.raises(ValueError):
        config_sync.cmd_reject(str(repo), "snapshot-file", "rules/a.md", "local")
