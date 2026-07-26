import config_sync
import pytest


def test_collect_scan_warnings_flags_secrets(claude_home):
    (claude_home / "CLAUDE.md").write_text("aws key AKIAIOSFODNN7EXAMPLE here\n")
    (claude_home / "rules").mkdir()
    (claude_home / "rules" / "ok.md").write_text("nothing secret here\n")

    warnings = config_sync._collect_scan_warnings()

    assert len(warnings) == 1
    assert warnings[0]["file"] == "CLAUDE.md"
    assert warnings[0]["line"] == 1


def test_scan_gate_exits_2_and_prints_when_dirty(claude_home, capsys):
    (claude_home / "CLAUDE.md").write_text("token: ghp_012345678901234567890123456789012345\n")

    with pytest.raises(SystemExit) as excinfo:
        config_sync.cmd_scan("--gate")

    assert excinfo.value.code == 2
    out = capsys.readouterr().out
    assert "CLAUDE.md:1" in out


def test_scan_gate_exits_0_when_clean(claude_home):
    (claude_home / "CLAUDE.md").write_text("all clean, nothing to see\n")

    with pytest.raises(SystemExit) as excinfo:
        config_sync.cmd_scan("--gate")

    assert excinfo.value.code == 0


def test_scan_json_mode_still_works(claude_home, capsys):
    (claude_home / "CLAUDE.md").write_text("clean\n")
    config_sync.cmd_scan()
    payload = config_sync.json.loads(capsys.readouterr().out)
    assert payload["clean"] is True
