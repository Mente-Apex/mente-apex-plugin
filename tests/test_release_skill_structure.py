"""Structural guard for the /release skill and the shared git-resolution doc.

Authored prose, not runtime code: assert files exist and carry the sections
the workflow depends on. Dependency-free (no PyYAML), matching the other
test_<skill>_skill_structure modules.
"""

import json
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
    "tag_pattern",
    "publish_command",
    "release_command",
    "install_verify_command",
    "distribution_names",
)

# The closed placeholder vocabulary. A command may contain these and nothing
# else: an unbound token is a value the running agent has to guess at, which is
# the class of error `artifact_pattern` exists to prevent (#98).
#
# `<distribution-name:role>` is bound per adapter, by the roles that adapter's
# `distribution_names` map declares — which is also what makes a null map with a
# name-using command a failure rather than a silent omission.
#
# `<tag>` is the expansion of this adapter's own `tag_pattern`, computed once the
# version settles. It exists so that `release_command` can name the tag without
# either re-encoding the convention or forcing the core to know it (#96, #97).
#
# `<release-notes-file>` is a path the core writes the grouped Conventional
# Commit notes to. A path rather than the notes themselves: release notes are
# multi-line and contain quotes and backticks, and inlining them into a command
# string makes every adapter responsible for shell quoting.
UNPARAMETERISED_PLACEHOLDERS = (
    "<remote>",
    "<default>",
    "<version>",
    "<tag>",
    "<release-notes-file>",
)
DISTRIBUTION_NAME_PREFIX = "<distribution-name:"

# Every adapter must be classified. This mapping is the classification — a new
# adapter absent from it fails `test_every_adapter_is_classified_exactly_once`
# rather than being silently skipped (#101.1).
ADAPTER_CLASSIFICATIONS = {
    "python/git-tag-only": "working",
    "python/uv": "working",
    "typescript/npm": "stub",
    "java/maven": "stub",
}


_FRONTMATTER_KEY_VALUE = re.compile(r"^([A-Za-z0-9_-]+):\s?(.*)$")
_BLOCK_SCALAR_INDICATORS = (">", ">-", "|", "|-")


def _strip_list_marker(line):
    """`- item` → `item`; anything else unchanged."""
    return line[2:].lstrip() if line.startswith("- ") else line


def parse_frontmatter(text):
    """Parse leading --- frontmatter into {key: value, '_body': rest}. No PyYAML.

    Two multi-line shapes fold into a space-joined value:

    - a block scalar (`>`, `>-`, `|`, `|-`), matching the repo's house style for
      skill descriptions;
    - a YAML list — an empty value followed by indented `- item` lines, which is
      how `derived_manifests` is written. Folding these matters because every
      field-value scan built on this parser (the forbidden-toolchain check, the
      placeholder check) would otherwise be blind to anything inside a list.

    Item text is folded without its `- ` marker. Any other continuation line is
    skipped, as before.
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
        if value.strip() in _BLOCK_SCALAR_INDICATORS or value.strip() == "":
            continuation_lines = []
            while (
                index < len(lines)
                and lines[index].strip()
                and not _FRONTMATTER_KEY_VALUE.match(lines[index])
            ):
                continuation_lines.append(_strip_list_marker(lines[index].strip()))
                index += 1
            fields[key] = " ".join(continuation_lines)
        else:
            fields[key] = value
    return fields


# Deliberately permissive: match ANY angle-bracket token, then subtract the bound
# set. The inverse — matching only well-formed tokens — fails open, because
# `<TOOL_NAME>` or `<gemName>` simply would not match and would be read as "not a
# placeholder at all" rather than as an unbound one.
_PLACEHOLDER_TOKEN = re.compile(r"<[^<>\s][^<>]{0,60}>")

# A role key inside `distribution_names:` once the frontmatter parser has folded
# the nested mapping to a single space-joined line.
_ROLE_DECLARATION = re.compile(r"([a-z][a-z0-9_-]*):\s*(\S+)")


# ── Policy helpers ────────────────────────────────────────────────────────────
# Each rule below is a pure function of plain data, deliberately separated from
# the filesystem read. The disk is the substitutable detail; the invariant is the
# policy. Filesystem-backed tests feed these the four real adapters, while
# table-driven tests feed them synthetic ones — which is the only way to exercise
# a rule (fingerprint collision) that today's adapters never trigger (#101.2).


def declared_roles(distribution_names_value):
    """Role keys declared by a `distribution_names` map, as the parser folds it."""
    value = (distribution_names_value or "").strip()
    if not value or value == "null":
        return set()
    return {role for role, _selector in _ROLE_DECLARATION.findall(value)}


def unbound_placeholders(field_values, roles=frozenset()):
    """Placeholder tokens in the values that the contract does not bind.

    `roles` are this adapter's declared `distribution_names` keys; only those
    make the matching `<distribution-name:role>` token bound. That is what makes
    a null map beside a name-using command a failure rather than an omission.
    """
    bound = set(UNPARAMETERISED_PLACEHOLDERS)
    bound.update(f"{DISTRIBUTION_NAME_PREFIX}{role}>" for role in roles)
    used_tokens = set()
    for value in field_values:
        used_tokens.update(_PLACEHOLDER_TOKEN.findall(str(value)))
    return sorted(used_tokens - bound)


def level_two_rows(contract_text):
    """(technology, toolchain) pairs from the Level 2 detection table, in order.

    Precedence is *position* in this table — "first match wins" — so membership
    plus order is what ranks two adapters. The previous rule asked whether the
    toolchain name appeared backticked anywhere in the document, which every
    correctly-registered adapter satisfies by construction, so it could never
    fire (#101.2, reopened in review).
    """
    section = _section_after(contract_text, "### Level 2")
    rows = []
    for line in section.splitlines():
        cells = [cell.strip().strip("`") for cell in line.split("|")[1:-1]]
        if len(cells) != 3:
            continue
        technology, _fingerprint, toolchain = cells
        if technology in ("", "Technology") or set(technology) <= {"-"}:
            continue
        rows.append((technology, toolchain))
    return rows


def _section_after(text, heading):
    """The text from `heading` up to the next heading of the same or higher level.

    Scoping matters: the eleven-field table is also three columns wide, so an
    unscoped scan reads `| technology | … | no |` as a detection row.
    """
    start = text.index(heading)
    depth = len(heading) - len(heading.lstrip("#"))
    remainder = text[start + len(heading) :]
    for line_offset, line in enumerate(remainder.splitlines()):
        stripped = line.lstrip("#")
        level = len(line) - len(stripped)
        if line.startswith("#") and 0 < level <= depth:
            return "\n".join(remainder.splitlines()[:line_offset])
    return remainder


def unranked_shared_fingerprints(entries, ranked_toolchains):
    """Toolchains in one technology sharing a fingerprint without being ranked.

    `entries` is a list of (toolchain, fingerprint) pairs for one technology;
    `ranked_toolchains` is that technology's Level 2 rows in table order. A
    colliding toolchain absent from the table has no declared precedence, so it
    silently shadows its twin or is shadowed by it.
    """
    fingerprints = [fingerprint for _toolchain, fingerprint in entries]
    duplicated = {
        fingerprint
        for fingerprint in fingerprints
        if fingerprints.count(fingerprint) > 1
    }
    return sorted(
        toolchain
        for toolchain, fingerprint in entries
        if fingerprint in duplicated and toolchain not in ranked_toolchains
    )


def classification_gaps(identities, classifications):
    """(unclassified, stale) — adapters on disk with no classification, and
    classifications naming an adapter that no longer exists."""
    unclassified = sorted(set(identities) - set(classifications))
    stale = sorted(set(classifications) - set(identities))
    return unclassified, stale


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


def test_every_adapter_declares_a_non_null_tag_pattern():
    """`tag_pattern` has no null case: every target creates a tag.

    The tag is the one artifact this workflow always produces — a `null`
    `build_command` or `release_command` is a real target shape, but a release
    with no tag is not a release. A null here would be an unfilled field wearing
    a contract value's clothes.
    """
    offenders = []
    for adapter in adapter_files():
        fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
        value = (fields.get("tag_pattern") or "").strip()
        if not value or value == "null":
            offenders.append(f"{adapter.relative_to(REPO_ROOT)}: {value or '(absent)'}")
    assert not offenders, "adapters declare no tag_pattern:\n" + "\n".join(offenders)


def test_no_tag_pattern_references_the_tag_it_defines():
    """`tag_pattern` is what `<tag>` expands *to* — it cannot contain `<tag>`.

    Nothing else in the placeholder vocabulary is self-referential, so the
    substitution loop has no cycle detection and would not acquire any: this is
    the one field that could introduce one.
    """
    offenders = [
        str(adapter.relative_to(REPO_ROOT))
        for adapter in adapter_files()
        if "<tag>"
        in str(
            parse_frontmatter(adapter.read_text(encoding="utf-8")).get("tag_pattern")
        )
    ]
    assert not offenders, f"tag_pattern is self-referential in: {offenders}"


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


def test_parse_frontmatter_folds_multi_line_lists():
    """`derived_manifests:` + indented `- item` lines previously captured as ''.

    That blinded every field-value scan to anything written as a list — including
    the forbidden-toolchain check below (#101.3).
    """
    parsed = parse_frontmatter(
        "---\n"
        "derived_manifests:\n"
        "  - one.toml#project.version\n"
        "  - two.json#.plugins[0].version\n"
        "toolchain: uv\n"
        "---\n"
        "body\n"
    )
    assert parsed["derived_manifests"] == (
        "one.toml#project.version two.json#.plugins[0].version"
    )
    # The key after the list must still parse — folding must not swallow it.
    assert parsed["toolchain"] == "uv"
    assert parsed["_body"] == "body\n"


def test_forbidden_toolchain_hidden_in_a_list_is_visible_to_the_scan():
    """The consequence of the fix above, pinned directly."""
    parsed = parse_frontmatter(
        "---\nderived_manifests:\n  - pip install something\n---\n\n"
    )
    assert "pip install" in parsed["derived_manifests"]


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


def adapter_identities():
    return [f"{adapter.parent.name}/{adapter.stem}" for adapter in adapter_files()]


def test_every_adapter_is_classified_exactly_once():
    """Fail-closed: an adapter nobody classified is an adapter nobody verified.

    The previous shape checked membership via if/elif against two hardcoded sets,
    so an adapter in neither set had no assertion run against it at all — the
    guard that exists to stop an unverified adapter from driving a real release
    could not see adapters it was not told about (#101.1).
    """
    unclassified, stale = classification_gaps(
        adapter_identities(), ADAPTER_CLASSIFICATIONS
    )
    assert not unclassified, (
        f"adapters are not classified as stub-or-working: {unclassified} — "
        "add them to ADAPTER_CLASSIFICATIONS"
    )
    assert not stale, f"ADAPTER_CLASSIFICATIONS names missing adapters: {stale}"


def test_stub_adapters_are_marked_and_working_ones_are_not():
    offenders = []
    for adapter in adapter_files():
        identity = f"{adapter.parent.name}/{adapter.stem}"
        fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
        is_stub = fields.get("status") == "stub"
        expected_stub = ADAPTER_CLASSIFICATIONS[identity] == "stub"
        if is_stub != expected_stub:
            offenders.append(
                f"{identity}: classified {ADAPTER_CLASSIFICATIONS[identity]!r} "
                f"but status: stub is {'present' if is_stub else 'absent'}"
            )
    assert not offenders, "stub markers disagree with classification:\n" + "\n".join(
        offenders
    )


def adapters_by_technology():
    by_technology = {}
    for adapter in adapter_files():
        fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
        by_technology.setdefault(adapter.parent.name, []).append(
            (adapter.stem, fields.get("fingerprint"))
        )
    return by_technology


def test_every_adapter_is_registered_in_the_level_two_table():
    """An adapter absent from the detection table is unreachable.

    The contract warns about this in "Adding an adapter" step 4 — detection
    resolves technology first, so an unregistered adapter sits on disk while the
    run refuses with "nothing matches". Nothing checked it until now, and it is
    the invariant the collision rule below actually depends on.
    """
    rows = level_two_rows(ADAPTER_CONTRACT.read_text(encoding="utf-8"))
    missing = [
        f"{technology}/{toolchain}"
        for technology, entries in adapters_by_technology().items()
        for toolchain, _fingerprint in entries
        if (technology, toolchain) not in rows
    ]
    assert not missing, f"adapters missing a Level 2 detection row: {missing}"


def test_fingerprints_within_a_technology_are_disjoint_or_ranked():
    """The real adapters, checked against the same rule the table-driven test pins."""
    rows = level_two_rows(ADAPTER_CONTRACT.read_text(encoding="utf-8"))
    offenders = []
    for technology, entries in adapters_by_technology().items():
        ranked = [
            toolchain
            for row_technology, toolchain in rows
            if row_technology == technology
        ]
        offenders += [
            f"{technology}/{toolchain}"
            for toolchain in unranked_shared_fingerprints(entries, ranked)
        ]
    assert (
        not offenders
    ), f"adapters share a fingerprint the contract does not rank: {offenders}"


def test_fingerprint_ranking_rule_catches_a_synthetic_collision():
    """Today no two adapters collide, so the guard above never executes its
    failure branch. This exercises the rule directly with synthetic pairs so it
    cannot rot unnoticed (#101.2)."""
    colliding = [("uv", "pyproject.toml"), ("poetry", "pyproject.toml")]

    # Neither toolchain has a detection row → neither has declared precedence.
    assert unranked_shared_fingerprints(colliding, []) == ["poetry", "uv"]

    # Both rowed, so the table's order ranks them → the collision is deliberate.
    assert unranked_shared_fingerprints(colliding, ["uv", "poetry"]) == []

    # Only one rowed → the unrowed one silently shadows or is shadowed.
    assert unranked_shared_fingerprints(colliding, ["uv"]) == ["poetry"]

    # Disjoint fingerprints are never offenders, rowed or not.
    disjoint = [("uv", "uv.lock"), ("git-tag-only", "plugin.json")]
    assert unranked_shared_fingerprints(disjoint, []) == []


def test_level_two_rows_are_parsed_from_the_real_contract():
    """The rule above is only as good as this parse — pin it against the real file."""
    rows = level_two_rows(ADAPTER_CONTRACT.read_text(encoding="utf-8"))
    assert ("python", "git-tag-only") in rows and ("python", "uv") in rows
    # Order is precedence: git-tag-only must precede uv (this repo matches both).
    python_order = [
        toolchain for technology, toolchain in rows if technology == "python"
    ]
    assert python_order.index("git-tag-only") < python_order.index("uv")


def test_every_placeholder_used_by_an_adapter_is_bound_by_the_contract():
    """A token the contract does not bind is a value the agent has to guess.

    `python/uv` is a working, non-stub adapter, so this bit a real release path:
    `<tool-name>` and `<version>` were both used and neither was bound (#98).

    Because a `<distribution-name:role>` token is bound only by a role the
    adapter declares, this also enforces the contract's `null`-iff rule: a null
    `distribution_names` beside a name-using command leaves the token unbound.
    """
    offenders = []
    for adapter in adapter_files():
        fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
        unbound = unbound_placeholders(
            (str(fields.get(field, "")) for field in CONTRACT_FIELDS),
            declared_roles(fields.get("distribution_names")),
        )
        if unbound:
            offenders.append(f"{adapter.relative_to(REPO_ROOT)}: {unbound}")
    assert not offenders, (
        "adapters use placeholders the contract does not bind:\n"
        + "\n".join(offenders)
        + f"\nbound without a role: {list(UNPARAMETERISED_PLACEHOLDERS)}"
    )


def test_unbound_placeholder_rule_catches_a_synthetic_unknown_token():
    """The rule itself, pinned without depending on any adapter being wrong."""
    assert unbound_placeholders(["push <remote> <default>"]) == []
    assert unbound_placeholders(["install <package-name>"]) == ["<package-name>"]
    assert unbound_placeholders([None, "", "dist/*-<version>.whl"]) == []

    # Matching must be permissive: these all failed to match the old regex and
    # were therefore read as "not a placeholder" rather than as unbound.
    assert unbound_placeholders(["which <TOOL_NAME>"]) == ["<TOOL_NAME>"]
    assert unbound_placeholders(["gem install <gemName>"]) == ["<gemName>"]
    assert unbound_placeholders(["<pkg.name>"]) == ["<pkg.name>"]
    assert unbound_placeholders(["<path/to/thing>"]) == ["<path/to/thing>"]

    # A role token is bound only by a declared role.
    assert unbound_placeholders(["which <distribution-name:binary>"]) == [
        "<distribution-name:binary>"
    ]
    assert unbound_placeholders(["which <distribution-name:binary>"], {"binary"}) == []
    assert unbound_placeholders(["which <distribution-name:binary>"], {"package"}) == [
        "<distribution-name:binary>"
    ]


def test_declared_roles_reads_the_folded_map():
    assert declared_roles(None) == set()
    assert declared_roles("null") == set()
    assert declared_roles("binary: pyproject.toml#project.scripts") == {"binary"}
    assert declared_roles("package: package.json#.name binary: package.json#.bin") == {
        "package",
        "binary",
    }


def test_contract_binds_every_placeholder_in_the_vocabulary():
    text = ADAPTER_CONTRACT.read_text(encoding="utf-8")
    expected = list(UNPARAMETERISED_PLACEHOLDERS) + ["<distribution-name:role>"]
    missing = [token for token in expected if f"`{token}`" not in text]
    assert not missing, f"contract does not bind its own placeholders: {missing}"


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

# Forge CLIs. A *second* axis of variation from the one above: `gh` is not a
# build tool, so it sailed through TECHNOLOGY_LITERALS while hardcoding GitHub
# into Step 9 (#97). Kept as its own tuple because it is also checked
# differently — see the guard below.
#
# Matched on word boundaries, not as substrings. `"gh "` as a plain substring
# hits "throu[gh ]those" and "enou[gh ]to", so the naive form fails *closed* on
# ordinary prose — a guard that cries wolf gets deleted, which is how you end up
# with no guard at all.
FORGE_CLIS = ("gh", "glab", "tea")
FORGE_LITERALS = ("releases/new",)

# Tag conventions. `v<version>` is one ecosystem's convention wearing the
# costume of a universal one: a Go submodule tags `sub/module/v1.2.3` and Maven
# frequently tags `<artifactId>-<version>` (#96).
TAG_CONVENTION_LITERALS = ("v<version>", "v<new>", "v<old>")


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


def forge_and_tag_offenders(text):
    """Forge CLIs and tag conventions appearing in core-workflow prose.

    Kept a pure function of the text, like the rules above, so the word-boundary
    behaviour can be pinned directly instead of only through whatever the real
    SKILL.md happens to say today.
    """
    offenders = [
        literal
        for literal in FORGE_LITERALS + TAG_CONVENTION_LITERALS
        if literal in text
    ]
    offenders += [
        command_line_interface
        for command_line_interface in FORGE_CLIS
        if re.search(rf"\b{command_line_interface}\b", text)
    ]
    return offenders


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


def test_core_names_no_forge_and_no_tag_convention():
    """The two seam leaks of #96 and #97, pinned over the *unstripped* file.

    Deliberately not `strip_fenced_code_blocks`. The guard above strips fences so
    illustrative examples are not read as instructions — but Step 9's leak was
    `gh release create` sitting *inside* a fence, as a live instruction. Stripping
    fences here would leave the guard blind to the exact shape the leak took.

    Fences in the core are not off-limits generally: `git tag -a`, `git add`, and
    `git reset --hard` all live in them legitimately. Git is the portable
    substrate every target shares. A forge CLI and a tag convention are not.
    """
    offenders = forge_and_tag_offenders(RELEASE_SKILL_MD.read_text(encoding="utf-8"))
    assert not offenders, (
        f"core SKILL.md hardcodes forge or tag conventions {offenders} — "
        "these belong in the adapter's `release_command` and `tag_pattern`"
    )


def test_forge_rule_is_matched_on_word_boundaries():
    """The rule itself, including the false positive that shaped it."""
    assert forge_and_tag_offenders("gh release create <tag>") == ["gh"]
    assert forge_and_tag_offenders("glab release create <tag>") == ["glab"]
    assert forge_and_tag_offenders("tag it as v<version>") == ["v<version>"]
    assert forge_and_tag_offenders("point them at releases/new") == ["releases/new"]

    # Ordinary prose that a substring match would have condemned.
    assert forge_and_tag_offenders("every later step reads through those fields") == []
    assert forge_and_tag_offenders("that is high enough to matter") == []
    # `<tag>` is the abstraction, never an offender.
    assert forge_and_tag_offenders('git tag -a "<tag>" -m "<tag>"') == []


def test_core_reads_the_tag_and_release_fields():
    """The positive counterpart to the guard above, which deletion satisfies.

    Removing Step 9's release-creation entirely would make the forge literals
    vanish and turn that test green while losing the behaviour. This asserts the
    core actually routes through the two new fields.
    """
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8")
    for field in ("tag_pattern", "release_command"):
        assert field in text, f"core does not read the adapter's `{field}`"
    assert "<tag>" in text, "core must substitute the expanded tag"


def test_core_treats_a_failed_release_object_as_a_shipped_release():
    """Graceful degradation, generalised off `gh`.

    `release_command` runs *after* the push, so by the time it can fail the tag
    is already public and the release has shipped. Reporting that as a failed
    release tells the user to re-cut something that is already out.
    """
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8").lower()
    assert "release object" in text, "core must name what degrades away"
    assert (
        "not a failed release" in text
    ), "core must state that a failed release_command is not a failed release"


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


def test_stamp_precedes_commit_which_precedes_tag():
    """The stamp-before-tag trap: tagging a tree whose manifests still carry the
    old version produces a tag that is wrong at the commit it points to."""
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8")
    stamp_position = text.index("## Step 5 — Stamp")
    commit_position = text.index("## Step 7 — Commit")
    tag_position = text.index("## Step 8 — Tag")
    assert (
        stamp_position < commit_position < tag_position
    ), "stamp must precede commit, which must precede tag"


def test_exactly_one_confirmation_checkpoint_before_publishing():
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8")
    assert (
        text.count("CONFIRMATION CHECKPOINT") == 1
    ), "there must be exactly one confirmation checkpoint"
    checkpoint_position = text.index("CONFIRMATION CHECKPOINT")
    assert checkpoint_position < text.index(
        "## Step 9 — Publish"
    ), "the checkpoint must precede the first outward-facing action"
    assert checkpoint_position > text.index(
        "## Step 8 — Tag"
    ), "the checkpoint must follow the local, reversible work"


def test_core_documents_the_rollback():
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8")
    assert "git tag -d" in text, "rollback must show how to delete the local tag"
    assert "git reset --hard" in text, "rollback must show how to undo the commit"


def test_core_verifies_the_install_not_just_the_build():
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8").lower()
    assert "install_verify_command" in text
    assert (
        "outside" in text and "checkout" in text
    ), "the install check must require the shim to resolve outside the checkout"


RELEASE_EVALS = REPO_ROOT / "evals" / "release-evals.json"
EVAL_CASE_KEYS = {"id", "skill", "prompt", "expected_output", "assertions"}

REQUIRED_EVAL_NAMES = {
    "happy-path",
    "dirty-tree-refusal",
    "failing-gate-refusal",
    "stamp-before-tag-ordering",
    "second-version-literal-refusal",
    "artifact-pattern-mismatch-refusal",
    "ship-release-trigger-boundary",
}


def test_release_evals_valid_schema():
    assert RELEASE_EVALS.is_file(), "evals/release-evals.json must exist"
    data = json.loads(RELEASE_EVALS.read_text(encoding="utf-8"))
    assert data["skill_name"] == "release"
    assert isinstance(data["evals"], list) and data["evals"], "no eval cases"
    for eval_case in data["evals"]:
        assert (
            eval_case.keys() >= EVAL_CASE_KEYS
        ), f"case {eval_case.get('id')} missing keys"
        assert isinstance(eval_case["assertions"], list) and eval_case["assertions"]


def test_cases_narrating_a_fixture_declare_themselves_illustrative():
    """Three cases narrate a fixture adapter at `references/targets/fixture/echo.md`
    that does not exist, with an empty `files` array — against a real checkout
    Step 0's "nothing matches → refuse" fires instead of the asserted behaviour.

    Shipping the fixture for real is the wrong fix: anything under
    `references/targets/` is a live adapter that detection can select during an
    actual release. So a case that narrates one must say it cannot execute.

    Keying the requirement to the narration is what gives it teeth: the earlier
    shape let any case exempt itself with one key (#101.5).
    """
    data = json.loads(RELEASE_EVALS.read_text(encoding="utf-8"))
    offenders = [
        eval_case.get("eval_name")
        for eval_case in data["evals"]
        if _narrates_a_fixture(eval_case)
        and not eval_case.get("files")
        and not eval_case.get("illustrative")
    ]
    assert (
        not offenders
    ), f"cases narrate a fixture that does not exist, unmarked: {offenders}"


def _narrates_a_fixture(eval_case):
    return "fixture" in json.dumps(eval_case).lower()


def test_not_every_eval_case_is_illustrative():
    """A suite where every case opts out asserts nothing.

    Without this the guard above stays green as the suite decays to zero
    executable cases — which is what my first pass did, marking all seven.
    """
    data = json.loads(RELEASE_EVALS.read_text(encoding="utf-8"))
    executable = [
        eval_case.get("eval_name")
        for eval_case in data["evals"]
        if not eval_case.get("illustrative")
    ]
    assert executable, "every release eval case is marked illustrative"


def test_illustrative_marks_are_not_over_applied():
    """A case narrating no fixture needs no exemption; claiming one hides that it
    was never checked for executability."""
    data = json.loads(RELEASE_EVALS.read_text(encoding="utf-8"))
    over_marked = [
        eval_case.get("eval_name")
        for eval_case in data["evals"]
        if eval_case.get("illustrative") and not _narrates_a_fixture(eval_case)
    ]
    assert not over_marked, f"marked illustrative without a fixture: {over_marked}"


def test_release_evals_cover_every_required_scenario():
    data = json.loads(RELEASE_EVALS.read_text(encoding="utf-8"))
    present = {eval_case.get("eval_name") for eval_case in data["evals"]}
    missing = REQUIRED_EVAL_NAMES - present
    assert not missing, f"eval coverage gaps: {sorted(missing)}"


README = REPO_ROOT / "README.md"
PLUGIN_JSON = REPO_ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE_JSON = REPO_ROOT / ".claude-plugin" / "marketplace.json"


def test_readme_skills_table_row_documents_every_adapter():
    """A bare `"/release" in README` passed even with the table row deleted — the
    convention note below the table mentions /release three more times. Pin the
    row itself, and pin its adapter list to the filesystem so it cannot rot (#101.4).
    """
    rows = [
        line
        for line in README.read_text(encoding="utf-8").splitlines()
        if line.startswith("| release ")
    ]
    assert (
        len(rows) == 1
    ), f"expected exactly one /release skills-table row, got {len(rows)}"
    row = rows[0]
    assert "`/release`" in row, "the skills-table row must name the invocation"
    missing = [identity for identity in adapter_identities() if identity not in row]
    assert not missing, f"the README row does not list adapters: {missing}"


def test_release_is_registered_everywhere_a_skill_must_be():
    assert "/release" in README.read_text(encoding="utf-8"), "README omits /release"
    plugin = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))
    assert "release" in plugin["keywords"], "plugin.json keywords omit release"
    assert "/release" in plugin["description"], "plugin.json description omits /release"
    marketplace = json.loads(MARKETPLACE_JSON.read_text(encoding="utf-8"))
    assert (
        "/release" in marketplace["plugins"][0]["description"]
    ), "marketplace.json description omits /release"


def test_ship_description_disclaims_release_territory():
    fields = parse_frontmatter(
        (REPO_ROOT / "skills" / "ship" / "SKILL.md").read_text(encoding="utf-8")
    )
    description = fields.get("description", "")
    assert (
        "version" in description.lower()
    ), "/ship must disclaim versioning so /release's territory is unambiguous"
