"""Structural guard for the code-quality umbrella's group declaration.

Authored prose, not runtime code: assert the consolidated report format and the
consolidator role carry the group markers the shared gate+apply parse.
Dependency-free (no PyYAML), mirroring tests/test_clean_architecture_skill_structure.py.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CQ_DIR = REPO_ROOT / "skills" / "code-quality"


def read_cq(relative_path):
    """Read a file under skills/code-quality/, failing the test if absent."""
    target = CQ_DIR / relative_path
    assert target.is_file(), f"expected code-quality file missing: {target}"
    return target.read_text(encoding="utf-8")


def extract_section(text, heading_text):
    """Return the text between a Markdown heading containing heading_text and
    the next heading of the same-or-higher level (fewer or equal '#'s).

    Scopes an assertion to one section of a doc instead of the whole file, so a
    marker that only happens to reappear in a later section can't paper over
    its absence from the section under test.
    """
    heading_pattern = re.compile(r"^(#{1,6})\s.*" + re.escape(heading_text) + r".*$", re.MULTILINE)
    heading_match = heading_pattern.search(text)
    assert heading_match, f"heading containing {heading_text!r} not found"
    level = len(heading_match.group(1))
    section_start = heading_match.end()
    next_heading_pattern = re.compile(r"^#{1," + str(level) + r"}\s", re.MULTILINE)
    next_heading_match = next_heading_pattern.search(text, section_start)
    section_end = next_heading_match.start() if next_heading_match else len(text)
    return text[section_start:section_end]


def test_grouped_changes_banner_carries_group_id():
    text = read_cq("references/report-template.md")
    assert re.search(r"\[group-\d+\]", text), \
        "report-template.md Grouped changes banner must carry a [group-<n>] id"


def test_grouped_changes_apply_line_splits_rider_kinds():
    text = read_cq("references/report-template.md").lower()
    assert "subsumed" in text and "separable" in text, \
        "report-template.md must annotate riders subsumed vs separable"


def test_consolidator_emits_group_id_and_rider_split():
    text = read_cq("agents/consolidator.md")
    assert "group-" in text, "consolidator.md must instruct emitting a stable group-<n> id"
    lowered = text.lower()
    assert "subsumed" in lowered and "separable" in lowered, \
        "consolidator.md must instruct the subsumed/separable apply-instruction split"


def test_workflow_phase3_is_group_aware():
    text = (REPO_ROOT / "docs" / "refactor-workflow.md").read_text(encoding="utf-8")
    phase3 = extract_section(text, "Phase 3").lower()
    assert "grouped change" in phase3 or "group" in phase3, \
        "Phase 3 must let the human approve a group"
    assert "veto" in phase3 and "separable" in phase3, \
        "Phase 3 must describe vetoing a separable rider"
    assert "primary's tier" in phase3 or "tier of its primary" in phase3, \
        "Phase 3 must state a group is approved at its Primary's tier"


def test_workflow_phase4_group_is_one_job():
    text = (REPO_ROOT / "docs" / "refactor-workflow.md").read_text(encoding="utf-8")
    phase4 = extract_section(text, "Phase 4").lower()
    assert "one job" in phase4 and "group" in phase4, \
        "Phase 4 must map a declared group to one job"
    assert "ungrouped" in phase4, \
        "Phase 4 must retain the ungrouped (file-overlap) fallback"
    assert "separable" in phase4 and "revert" in phase4, \
        "Phase 4 must describe reverting a failed separable rider alone"


def test_implementer_has_group_apply_unit():
    text = (REPO_ROOT / "docs" / "refactor-agents" / "implementer.md").read_text(encoding="utf-8")
    assert "group" in text.lower(), "implementer must gain a group apply unit"
    assert "applied (via" in text, \
        "implementer must record subsumed riders as 'applied (via <primary>)'"


def test_workflow_states_the_detect_and_load_language_convention():
    text = (REPO_ROOT / "docs" / "refactor-workflow.md").read_text(encoding="utf-8")
    lowered = text.lower()
    # the convention that lets a new language be a new file, not a SKILL-body edit
    assert "references/<language>.md" in text, \
        "workflow must state the references/<language>.md convention"
    assert "references/<language>-<runner>.md" in text, \
        "workflow must state the apply-engine references/<language>-<runner>.md convention"
    assert "detected language" in lowered, \
        "Phase 0 must record the detected-language set that drives reference loading"
    assert "degrade" in lowered, \
        "convention must state graceful degradation when no reference matches"


def test_umbrella_passes_detected_language_set_to_analyzers():
    text = read_cq("SKILL.md").lower()
    assert "detected language" in text, \
        "umbrella must detect the language set once in Phase 0"
    assert "references/<language>.md" in read_cq("SKILL.md"), \
        "umbrella must hand each analyzer its references/<language>.md per the convention"


def test_umbrella_skill_prose_is_group_aware():
    text = read_cq("SKILL.md")
    lowered = text.lower()
    assert "group" in lowered, \
        "umbrella SKILL.md must mention grouped-change approval/apply"
    # the stale 'by tier or ID' phrasing must no longer be the only stated path
    assert "grouped change" in lowered or "as units" in lowered, \
        "umbrella SKILL.md must state groups are approved/applied as units"
