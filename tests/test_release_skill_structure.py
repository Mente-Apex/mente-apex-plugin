"""Structural guard for the /release skill and the shared git-resolution doc.

Authored prose, not runtime code: assert files exist and carry the sections
the workflow depends on. Dependency-free (no PyYAML), matching the other
test_<skill>_skill_structure modules.
"""

import re
from pathlib import Path

from skill_version_policy import assert_version_at_least

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


_FRONTMATTER_KEY_VALUE = re.compile(r"^([A-Za-z0-9_-]+):\s?(.*)$")
_BLOCK_SCALAR_INDICATORS = (">", ">-", "|", "|-")


def parse_frontmatter(text):
    """Parse leading --- frontmatter into {key: value, '_body': rest}. No PyYAML.

    A key whose value is a block-scalar indicator (`>`, `>-`, `|`, `|-`) folds its
    indented continuation lines into the value, space-joined — this is the only
    multi-line shape this parser understands, matching the repo's house style for
    skill descriptions. Every other key (including a YAML list like
    `derived_manifests:` followed by `  - item` lines) is read as a single
    physical line, exactly as before; its continuation lines are simply not
    key: value lines and are skipped.
    """
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    assert match, "file does not start with a --- frontmatter block"
    raw_frontmatter, body = match.group(1), match.group(2)
    fields = {"_body": body}
    lines = raw_frontmatter.splitlines()
    index = 0
    while index < len(lines):
        key_value = _FRONTMATTER_KEY_VALUE.match(lines[index])
        if not key_value:
            index += 1
            continue
        key, value = key_value.group(1), key_value.group(2)
        index += 1
        if value.strip() in _BLOCK_SCALAR_INDICATORS:
            continuation_lines = []
            while (
                index < len(lines)
                and lines[index].strip()
                and not _FRONTMATTER_KEY_VALUE.match(lines[index])
            ):
                continuation_lines.append(lines[index].strip())
                index += 1
            fields[key] = " ".join(continuation_lines)
        else:
            fields[key] = value
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


def test_uv_adapter_verifies_a_real_artifact_pattern():
    """The wheel-name check is the whole point of artifact_pattern."""
    adapter = TARGETS_DIR / "python" / "uv.md"
    assert adapter.is_file(), "the uv adapter must exist"
    fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
    assert fields.get("build_command") == "uv build", "uv projects build with uv build"
    assert "dist/" in fields.get(
        "artifact_pattern", ""
    ), "artifact_pattern must name the real build output directory"
    assert fields.get("build_command") != "null", "a uv package target does build"


def test_no_adapter_recommends_a_forbidden_python_toolchain():
    """uv is canonical: pip/pipx/pyenv must never appear as an instruction."""
    offenders = []
    for adapter in adapter_files():
        fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
        if fields.get("technology") != "python":
            continue
        commands = " ".join(str(fields.get(field, "")) for field in CONTRACT_FIELDS)
        for forbidden in ("pip install", "pipx", "pyenv", "python -m build"):
            if forbidden in commands:
                offenders.append(f"{adapter.relative_to(REPO_ROOT)}: {forbidden}")
    assert not offenders, "adapters use forbidden Python tooling:\n" + "\n".join(
        offenders
    )


def test_three_technologies_are_represented():
    """The seam must be proven across a technology boundary, not just within one."""
    technologies = {adapter.parent.name for adapter in adapter_files()}
    assert {
        "python",
        "typescript",
        "java",
    } <= technologies, (
        f"expected python, typescript and java adapters; found {sorted(technologies)}"
    )


def test_stub_adapters_are_marked_and_working_ones_are_not():
    expected_stubs = {"typescript/npm", "java/maven"}
    expected_working = {"python/git-tag-only", "python/uv"}
    for adapter in adapter_files():
        identity = f"{adapter.parent.name}/{adapter.stem}"
        fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
        is_stub = fields.get("status") == "stub"
        if identity in expected_stubs:
            assert is_stub, f"{identity} must declare status: stub"
        elif identity in expected_working:
            assert not is_stub, f"{identity} is exercised and must not be a stub"


def test_fingerprints_within_a_technology_are_disjoint_or_ranked():
    """Two adapters in one technology may share a fingerprint only if the contract
    ranks them explicitly — otherwise a new adapter silently shadows an old one."""
    contract = ADAPTER_CONTRACT.read_text(encoding="utf-8")
    by_technology = {}
    for adapter in adapter_files():
        fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
        by_technology.setdefault(adapter.parent.name, []).append(
            (adapter.stem, fields.get("fingerprint"))
        )
    for technology, entries in by_technology.items():
        fingerprints = [fingerprint for _stem, fingerprint in entries]
        if len(fingerprints) == len(set(fingerprints)):
            continue
        for toolchain_name, _fingerprint in entries:
            assert f"`{toolchain_name}`" in contract, (
                f"{technology}/{toolchain_name} shares a fingerprint but the "
                "contract does not rank it"
            )


RELEASE_SKILL_MD = RELEASE_SKILL_DIR / "SKILL.md"

# Literals that would mean the core stopped being technology-agnostic.
TECHNOLOGY_LITERALS = (
    "uv build",
    "uv sync",
    "npm ci",
    "npm publish",
    "mvn ",
    "pyproject",
)


def strip_fenced_code_blocks(markdown_text):
    """Drop ``` fenced blocks so illustrative examples aren't read as instructions."""
    kept_lines = []
    inside_fence = False
    for line in markdown_text.splitlines():
        if line.lstrip().startswith("```"):
            inside_fence = not inside_fence
            continue
        if not inside_fence:
            kept_lines.append(line)
    return "\n".join(kept_lines)


def test_release_skill_declares_house_style_frontmatter():
    assert RELEASE_SKILL_MD.is_file(), "skills/release/SKILL.md must exist"
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8")
    fields = parse_frontmatter(text)
    assert fields.get("name") == "release"
    assert fields.get("user-invocable") == "true"
    assert fields.get("disable-model-invocation") == "true"
    assert "allowed-tools" in fields
    assert_version_at_least(text.split("---")[1], (0, 1, 0))


def test_release_description_disclaims_ship_territory():
    fields = parse_frontmatter(RELEASE_SKILL_MD.read_text(encoding="utf-8"))
    description = fields.get("description", "")
    for trigger in ("cut a release", "tag and publish", "/release"):
        assert trigger in description, f"description missing trigger: {trigger}"
    assert (
        "pull request" in description or "PR" in description
    ), "description must disclaim /ship's territory explicitly"


def test_core_workflow_contains_no_technology_specific_command():
    """The seam, enforced. Extending the core by editing it must fail CI."""
    body = strip_fenced_code_blocks(RELEASE_SKILL_MD.read_text(encoding="utf-8"))
    offenders = [literal for literal in TECHNOLOGY_LITERALS if literal in body]
    assert not offenders, (
        f"core SKILL.md names technology-specific commands {offenders} — "
        "these belong in references/targets/, not the core"
    )


def test_core_declares_every_hard_refusal():
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8").lower()
    for refusal in (
        "dirty",
        "default branch",
        "gate",
        "second",
        "artifact_pattern",
        "already exists",
        "stub",
    ):
        assert refusal in text, f"core does not document the refusal: {refusal}"


def test_core_links_the_shared_git_resolution():
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8")
    assert (
        "git-remote-resolution.md" in text
    ), "core must link the shared resolution rather than restating it"
    assert (
        "gh repo view --json defaultBranchRef" not in text
    ), "core restates the resolution inline — link the shared doc instead"
