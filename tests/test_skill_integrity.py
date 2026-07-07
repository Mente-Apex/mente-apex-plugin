"""Static structural guards for the plugin's skills, shared docs, and manifests.

No engine import: these are pure file checks. They protect the refactor
ecosystem's shared-docs architecture (a skill pointing at
docs/refactor-workflow.md must not dangle) and keep the three version mirrors
in lockstep. Narrative docs under docs/superpowers/ (plans, specs) are out of
scope — they carry intentional forward-references and fenced example links.
"""
import json
import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
DOCS_DIR = REPO_ROOT / "docs"
PLUGIN_JSON = REPO_ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE_JSON = REPO_ROOT / ".claude-plugin" / "marketplace.json"
PYPROJECT = REPO_ROOT / "pyproject.toml"

REQUIRED_FRONTMATTER_KEYS = ("name", "description")

GOF_PATTERNS = [
    "Abstract Factory", "Builder", "Factory Method", "Prototype", "Singleton",
    "Adapter", "Bridge", "Composite", "Decorator", "Facade", "Flyweight", "Proxy",
    "Chain of Responsibility", "Command", "Interpreter", "Iterator", "Mediator",
    "Memento", "Observer", "State", "Strategy", "Template Method", "Visitor",
]

# The cross-references this guard protects: the refactor ecosystem's skills and
# shared docs. Files created by later tasks simply don't match yet.
INTEGRITY_SCAN_GLOBS = (
    "skills/gof/**/*.md",
    "skills/solid/**/*.md",
    "skills/tdd/**/*.md",
    "docs/refactor-workflow.md",
    "docs/refactor-agents/*.md",
    "docs/solid-gof-overlap.md",
    "docs/git-convention.md",
)

MARKDOWN_LINK = re.compile(r"\]\(([^)]+)\)")


def _parse_frontmatter(markdown_text):
    """Return the raw YAML frontmatter between the first two '---' fences, or None."""
    if not markdown_text.startswith("---"):
        return None
    fence_end = markdown_text.find("\n---", 3)
    if fence_end == -1:
        return None
    return markdown_text[3:fence_end]


def _integrity_scan_files():
    """Existing Markdown files whose links this guard resolves (dedup, sorted)."""
    matched = set()
    for glob_pattern in INTEGRITY_SCAN_GLOBS:
        for markdown_file in REPO_ROOT.glob(glob_pattern):
            if markdown_file.is_file():
                matched.add(markdown_file)
    return sorted(matched)


def _strip_fenced_code_blocks(markdown_text):
    """Drop ``` fenced blocks so example links inside them aren't treated as live pointers."""
    kept_lines = []
    inside_fence = False
    for line in markdown_text.splitlines():
        if line.lstrip().startswith("```"):
            inside_fence = not inside_fence
            continue
        if not inside_fence:
            kept_lines.append(line)
    return "\n".join(kept_lines)


def _relative_link_targets(markdown_text):
    """Yield each relative markdown-link target (fenced blocks stripped, anchors removed, URLs skipped)."""
    for raw_target in MARKDOWN_LINK.findall(_strip_fenced_code_blocks(markdown_text)):
        target = raw_target.split("#", 1)[0].strip()
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        yield target


def test_every_skill_has_required_frontmatter():
    offenders = []
    for skill_file in sorted(SKILLS_DIR.rglob("SKILL.md")):
        frontmatter = _parse_frontmatter(skill_file.read_text())
        if frontmatter is None:
            offenders.append(f"{skill_file.relative_to(REPO_ROOT)}: no frontmatter")
            continue
        for required_key in REQUIRED_FRONTMATTER_KEYS:
            if not re.search(rf"^{required_key}:", frontmatter, re.MULTILINE):
                offenders.append(f"{skill_file.relative_to(REPO_ROOT)}: missing '{required_key}'")
    assert not offenders, "Frontmatter problems:\n" + "\n".join(offenders)


def test_relative_markdown_links_resolve():
    offenders = []
    for markdown_file in _integrity_scan_files():
        for target in _relative_link_targets(markdown_file.read_text()):
            resolved = (markdown_file.parent / target).resolve()
            if not resolved.exists():
                offenders.append(f"{markdown_file.relative_to(REPO_ROOT)} -> {target}")
    assert not offenders, "Dangling relative markdown links:\n" + "\n".join(offenders)


def test_version_mirrors_match():
    plugin_version = json.loads(PLUGIN_JSON.read_text())["version"]
    pyproject_version = tomllib.loads(PYPROJECT.read_text())["project"]["version"]
    marketplace_version = json.loads(MARKETPLACE_JSON.read_text())["plugins"][0]["version"]
    assert plugin_version == pyproject_version == marketplace_version, (
        f"version drift — plugin.json={plugin_version} "
        f"pyproject={pyproject_version} marketplace={marketplace_version}"
    )
