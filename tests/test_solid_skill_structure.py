"""Structural guard for the SOLID skill.

Authored prose, not runtime code: assert each file exists and carries the
sections the orchestration and the plugin loader depend on. Dependency-free
(no PyYAML).
"""

import re
from pathlib import Path

from skill_version_policy import assert_version_at_least

REPO_ROOT = Path(__file__).resolve().parents[1]
SOLID_SKILL_DIR = REPO_ROOT / "skills" / "solid"


def read_skill_file(relative_path):
    """Read a file under skills/solid/, failing the test if absent."""
    target = SOLID_SKILL_DIR / relative_path
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


def test_skill_md_frontmatter_is_well_formed():
    fields = parse_frontmatter(read_skill_file("SKILL.md"))
    assert fields.get("name") == "solid"
    assert fields.get("user-invocable") == "true"
    frontmatter_text = read_skill_file("SKILL.md").split("---")[1]
    assert_version_at_least(frontmatter_text, (0, 1, 0))


def test_analyzer_agent_states_its_contract():
    analyzer = read_skill_file("agents/analyzer.md")
    assert "draft-findings.md" in analyzer
    assert "principles.md" in analyzer
