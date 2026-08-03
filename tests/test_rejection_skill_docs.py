"""The SKILL must teach the commands the engine now exposes.

This repo already tests SKILL structure elsewhere; a documented command that
does not exist, or an existing command nobody documents, is the failure mode.
"""

from pathlib import Path

import config_sync

SKILL = Path(__file__).resolve().parents[1] / "skills" / "config-sync" / "SKILL.md"


def test_every_new_command_is_documented():
    text = SKILL.read_text(encoding="utf-8")
    for command in ("reject", "rejections", "unreject", "resolve-rejection"):
        assert command in text, f"{command} is not documented in SKILL.md"


def test_documented_commands_exist_in_the_engine():
    for command in ("reject", "rejections", "unreject", "resolve-rejection"):
        assert command in config_sync.COMMANDS


def test_the_summary_block_reports_rejections():
    assert "Rejected" in SKILL.read_text(encoding="utf-8")


def test_the_union_only_warning_no_longer_claims_deletions_are_impossible():
    text = SKILL.read_text(encoding="utf-8")
    assert "resurrected" in text
    assert "`reject`" in text
