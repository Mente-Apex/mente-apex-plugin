"""The SKILL must teach the commands the engine now exposes.

This repo already tests SKILL structure elsewhere; a documented command that
does not exist, or an existing command nobody documents, is the failure mode.
"""

import re
from pathlib import Path

import config_sync
import mutation_gate_prose

SKILL = Path(__file__).resolve().parents[1] / "skills" / "config-sync" / "SKILL.md"

# No leading `##`: `mutation_gate_prose._locate` wraps the marker in `\b`, and a
# `#` has no word boundary before it at the start of a line.
STEP_5 = "Step 5 — Commit the updated consolidated snapshot"


def test_every_new_command_is_documented():
    text = SKILL.read_text(encoding="utf-8")
    for command in ("reject", "rejections", "unreject", "resolve-rejection"):
        assert re.search(
            rf"(?<![\w-]){re.escape(command)}(?![\w-])", text
        ), f"{command} is not documented in SKILL.md"


def test_documented_commands_exist_in_the_engine():
    for command in ("reject", "rejections", "unreject", "resolve-rejection"):
        assert command in config_sync.COMMANDS


def test_the_summary_block_reports_rejections():
    assert "Rejected" in SKILL.read_text(encoding="utf-8")


def test_the_union_only_warning_no_longer_claims_deletions_are_impossible():
    text = SKILL.read_text(encoding="utf-8")
    assert "resurrected" in text
    assert "`reject`" in text


def test_step_5_stages_the_rejection_ledger():
    """`reject` and `resolve-rejection keep` run at Step 4, after Step 1 has
    already committed. Step 5 is therefore the only commit in the cycle that can
    carry `rejections/` — without it a `--scope network` rejection is written and
    then stranded as an uncommitted working-tree change, so it never reaches any
    other machine and the whole network scope is inert."""
    step_5 = mutation_gate_prose.extract_section(
        SKILL.read_text(encoding="utf-8"), STEP_5
    )
    # `in`, not `startswith`: the ledger directory is optional, so its staging is
    # guarded (`if [ -d rejections ]; then git add rejections/; fi`) and a
    # prefix match would miss the very line this test exists to require.
    staged = [line for line in step_5.splitlines() if "git add " in line]
    assert any(
        "rejections/" in line for line in staged
    ), "Step 5 stages no rejections/: " + repr(staged)
    assert any("consolidated/" in line for line in staged)
