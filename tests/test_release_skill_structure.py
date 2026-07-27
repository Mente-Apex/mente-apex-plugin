"""Structural guard for the /release skill and the shared git-resolution doc.

Authored prose, not runtime code: assert files exist and carry the sections
the workflow depends on. Dependency-free (no PyYAML), matching the other
test_<skill>_skill_structure modules.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GIT_RESOLUTION_DOC = REPO_ROOT / "docs" / "git-remote-resolution.md"
SHIP_SKILL = REPO_ROOT / "skills" / "ship" / "SKILL.md"
RELEASE_SKILL_DIR = REPO_ROOT / "skills" / "release"
TARGETS_DIR = RELEASE_SKILL_DIR / "references" / "targets"
ADAPTER_CONTRACT = RELEASE_SKILL_DIR / "references" / "ADAPTER-CONTRACT.md"

# The abstraction the core workflow depends on. Order is the documented order.
CONTRACT_FIELDS = (
    "technology",
    "toolchain",
    "fingerprint",
    "version_source",
    "derived_manifests",
    "gate_command",
    "build_command",
    "artifact_pattern",
    "publish_command",
    "install_verify_command",
)


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


def test_shared_git_resolution_doc_exists_and_defines_both_variables():
    assert GIT_RESOLUTION_DOC.is_file(), "docs/git-remote-resolution.md must exist"
    text = GIT_RESOLUTION_DOC.read_text(encoding="utf-8")
    for heading in ("## Resolve the remote", "## Resolve the default branch"):
        assert heading in text, f"shared doc missing section: {heading}"
    # The four layers that make this worth sharing at all.
    for layer in ("symbolic-ref", "git remote show", "gh repo view", "main master"):
        assert layer in text.replace(
            "\n", " "
        ), f"shared doc lost fallback layer: {layer}"


def test_ship_links_the_shared_doc_instead_of_restating_it():
    text = SHIP_SKILL.read_text(encoding="utf-8")
    assert (
        "docs/git-remote-resolution.md" in text
    ), "/ship must link the shared resolution doc"
    # The duplication must not silently return: /ship no longer carries the
    # gh-repo-view fallback line itself.
    assert (
        "gh repo view --json defaultBranchRef" not in text
    ), "/ship still restates the resolution inline — it must link the shared doc"


def test_adapter_contract_documents_every_field():
    assert ADAPTER_CONTRACT.is_file(), "ADAPTER-CONTRACT.md must exist"
    text = ADAPTER_CONTRACT.read_text(encoding="utf-8")
    missing = [field for field in CONTRACT_FIELDS if f"`{field}`" not in text]
    assert not missing, f"contract does not document fields: {missing}"


def test_adapter_contract_declares_detection_precedence():
    text = ADAPTER_CONTRACT.read_text(encoding="utf-8")
    assert "## Detection" in text, "contract must declare the detection procedure"
    # Precedence is declared, not emergent from directory listing order.
    for technology in ("python", "typescript", "java"):
        assert technology in text, f"detection omits technology: {technology}"
    assert "status: stub" in text, "contract must define the stub marker"


def adapter_files():
    """Every adapter under references/targets/, recursively, sorted."""
    return sorted(TARGETS_DIR.rglob("*.md"))


def test_every_adapter_declares_all_contract_fields():
    adapters = adapter_files()
    assert adapters, "no adapters found under references/targets/"
    offenders = []
    for adapter in adapters:
        fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
        missing = [field for field in CONTRACT_FIELDS if field not in fields]
        if missing:
            offenders.append(f"{adapter.relative_to(REPO_ROOT)}: missing {missing}")
    assert not offenders, "adapters violate the contract:\n" + "\n".join(offenders)


def test_every_adapter_matches_its_location():
    """technology is the parent directory; toolchain is the filename stem."""
    offenders = []
    for adapter in adapter_files():
        fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
        if fields.get("technology") != adapter.parent.name:
            offenders.append(
                f"{adapter.relative_to(REPO_ROOT)}: technology "
                f"{fields.get('technology')!r} != directory {adapter.parent.name!r}"
            )
        if fields.get("toolchain") != adapter.stem:
            offenders.append(
                f"{adapter.relative_to(REPO_ROOT)}: toolchain "
                f"{fields.get('toolchain')!r} != filename {adapter.stem!r}"
            )
    assert not offenders, "adapter location mismatch:\n" + "\n".join(offenders)


def test_git_tag_only_adapter_stamps_all_three_version_mirrors():
    """This repo's own adapter must name every manifest the lockstep guard checks."""
    adapter = TARGETS_DIR / "python" / "git-tag-only.md"
    assert adapter.is_file(), "the dogfooded adapter must exist"
    text = adapter.read_text(encoding="utf-8")
    assert ".claude-plugin/plugin.json" in text, "canonical version source missing"
    for stamped in (".claude-plugin/marketplace.json", "pyproject.toml"):
        assert stamped in text, f"derived manifest not declared: {stamped}"
    fields = parse_frontmatter(text)
    assert fields.get("build_command") == "null", "a plugin builds no artifact"
    assert (
        fields.get("artifact_pattern") == "null"
    ), "no build means no artifact pattern"
    assert "status" not in fields, "the dogfooded adapter is not a stub"
