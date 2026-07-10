"""Structural guard for the `ddd` skill.

The `ddd` skill is authored prose, not runtime code, so its "tests" assert that
each file exists and carries the sections/fields the orchestration and the
plugin loader depend on. Dependency-free on purpose: PyYAML is not installed, so
frontmatter is parsed with string ops only (same discipline as
test_skill_shell_safety.py).
"""
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DDD_SKILL_DIR = REPO_ROOT / "skills" / "ddd"


def read_skill_file(relative_path):
    """Read a file under skills/ddd/, returning its text (fails the test if absent)."""
    target = DDD_SKILL_DIR / relative_path
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
    assert fields.get("name") == "ddd"
    assert fields.get("user-invocable") == "true"
    # description is a block scalar; the key line is `description: >` or `>-`
    assert "description" in fields
    # version lives under metadata: — assert the literal line is present in body-adjacent frontmatter
    frontmatter_text = read_skill_file("SKILL.md").split("---")[1]
    assert re.search(r'version:\s*"0\.1\.0"', frontmatter_text), "metadata.version must be 0.1.0"


def test_skill_md_covers_both_modes_and_both_gates():
    body = parse_frontmatter(read_skill_file("SKILL.md"))["_body"]
    required_markers = [
        "design",            # design mode
        "analyze",           # analyze mode
        "MODELING GATE",     # design-mode hard gate
        "MODEL REVIEW GATE",  # analyze-mode keep/discard gate
        "docs/domain",       # durable model artifacts
        "ddd-reports",       # analyze report dir
        "programmatic",      # tdd handoff contract
    ]
    missing = [marker for marker in required_markers if marker not in body]
    assert not missing, f"SKILL.md missing required content: {missing}"
