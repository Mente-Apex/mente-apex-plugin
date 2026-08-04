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


SPEC = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-08-03-config-sync-rejection-ledger-design.md"
)


def test_the_convergence_limit_is_stated_rather_than_promised_away():
    """Phase 1 converges a network rejection only once no machine still carries
    the content: every machine exports before anyone consolidates, and an export
    is stamped "now", so an unchanged re-export is indistinguishable from a
    deliberate re-add. Shipping documentation that promised unconditional
    convergence would promise behaviour the engine does not have."""
    for document in (SKILL, SPEC):
        text = document.read_text(encoding="utf-8")
        assert "provenance" in text, f"{document.name} does not name the real fix"
        assert re.search(
            r"[Pp]hase 2", text
        ), f"{document.name} does not say where the fix lives"
        assert re.search(
            r"converge", text
        ), f"{document.name} does not state the convergence limit"


def test_step_4e_hands_the_operator_a_usable_rejection_id():
    """`resolve-rejection` keys on `id`, and the prompt names the rejecting
    machine and time. Documenting a bare address would leave the agent with no
    way to run the command it is told to run."""
    step_4e = mutation_gate_prose.extract_section(
        SKILL.read_text(encoding="utf-8"), "Step 4e"
    )
    for field in ("id", "machine_id", "rejected_at", "address", "scope"):
        assert field in step_4e, f"Step 4e never mentions {field}"


def test_every_phase_2_kind_is_documented():
    text = SKILL.read_text(encoding="utf-8")
    for kind in ("settings-key", "plugin", "hook-registration"):
        assert kind in text, f"{kind} is not documented in SKILL.md"


def test_the_hook_addressing_options_are_documented():
    text = SKILL.read_text(encoding="utf-8")
    for option in ("--event", "--matcher", "--key"):
        assert option in text, f"{option} is not documented in SKILL.md"


STEP_3 = "Step 3 — Consolidate all machine snapshots"


def test_the_force_guard_on_whole_file_rejection_is_documented():
    """`cmd_reject` refuses `snapshot-file` on every name in `SNAPSHOT_FILES`
    unless `--force` is passed (`MassRejectionRefusedError`). An operator who
    hits that refusal with nothing in the docs explaining it has no way to
    know `--force` is the escape hatch."""
    step_3 = mutation_gate_prose.extract_section(
        SKILL.read_text(encoding="utf-8"), STEP_3
    )
    assert "--force" in step_3
    for synced_file in config_sync.SNAPSHOT_FILES:
        assert synced_file in step_3, f"{synced_file} not named near the --force guard"


def test_the_scope_asymmetry_between_writers_is_documented():
    """`network_rejection_policy` (used by `cmd_consolidate`, a shared-state
    writer) checks network scope only; `local_rejection_policy` (used by the
    local-state writers) checks both. The docs must say *why*, not just name
    the scopes: a local veto reaching shared state would impose one machine's
    taste on the whole network."""
    step_4 = mutation_gate_prose.extract_section(
        SKILL.read_text(encoding="utf-8"),
        "Step 4 — Backup, then apply through the propagator seam",
    )
    assert re.search(r"network[- ]only", step_4)
    assert "impose" in step_4


def test_the_documented_kinds_match_the_engine():
    import config_sync_rejections as rejections

    text = SKILL.read_text(encoding="utf-8")
    for kind in rejections.REJECTION_KINDS:
        assert kind in text, f"{kind} is advertised by the engine but undocumented"


def test_the_skill_says_rejection_does_not_delete_an_existing_hook():
    text = SKILL.read_text(encoding="utf-8")
    assert "hooks-prune" in text


STEP_4E_CONVERGENCE = "Step 4e — Answer other machines' rejections"


def test_the_skill_documents_that_convergence_no_longer_needs_resolve_rejection():
    """Scoped to the section, not the whole file: a whole-file substring test
    passes even when the behaviour it describes is broken."""
    section = mutation_gate_prose.extract_section(
        SKILL.read_text(encoding="utf-8"), STEP_4E_CONVERGENCE
    )
    assert "resolve-rejection" in section
    assert "converge" in section.lower()
