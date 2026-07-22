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
    lowered = text.lower()
    assert "grouped change" in lowered or "group" in lowered, \
        "Phase 3 must let the human approve a group"
    assert "veto" in lowered and "separable" in lowered, \
        "Phase 3 must describe vetoing a separable rider"
    assert "primary's tier" in lowered or "tier of its primary" in lowered, \
        "Phase 3 must state a group is approved at its Primary's tier"
