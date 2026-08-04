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

# No leading `##`, same reason as STEP_5 above. Hoisted here (rather than left
# by the test that first needed it) because two tests in this file now scope
# to this section.
STEP_4E_CONVERGENCE = "Step 4e — Answer other machines' rejections"

# SPEC's own heading for the paragraph this test protects. Scoping to it, not
# the whole file, matters here just as much as it does on the SKILL.md side:
# "provenance" also appears at spec line 208 ("no new provenance tracking", a
# ratchet-fix detail under "Enforcing it — three filter points") and "converge"
# also appears at spec line 111 ("converges without merge conflicts", a
# git-layout detail under "Two stores, one interface"). Both sit in different
# sections from "### Converging other machines", so scoping here is what keeps
# the assertions below from being satisfied by either of them by accident.
SPEC_CONVERGING_OTHER_MACHINES = "Converging other machines"


def test_the_convergence_limit_is_stated_rather_than_promised_away():
    """Phase 1 converged a network rejection only once no machine still carried
    the content, and phase 3's per-content provenance closed that gap -- SKILL.md's
    Step 4e callout now says so. That is not the same as unconditional convergence,
    though: a machine on an engine older than phase 3 has no provenance map, so it
    keeps resurrecting rejected content until it upgrades. Shipping documentation
    that dropped that caveat would promise behaviour a mixed fleet does not have.

    Both assertions below are scoped with `extract_section`, not a whole-file
    substring check: this test used to assert `"[Pp]hase 2"` and `"converge"`
    appear anywhere in either document, which kept passing after phase 3 shipped
    only because unrelated prose elsewhere in each file happened to contain the
    same words -- SKILL.md's rejection-*kind* split ("phase 2 adds the rest of
    what syncs") on one side, SPEC's git-layout and ratchet-fix asides
    ("converges without merge conflicts", "no new provenance tracking") on the
    other. A whole-file match satisfied by unrelated sentences is the same
    failure mode on both sides of this test; both needed the same discipline,
    not just the side that was first reported.

    SPEC is a frozen design record of phase 1's bounded-convergence decision,
    not living documentation the engine's current behaviour must match -- so
    the SPEC-side assertions still check only that the historical paragraph is
    still there, never anything about the shipped engine. Scoping to its
    enclosing section is what makes that check real rather than coincidental:
    see the module comment on SPEC_CONVERGING_OTHER_MACHINES for the two
    unrelated matches elsewhere in the file this excludes.
    """
    skill_section = mutation_gate_prose.extract_section(
        SKILL.read_text(encoding="utf-8"), STEP_4E_CONVERGENCE
    )
    assert "provenance" in skill_section, "Step 4e does not name the real fix"
    assert re.search(
        r"upgrade", skill_section
    ), "Step 4e drops the caveat that an unupgraded machine still resurrects"
    assert re.search(
        r"converge", skill_section.lower()
    ), "Step 4e does not state the convergence behaviour"

    spec_section = mutation_gate_prose.extract_section(
        SPEC.read_text(encoding="utf-8"), SPEC_CONVERGING_OTHER_MACHINES
    )
    assert "provenance" in spec_section, f"{SPEC.name} does not name the real fix"
    assert re.search(
        r"[Pp]hase 2", spec_section
    ), f"{SPEC.name} does not say where the fix lives"
    assert re.search(
        r"converge", spec_section
    ), f"{SPEC.name} does not state the convergence limit"


def test_step_4e_hands_the_operator_a_usable_rejection_id():
    """`resolve-rejection` keys on `id`, and the prompt names the rejecting
    machine and time. Documenting a bare address would leave the agent with no
    way to run the command it is told to run."""
    step_4e = mutation_gate_prose.extract_section(
        SKILL.read_text(encoding="utf-8"), "Step 4e"
    )
    for field in ("id", "machine_id", "rejected_at", "address", "scope"):
        assert field in step_4e, f"Step 4e never mentions {field}"


def test_step_4e_states_the_window_a_keep_has_to_be_answered_in():
    """`keep` revives from `machines/<id>.json` — this machine's last export —
    and consolidate is what republishes from it. Apply has already stripped a
    rejected section off local disk by the time the prompt appears, so once this
    machine exports again that last copy is overwritten and no answer recovers
    anything. Documenting `keep` as an escape hatch without its deadline offers
    an escape hatch that may already have closed.
    """
    step_4e = mutation_gate_prose.extract_section(
        SKILL.read_text(encoding="utf-8"), STEP_4E_CONVERGENCE
    )
    assert (
        "withheld" in step_4e
    ), "Step 4e never names the channel the report arrives on"
    assert (
        "machines/<machine-id>.json" in step_4e
    ), "Step 4e does not say what `keep` revives from"
    assert re.search(
        r"before this machine's next export", step_4e
    ), "Step 4e does not state the deadline"
    assert (
        "git history" in step_4e
    ), "Step 4e does not say what is left after the window"


def test_step_4e_documents_the_disk_asymmetry_between_rejection_kinds():
    """apply never deletes, so a whole-file rejection leaves this machine's copy
    on disk and its recovery window never closes. A section or settings-key
    rejection has its container file rewritten without the unit, so the content
    is gone from disk before the operator is asked. One sentence covering both
    ("the content named above is still on this machine's disk") was true for one
    kind and false for the other.
    """
    step_4e = mutation_gate_prose.extract_section(
        SKILL.read_text(encoding="utf-8"), STEP_4E_CONVERGENCE
    )
    assert "snapshot-file" in step_4e
    assert "snapshot-section" in step_4e
    assert "settings-key" in step_4e
    assert re.search(
        r"survives untouched", step_4e
    ), "Step 4e does not say a whole-file rejection leaves the local copy alone"
    assert re.search(
        r"off this machine's disk", step_4e
    ), "Step 4e does not say a section rejection has already rewritten the file"


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


def test_the_skill_documents_that_convergence_no_longer_needs_resolve_rejection():
    """Scoped to the section, not the whole file: a whole-file substring test
    passes even when the behaviour it describes is broken."""
    section = mutation_gate_prose.extract_section(
        SKILL.read_text(encoding="utf-8"), STEP_4E_CONVERGENCE
    )
    assert "resolve-rejection" in section
    assert "converge" in section.lower()


STEP_1 = "Step 1 — Scan for secrets, then export and push local state"


def test_step_1_surfaces_snapshot_warnings_not_only_marketplace_ones():
    """`SnapshotPropagator.export` routes provenance degradation through
    `ExportResult.warnings`, which `propagate-export` prints under the
    `snapshot` key. The runbook's extractor read only `marketplace`, so the new
    warnings landed as unremarked keys in a JSON dump — most of the way back to
    the silent fallback spec §9 exists to prevent."""
    step_1 = mutation_gate_prose.extract_section(
        SKILL.read_text(encoding="utf-8"), STEP_1
    )
    assert "'marketplace'" in step_1
    assert "'snapshot'" in step_1, "Step 1 never extracts the snapshot warnings"


def test_the_extracted_warning_keys_match_the_propagators_that_emit_them():
    """The extractor names propagators by their `name` attribute, which is what
    `cmd_propagate_export` keys the payload on. A rename on either side must not
    silently stop surfacing a warning."""
    import config_sync_propagators as propagators

    step_1 = mutation_gate_prose.extract_section(
        SKILL.read_text(encoding="utf-8"), STEP_1
    )
    assert f"'{propagators.SnapshotPropagator.name}'" in step_1


def test_step_3_tells_the_agent_to_relay_provenance_warnings():
    """`cmd_consolidate` prints `provenance_warnings` beside `rejected` and
    `withheld`. A warning nobody is told to read is not a warning."""
    step_3 = mutation_gate_prose.extract_section(
        SKILL.read_text(encoding="utf-8"), STEP_3
    )
    assert "provenance_warnings" in step_3


def test_step_3_describes_both_classes_of_provenance_warning():
    """`cmd_consolidate` emits two shapes on this channel: a malformed map,
    which names a machine and is fixed by re-exporting there, and an
    unattributable snapshot with no `machine_id`, which names no machine and is
    not fixed by re-exporting. A single "each line names a machine ... tell the
    user which machine to re-export" sentence is false for the second, and a
    doc asserting behaviour the engine does not have is this branch's own
    Critical finding in miniature."""
    step_3 = mutation_gate_prose.extract_section(
        SKILL.read_text(encoding="utf-8"), STEP_3
    )
    assert "machine_id" in step_3, "Step 3 never covers the unattributable class"
    assert re.search(
        r"names no machine", step_3
    ), "Step 3 still implies every warning names a machine"


def test_step_4e_does_not_claim_a_withheld_whole_file_was_already_rewritten():
    """`apply` never deletes, and a whole-file withholding leaves no key in the
    consolidated snapshot at all, so nothing rewrites the file — the local copy
    is untouched. The `remove` paragraph said the file "has already been
    rewritten without it" for every kind, contradicting the callout below it."""
    step_4e = mutation_gate_prose.extract_section(
        SKILL.read_text(encoding="utf-8"), STEP_4E_CONVERGENCE
    )
    remove_paragraph = step_4e.split("`keep` does not edit")[0]
    assert "snapshot-file" in remove_paragraph, "the `remove` text is not split by kind"
    assert re.search(
        r"untouched on disk", remove_paragraph
    ), "the `remove` text still claims a withheld whole file was rewritten"


def test_step_4e_says_the_rejecting_machine_is_not_prompted_either():
    """`SnapshotPropagator._report_withholdings` skips a record this machine
    authored. An operator on the rejecting machine would otherwise expect a
    prompt about their own network rejection and never see one."""
    step_4e = mutation_gate_prose.extract_section(
        SKILL.read_text(encoding="utf-8"), STEP_4E_CONVERGENCE
    )
    assert "unreject" in step_4e
    assert re.search(
        r"recorded the rejection|that ran `reject`", step_4e
    ), "Step 4e does not say the rejecting machine is not asked"
