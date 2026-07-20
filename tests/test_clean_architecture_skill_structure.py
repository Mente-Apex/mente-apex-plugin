"""Structural guard for the clean-architecture lens and the shared overlap hub.

Authored prose, not runtime code: assert files exist and carry the sections the
orchestration and the plugin loader depend on. Dependency-free (no PyYAML).
"""
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CA_SKILL_DIR = REPO_ROOT / "skills" / "clean-architecture"
LENS_OVERLAP = REPO_ROOT / "docs" / "lens-overlap.md"


def read_skill_file(relative_path):
    """Read a file under skills/clean-architecture/, failing the test if absent."""
    target = CA_SKILL_DIR / relative_path
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


def test_lens_overlap_hub_replaces_pairwise_map():
    assert LENS_OVERLAP.is_file(), "docs/lens-overlap.md must exist"
    assert not (REPO_ROOT / "docs" / "solid-gof-overlap.md").exists(), \
        "docs/solid-gof-overlap.md must be gone (migrated to lens-overlap.md)"
    text = LENS_OVERLAP.read_text(encoding="utf-8")
    # the hub adds clean-architecture as a participating lens
    assert "clean-architecture" in text.lower(), "hub must carry clean-architecture rows"
    # the SOLID<->GoF content survives the move (spot-check canonical entries)
    for kept in ["Strategy", "Singleton", "Abstract Factory", "DIP"]:
        assert kept in text, f"hub lost SOLID/GoF content: {kept}"


def test_no_stale_overlap_references_remain():
    offenders = []
    scan_dirs = ["skills/solid", "skills/gof", "docs/refactor-workflow.md",
                 "docs/refactor-agents", "README.md", "tests/test_skill_integrity.py"]
    for scan in scan_dirs:
        target = REPO_ROOT / scan
        files = target.rglob("*") if target.is_dir() else [target]
        for candidate in files:
            if candidate.is_file() and candidate.suffix in {".md", ".py"}:
                if "solid-gof-overlap" in candidate.read_text(encoding="utf-8"):
                    offenders.append(str(candidate.relative_to(REPO_ROOT)))
    assert not offenders, f"stale solid-gof-overlap references remain: {offenders}"
