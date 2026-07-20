"""Structural guard for the clean-code substrate.

clean-code is authored prose (a shared standard + a thin review skill), not
runtime code, so its "tests" assert each file exists and carries the
sections/links the ecosystem depends on. Dependency-free on purpose: PyYAML is
not installed, so frontmatter is parsed with string ops only (same discipline as
test_ddd_skill_structure.py).
"""
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CLEAN_CODE_SKILL_DIR = REPO_ROOT / "skills" / "clean-code"
CLEAN_CODE_STANDARD = REPO_ROOT / "docs" / "clean-code-standard.md"


def read_repo_file(relative_path):
    """Read a repo-relative file, failing the test if it is absent."""
    target = REPO_ROOT / relative_path
    assert target.is_file(), f"expected file missing: {target}"
    return target.read_text(encoding="utf-8")


def read_skill_file(relative_path):
    """Read a file under skills/clean-code/, failing the test if absent."""
    target = CLEAN_CODE_SKILL_DIR / relative_path
    assert target.is_file(), f"expected skill file missing: {target}"
    return target.read_text(encoding="utf-8")


def parse_frontmatter(text):
    """Parse leading --- frontmatter into {key: value, '_body': rest}. No PyYAML."""
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    assert match, "file does not start with a --- frontmatter block"
    raw_frontmatter, body = match.group(1), match.group(2)
    fields = {"_body": body}
    for line in raw_frontmatter.splitlines():
        key_value = re.match(r"^([A-Za-z0-9_-]+):\s?(.*)$", line)
        if key_value:
            fields[key_value.group(1)] = key_value.group(2)
    return fields


def test_standard_has_the_fifteen_principles_and_three_new_chapters():
    text = CLEAN_CODE_STANDARD.read_text(encoding="utf-8")
    lowered = text.lower()
    # the 15 ported leverage-ranked principle anchors
    ported_anchors = [
        "meaningful names",
        "single responsibility",
        "functions do one thing",
        "don't repeat yourself",
        "high cohesion",
        "command-query separation",
        "one level of abstraction",
        "flag argument",
        "never return null",
        "comments are a last resort",
        "law of demeter",
        "encapsulate conditionals",
        "clean tests",
        "consistent formatting",
        "boy scout rule",
    ]
    missing_ported = [anchor for anchor in ported_anchors if anchor not in lowered]
    assert not missing_ported, f"standard missing ported principles: {missing_ported}"
    # the three NEW chapters
    for new_chapter in ["Boundaries", "Simple Design", "Smells & Heuristics"]:
        assert new_chapter in text, f"standard missing new chapter: {new_chapter}"
    for new_marker in ["learning test", "runs all tests", "expresses intent"]:
        assert new_marker in lowered, f"standard missing new content: {new_marker}"
    # the meta-rule + severity rubric survive the move
    assert "meta-rule" in lowered
    for severity in ["High", "Medium", "Low"]:
        assert severity in text, f"standard missing severity level: {severity}"


def test_skill_md_is_thin_and_links_the_standard():
    fields = parse_frontmatter(read_skill_file("SKILL.md"))
    assert fields.get("name") == "clean-code"
    assert fields.get("user-invocable") == "true"
    frontmatter_text = read_skill_file("SKILL.md").split("---")[1]
    assert re.search(r'version:\s*"0\.2\.0"', frontmatter_text), "metadata.version must be 0.2.0"
    body = fields["_body"]
    lowered = body.lower()
    # links the single source of truth rather than restating it
    assert "docs/clean-code-standard.md" in body, "SKILL.md must link the canonical standard"
    # the two gears
    assert "quick" in lowered and "deep" in lowered, "SKILL.md must describe the two review gears"
    # defers structural findings up-ladder (non-overlap contract)
    for sibling in ["solid", "gof"]:
        assert sibling in lowered, f"SKILL.md must defer up-ladder to {sibling}"
    # the substrate framing
    assert "substrate" in lowered or "written by construction" in lowered or "by construction" in lowered


def test_deep_gear_agents_state_their_contracts():
    analyzer = read_skill_file("agents/analyzer.md")
    reviewer = read_skill_file("agents/reviewer.md")
    assert "read-only" in analyzer.lower()
    assert "findings-draft.md" in analyzer
    assert "clean-code-standard.md" in analyzer, "analyzer must judge against the standard"
    assert "report-template.md" in reviewer
    assert "clean-code-standard.md" in reviewer
    assert "verify" in reviewer.lower() and "prune" in reviewer.lower()
    assert "no code" in reviewer.lower() or "edit no code" in reviewer.lower()


def test_report_template_has_the_expected_structure():
    text = read_skill_file("references/report-template.md")
    for marker in ["[G1]", "Principle", "Severity", "High", "Medium", "Low", "Hand-offs"]:
        assert marker in text, f"report-template.md missing: {marker}"


def test_substrate_consumers_link_the_standard():
    implementer = read_repo_file("docs/refactor-agents/implementer.md")
    refactor_jobs = read_repo_file("skills/tdd/references/refactor-jobs.md")
    assert "clean-code-standard.md" in implementer, "implementer role must link the standard"
    assert "clean-code-standard.md" in refactor_jobs, "tdd refactor step must link the standard"
