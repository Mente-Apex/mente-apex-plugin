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
BUILD_DIR = RELEASE_SKILL_DIR / "references" / "build"
DISTRIBUTIONS_DIR = RELEASE_SKILL_DIR / "references" / "distributions"
ADAPTER_CONTRACT = RELEASE_SKILL_DIR / "references" / "ADAPTER-CONTRACT.md"

# How a component builds and tests itself. `distribution_names` is here despite
# its name: every value it holds is a path the TOOLCHAIN determines
# (pyproject.toml#project.scripts, package.json#.bin, pom.xml#/project/groupId).
# The naming coincidence is not evidence. `tag_pattern` and `publish_command` are
# repo-level in effect and read only from the root component.
BUILD_FIELDS = (
    "technology",
    "toolchain",
    "fingerprint",
    "version_source",
    "relock_command",
    "gate_command",
    "build_command",
    "artifact_pattern",
    "distribution_names",
    "install_verify_command",
    "tag_pattern",
    "publish_command",
)

# What the repository ships beyond the tag, and how you confirm it arrived.
# `install_verify_command` is on BOTH field sets and both run: one proves the
# built thing installs, the other proves the shipped thing arrived. Forcing them
# into one field is what made that command a compound.
DISTRIBUTION_FIELDS = (
    "kind",
    "fingerprint",
    "derived_manifests",
    "install_verify_command",
    "release_command",
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
    "python/uv-nobuild": "working",
    "python/uv": "working",
    "typescript/npm": "stub",
    "java/maven": "stub",
    "rust/cargo": "stub",
    "distributions/claude-plugin": "working",
    "distributions/npm-registry": "stub",
    "distributions/maven-central": "stub",
    "distributions/crates-io": "stub",
}

# Adapters whose lockfile records the project's *own* version, so stamping the
# manifest makes the lockfile stale. Pinned by identity because the failure is
# invisible until publish time: the release commit carries an inconsistent pair
# and the toolchain refuses on a dirty tree at the last step (#99).
LOCKFILE_CARRIES_OWN_VERSION = (
    "python/uv-nobuild",
    "python/uv",
    "typescript/npm",
    "rust/cargo",
)

# The separation rule. A build adapter may fingerprint only on build evidence; a
# distribution adapter only on shipping evidence. Neither may look at the other's.
#
# This is what makes the skipped-wheel incident impossible rather than patched.
# `.claude-plugin/plugin.json` is shipping evidence, and it was deciding
# `build_command: null` for a repository with a setuptools backend and a console
# script — one that builds a wheel perfectly well. Adding a fourth adapter filled
# in the missing square; it did not remove the cause.
#
# Both tuples are tied to the contract's own prose by the two guards below:
# `test_build_evidence_covers_the_contracts_level_one_table` and
# `test_the_evidence_lists_match_the_contracts_separation_rule`. They had drifted
# apart with nothing comparing them — `package.json` and `build.gradle.kts` are
# named by the Level 1 table and were absent here, so a distribution adapter
# could fingerprint bare `package.json` and this guard said nothing.
BUILD_EVIDENCE = (
    "uv.lock",
    "package-lock.json",
    "package.json",
    "Cargo.lock",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "pyproject.toml",
    "setup.py",
)

# Files that record only how a repository ships. Matched on the whole path, at any
# selector, in the build direction — `.claude-plugin/` and an `.npmrc` carry no
# build fact for a selector to disambiguate.
SHIPPING_EVIDENCE = (
    ".claude-plugin",
    ".npmrc",
    ".goreleaser.yml",
    ".goreleaser.yaml",
)

# The ecosystems whose ONE manifest carries both kinds of fact, which is the whole
# and only justification for the selector carve-out below. Maven, Cargo and npm
# each have no second file to redirect a distribution fingerprint to, the way
# `.claude-plugin/` sits apart from `package.json`. Any other build-evidence file
# has one, so the carve-out does not reach it: a distribution adapter
# fingerprinting `pyproject.toml#project.version` or `uv.lock#anything` is a
# violation, selector or no selector.
SHARED_MANIFESTS = ("pom.xml", "Cargo.toml", "package.json")

# The named shipping facts each shared manifest records. Prefix-matched, so a
# predicate form (`.private==false`) reads the same as the bare selector. A
# selector into a shared manifest that is NOT one of these is a build fact, and
# naming it from either axis is an offence in that axis's direction.
SHIPPING_SELECTORS = {
    "pom.xml": ("/project/distributionManagement",),
    "Cargo.toml": ("package.publish",),
    "package.json": (".private", ".publishConfig", ".files"),
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


def level_one_fingerprints(contract_text):
    """Every backticked path in the Level 1 detection table's fingerprint cells.

    This is the contract's *other* definition of build evidence, and the one Step
    0 tells the agent to walk for. It and `BUILD_EVIDENCE` had drifted apart with
    no test comparing them.
    """
    section = _section_after(contract_text, "### Level 1")
    paths = set()
    for line in section.splitlines():
        cells = [cell.strip() for cell in line.split("|")[1:-1]]
        if len(cells) != 2:
            continue
        fingerprint_cell, technology = cells
        if technology in ("", "Technology") or set(technology) <= {"-"}:
            continue
        paths.update(re.findall(r"`([^`]+)`", fingerprint_cell))
    return paths


def evidence_bullet_paths(contract_text, label):
    """Bare backticked paths from one bullet of the separation rule's evidence lists.

    Selector-bearing examples (`pyproject.toml#tool.uv.package==false`) are
    dropped: the tuples they are compared against hold paths.
    """
    section = _section_after(contract_text, "### The separation rule")
    collected = []
    capturing = False
    for line in section.splitlines():
        if line.startswith(f"- **{label}"):
            capturing = True
        elif capturing and (not line.startswith("  ") or not line.strip()):
            break
        if capturing:
            collected.append(line)
    return {
        token
        for token in re.findall(r"`([^`]+)`", " ".join(collected))
        if "#" not in token
    }


def level_two_fingerprints(contract_text):
    """{(technology, toolchain): frozenset of selectors} from the Level 2 table.

    The table's fingerprint cell must list exactly what the adapter's `fingerprint`
    field lists. It did not, and could not: the field was one file path while the
    cell already carried a second, non-file selector, so the document contradicted
    itself and an adapter author had no rule to follow (#100.1).
    """
    section = _section_after(contract_text, "### Level 2")
    fingerprints = {}
    for line in section.splitlines():
        cells = [cell.strip() for cell in line.split("|")[1:-1]]
        if len(cells) != 3:
            continue
        technology, fingerprint_cell, toolchain = cells
        technology, toolchain = technology.strip("`"), toolchain.strip("`")
        if technology in ("", "Technology") or set(technology) <= {"-"}:
            continue
        fingerprints[(technology, toolchain)] = frozenset(
            token.strip().strip("`")
            for token in fingerprint_cell.split(" or ")
            if token.strip()
        )
    return fingerprints


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


def fingerprint_selectors(fingerprint_value):
    """The individual detection selectors in a `fingerprint`, however it is written.

    The field is a list (#100.1): an inline scalar is the one-entry shorthand, and
    a written-out list reaches here folded to one space-joined string. Splitting on
    whitespace is exact because the predicate form is spelled without spaces —
    `pyproject.toml#tool.uv.package==false` — which is why the contract requires
    that spelling rather than the `key == value` the detection table used to show.
    """
    return tuple(str(fingerprint_value or "").split())


def fingerprint_clauses(fingerprint_value):
    """Every individual clause a `fingerprint` tests, conjunctions expanded.

    An entry may be a `+`-joined conjunction — `uv.lock+.claude-plugin/plugin.json`
    — meaning every clause must match. For collision purposes the clause is the
    unit: `uv.lock+X` and a bare `uv.lock` both fire on a repo with a lockfile, so
    they overlap and need ranking, even though the two entries compare unequal as
    strings. Comparing whole entries would reintroduce at the clause level exactly
    the fail-open that comparing whole *fields* had at the entry level.
    """
    return tuple(
        clause
        for entry in fingerprint_selectors(fingerprint_value)
        for clause in entry.split("+")
    )


def unranked_shared_fingerprints(entries, ranked_toolchains):
    """Toolchains in one technology sharing a selector without being ranked.

    `entries` is a list of (toolchain, fingerprint) pairs for one technology;
    `ranked_toolchains` is that technology's Level 2 rows in table order. A
    colliding toolchain absent from the table has no declared precedence, so it
    silently shadows its twin or is shadowed by it.

    Collision is per *clause*, not per whole field. Comparing the folded field
    would let two adapters share one selector out of several and read as disjoint
    — a fail-open the field only acquired when it became a list.
    """
    selectors_by_toolchain = {
        toolchain: fingerprint_clauses(fingerprint)
        for toolchain, fingerprint in entries
    }
    all_selectors = [
        selector
        for selectors in selectors_by_toolchain.values()
        for selector in selectors
    ]
    duplicated = {
        selector for selector in all_selectors if all_selectors.count(selector) > 1
    }
    return sorted(
        toolchain
        for toolchain, selectors in selectors_by_toolchain.items()
        if duplicated.intersection(selectors) and toolchain not in ranked_toolchains
    )


# ── Selector syntax (#100.2) ──────────────────────────────────────────────────
# The selector language is a property of the FILE FORMAT, never of the field or
# the adapter's preference. Four adapters used three languages with the rule
# visible only by example, so an author had nothing to follow and the core had no
# way to know which parser a selector wanted.
SELECTOR_LANGUAGE_BY_SUFFIX = {
    ".json": "jq",
    ".yaml": "jq",
    ".yml": "jq",
    ".toml": "dotted",
    ".xml": "xpath",
}

SELECTOR_SHAPE_BY_LANGUAGE = {
    "jq": re.compile(r"^\.[A-Za-z_]"),
    "dotted": re.compile(r"^[A-Za-z_]"),
    "xpath": re.compile(r"^/[A-Za-z_]"),
}

# `path/to/file#selector==value`, the predicate form of a fingerprint entry.
_FINGERPRINT_PREDICATE = re.compile(r"^(\S+#\S+?)==(\S+)$")


def split_optional_marker(entry):
    """`(reference, is_optional)` for a `derived_manifests` entry.

    A trailing `?` means the mirror is legitimately absent in some repositories of
    the adapter's shape: stamp it if present, skip it if not. Required is the
    default and stays strict, so that a *typo'd* path stays distinguishable from a
    declared absence — silently skipping any missing file would make a mistyped
    entry read as a clean release that stamped one manifest fewer.

    The marker is stripped before the selector is validated, so an optional entry
    gets exactly the same syntax check as a required one. Exactly one `?` is
    stripped: a doubled `??` leaves a stray marker behind, which
    `selector_syntax_violation` then rejects rather than waving through as a jq
    optional-value operator nobody meant to write.
    """
    text = str(entry).strip()
    if text.endswith("?"):
        return text[:-1], True
    return text, False


def selector_syntax_violation(reference):
    """Why this `path#selector` misuses its file format's language, or None.

    Callers must strip the contract's optional marker first — a `?` reaching here
    is either a doubled marker or an unstripped entry, and both are errors rather
    than selectors. Without this branch the strip in `selector_references` would be
    unobservable: the shape checks below are prefix-anchored, so a trailing `?`
    would sail past every one of them.
    """
    if reference.endswith("?"):
        return (
            f"{reference}: a trailing '?' is the contract's optional marker, not "
            "part of the selector — strip it (and write only one)"
        )
    if "#" not in reference:
        return f"{reference}: not a path#selector reference"
    path, _, selector = reference.partition("#")
    suffix = Path(path).suffix
    language = SELECTOR_LANGUAGE_BY_SUFFIX.get(suffix)
    if language is None:
        return (
            f"{reference}: the contract declares no selector language for "
            f"{suffix or path!r} — add a row to its Selector syntax table"
        )
    if not SELECTOR_SHAPE_BY_LANGUAGE[language].match(selector):
        return f"{reference}: a {suffix} file takes a {language} selector"
    return None


def selector_references(fields):
    """Every `path#selector` an adapter declares, from every field carrying one."""
    references = []
    if not is_null(fields.get("version_source")):
        references.append(str(fields["version_source"]).strip())
    derived = str(fields.get("derived_manifests") or "").strip()
    if derived not in ("", "null", "[]"):
        references.extend(split_optional_marker(entry)[0] for entry in derived.split())
    references.extend(
        selector
        for _role, selector in _ROLE_DECLARATION.findall(
            str(fields.get("distribution_names") or "")
        )
    )
    for clause in fingerprint_clauses(fields.get("fingerprint")):
        predicate = _FINGERPRINT_PREDICATE.match(clause)
        if predicate:
            references.append(predicate.group(1))
        elif "#" in clause:
            references.append(clause)
    return references


def is_null(field_value):
    """The contract's `null`, however the frontmatter parser hands it over."""
    return (str(field_value or "")).strip() in ("", "null")


def relock_contract_violation(version_source, relock_command):
    """Why this pair is inconsistent, or None.

    `relock_command` refreshes a lockfile the *stamp* invalidated, so it only
    means anything for a target that stamps something. A target whose
    `version_source` is `null` records the version nowhere — the tag is the
    version — so nothing can go stale and a relock step would run a toolchain
    command for no reason, outside the one window the core can stage its output.
    """
    if is_null(version_source) and not is_null(relock_command):
        return "relock_command is set while version_source is null: nothing is stamped"
    return None


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
    # fingerprint and install_verify_command appear in both tuples; documenting
    # each once in the contract is enough, so duplicates collapse via set().
    fields = set(BUILD_FIELDS + DISTRIBUTION_FIELDS)
    missing = sorted(field for field in fields if f"`{field}`" not in text)
    assert not missing, f"contract does not document fields: {missing}"


def test_adapter_contract_explains_why_a_lockfile_is_not_a_derived_manifest():
    """`Cargo.lock` and `package-lock.json` are regenerated, never hand-stamped —
    which is why the concern needed a field of its own rather than another
    `derived_manifests` entry (#99)."""
    text = ADAPTER_CONTRACT.read_text(encoding="utf-8")
    assert (
        "### `relock_command`" in text
    ), "contract must explain the field, not just list it"
    assert "derived_manifests" in _section_after(
        text, "### `relock_command`"
    ), "the contract must say why a lockfile is not simply a derived manifest"


def test_adapter_contract_declares_detection_precedence():
    text = ADAPTER_CONTRACT.read_text(encoding="utf-8")
    assert "## Detection" in text, "contract must declare the detection procedure"
    # Precedence is declared, not emergent from directory listing order.
    for technology in ("python", "typescript", "java"):
        assert technology in text, f"detection omits technology: {technology}"
    assert "status: stub" in text, "contract must define the stub marker"


def adapter_files():
    """Every build adapter under references/build/, recursively, sorted."""
    return sorted(BUILD_DIR.rglob("*.md"))


def distribution_files():
    """Every distribution adapter under references/distributions/, sorted."""
    return sorted(DISTRIBUTIONS_DIR.rglob("*.md"))


def test_every_build_adapter_declares_all_build_fields():
    adapters = adapter_files()
    assert adapters, "no adapters found under references/build/"
    offenders = []
    for adapter in adapters:
        fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
        missing = [field for field in BUILD_FIELDS if field not in fields]
        extra = [
            field
            for field in DISTRIBUTION_FIELDS
            if field in fields and field not in BUILD_FIELDS
        ]
        if missing:
            offenders.append(f"{adapter.relative_to(REPO_ROOT)}: missing {missing}")
        if extra:
            offenders.append(
                f"{adapter.relative_to(REPO_ROOT)}: carries distribution fields "
                f"{extra} — those belong in references/distributions/"
            )
    assert not offenders, "build adapters violate the contract:\n" + "\n".join(
        offenders
    )


def test_every_distribution_adapter_declares_all_distribution_fields():
    adapters = distribution_files()
    assert adapters, "no adapters found under references/distributions/"
    offenders = []
    for adapter in adapters:
        fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
        missing = [field for field in DISTRIBUTION_FIELDS if field not in fields]
        if missing:
            offenders.append(f"{adapter.relative_to(REPO_ROOT)}: missing {missing}")
        if fields.get("kind") != adapter.stem:
            offenders.append(
                f"{adapter.relative_to(REPO_ROOT)}: kind {fields.get('kind')!r} "
                f"!= filename {adapter.stem!r}"
            )
    assert not offenders, "distribution adapters violate the contract:\n" + "\n".join(
        offenders
    )


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


def test_claude_plugin_distribution_stamps_both_manifest_mirrors():
    """This repo's own distribution adapter must name every manifest the guard checks."""
    adapter = DISTRIBUTIONS_DIR / "claude-plugin.md"
    assert adapter.is_file(), "the dogfooded distribution adapter must exist"
    fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
    # Read the parsed fields, never the file text. A substring search is satisfied
    # by body prose that *discusses* these paths, and this adapter's prose names
    # every one of them.
    entries = str(fields.get("derived_manifests") or "").split()
    optionality = {
        split_optional_marker(entry)[0].partition("#")[0]: split_optional_marker(entry)[
            1
        ]
        for entry in entries
    }
    assert set(optionality) == {
        ".claude-plugin/plugin.json",
        ".claude-plugin/marketplace.json",
    }, f"both plugin mirrors must be stamped; got {sorted(optionality)}"
    # The `?` is load-bearing (see the adapter's own "the `?` is load-bearing"
    # section): plugin.json is this shape's defining mirror and must stay
    # required, while marketplace.json is legitimately absent in some repos of
    # this shape and must stay optional.
    assert (
        optionality[".claude-plugin/plugin.json"] is False
    ), "plugin.json must be required, not optional"
    assert (
        optionality[".claude-plugin/marketplace.json"] is True
    ), "marketplace.json must be optional"
    assert "status" not in fields, "the dogfooded adapter is not a stub"


def test_the_no_build_adapter_makes_the_build_manifest_canonical():
    """The version arrow points out of the build adapter, with no exception.

    git-tag-only previously made .claude-plugin/plugin.json canonical while
    uv-plugin made pyproject.toml canonical — a disagreement about direction that
    reopened the axis tangle. Nothing reads either literal when there is no build,
    so the direction is free, and uniform beats faithful.
    """
    adapter = BUILD_DIR / "python" / "uv-nobuild.md"
    fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
    assert fields.get("version_source") == "pyproject.toml#project.version"
    assert (
        fields.get("build_command") == "null"
    ), "a package = false target builds nothing"
    assert (
        fields.get("artifact_pattern") == "null"
    ), "no build means no artifact pattern"


def test_no_build_adapter_names_no_install_verify_command():
    """A build adapter that builds nothing has nothing to install-verify.

    `install_verify_command` proves the *built* thing installs — the contract's
    own "Where the axes tangle" section says each of the two adapters that carry
    this field names only its own half. `claude plugin list` verifies what a
    *distribution* adapter shipped; declaring it here, on the build side, names
    the other half, and duplicates `distributions/claude-plugin.md`'s identical
    entry on any repository that resolves both.
    """
    adapter = BUILD_DIR / "python" / "uv-nobuild.md"
    fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
    assert is_null(fields.get("install_verify_command")), (
        "uv-nobuild builds nothing, so install_verify_command must be null, "
        "not a distribution-side check like `claude plugin list`"
    )


def test_uv_adapter_verifies_a_real_artifact_pattern():
    """The wheel-name check is the whole point of artifact_pattern."""
    adapter = BUILD_DIR / "python" / "uv.md"
    assert adapter.is_file(), "the uv adapter must exist"
    fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
    assert fields.get("build_command") == "uv build", "uv projects build with uv build"
    assert "dist/" in fields.get(
        "artifact_pattern", ""
    ), "artifact_pattern must name the real build output directory"
    assert fields.get("build_command") != "null", "a uv package target does build"


def test_the_optional_marker_is_stripped_on_the_path_adapters_are_validated_by():
    """The strip must be observable, or it is decoration.

    An earlier version of this test called `split_optional_marker` directly and
    asserted on its output, which passed identically whether or not
    `selector_references` stripped anything: the shape checks are prefix-anchored,
    so a trailing `?` was never a violation to begin with. Reverting the strip left
    the whole suite green. Two things fix that — `selector_syntax_violation` now
    rejects a stray `?`, and this test goes through `selector_references`, the
    function every adapter is actually validated by.
    """
    optional = {"derived_manifests": "a.json#.version?"}
    assert selector_references(optional) == ["a.json#.version"], "marker not stripped"
    assert [
        selector_syntax_violation(ref) for ref in selector_references(optional)
    ] == [None]
    # The stripped reference still gets the full format-specific check: a TOML file
    # refuses a jq selector whether the entry is optional or not.
    assert selector_syntax_violation(
        selector_references({"derived_manifests": "a.toml#.version?"})[0]
    )
    # Exactly one marker is stripped, so a doubled one cannot pose as a selector.
    assert selector_syntax_violation(
        selector_references({"derived_manifests": "a.json#.version??"})[0]
    )
    # A required entry is untouched, and `is_optional` is what tells them apart.
    assert split_optional_marker("a.json#.version") == ("a.json#.version", False)
    assert split_optional_marker("a.json#.version?") == ("a.json#.version", True)


def test_optional_marker_is_confined_to_derived_manifests():
    """`version_source`, `fingerprint` and `distribution_names` have no optional case.

    A canonical version that might not exist is not canonical; an absent file
    simply fails to match a fingerprint, so a marker there means nothing; and a
    name a command interpolates is not optional. All three would fail later, at
    the point where nothing is checking.

    The contract names all three exclusions. An earlier version of this test
    checked only two, and `fingerprint: …?` passed the whole suite.

    Runs over both adapter kinds: a distribution adapter has no `version_source`
    or `distribution_names` (those checks are simply no-ops for it), but it does
    have `fingerprint`, and the rule against an optional fingerprint entry binds
    there exactly as it does on a build adapter.
    """
    offenders = []
    for adapter in adapter_files() + distribution_files():
        identity = f"{adapter.parent.name}/{adapter.stem}"
        fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
        if str(fields.get("version_source") or "").strip().endswith("?"):
            offenders.append(f"{identity}: version_source is marked optional")
        for entry in fingerprint_selectors(fields.get("fingerprint")):
            if entry.endswith("?"):
                offenders.append(f"{identity}: fingerprint entry {entry!r} is optional")
        for _role, selector in _ROLE_DECLARATION.findall(
            str(fields.get("distribution_names") or "")
        ):
            if selector.strip().endswith("?"):
                offenders.append(f"{identity}: distribution_names entry is optional")
    assert (
        not offenders
    ), "optional marker used outside derived_manifests:\n" + "\n".join(offenders)


def test_the_contract_and_the_core_both_define_the_optional_marker():
    """A marker the contract declares but the core never acts on is a no-op.

    Both halves are scoped to the section that has to carry them. Unscoped
    whole-file substring checks passed when the entire Step 5 block was moved
    verbatim into the trailing "what /release does not do" section, where the
    stamp never reaches it — prose present but dead.
    """
    contract = ADAPTER_CONTRACT.read_text(encoding="utf-8")
    marker_section = _section_after(contract, "### Optional derived manifests")
    assert marker_section.strip(), "the marker is undocumented"
    assert (
        "typo" in marker_section.lower()
    ), "the section must say why absence is declared rather than inferred"

    stamp_step = _section_after(RELEASE_SKILL_MD.read_text(), "## Step 5 — Stamp")
    assert "ends in `?`" in stamp_step, (
        "Step 5 must define the marker's behaviour, or the contract declares a "
        "syntax the core ignores"
    )
    assert (
        "does not exist is a refusal" in stamp_step
    ), "Step 5 must still refuse an absent *required* entry"


def test_the_core_never_recites_the_declared_manifest_list_to_git():
    """Steps 6 and 7 must name the *stamped set*, not `derived_manifests`.

    Step 5 learned to skip an absent optional manifest while the staging and
    rollback commands still recited every declared entry. `git add` on a
    nonexistent pathspec stages NOTHING — not "everything else" — so the release
    commit would abort at Step 7, after the gate and the build, on precisely the
    repositories the optional marker was added to support. The rollback line at
    Step 6 had the same defect while being the recovery advice printed to the user.
    """
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8")
    for heading in ("## Step 6 — Build and verify the artifacts", "## Step 7 — Commit"):
        section = _section_after(text, heading)
        for command in ("git add", "git checkout --"):
            for line in section.splitlines():
                if command not in line:
                    continue
                assert "each derived manifest" not in line, (
                    f"{heading}: `{command}` recites the declared list; an absent "
                    "optional manifest makes git reject the whole pathspec"
                )
                assert "stamped set" in line, (
                    f"{heading}: `{command}` must name the stamped set, so a "
                    "skipped optional manifest is not passed to git"
                )


def test_the_report_surfaces_a_skipped_optional_manifest():
    """An optional entry that silently does nothing is the marker's failure mode.

    "Stamp it if present, skip it if absent" makes a manifest renamed a year ago
    indistinguishable from one that was never meant to exist here — unless every
    skip is named. The contract argues absence must be declared rather than
    inferred; this is the other half, at the point the user actually reads.
    """
    report = _section_after(RELEASE_SKILL_MD.read_text(), "## Step 11 — Report")
    # Scope to the fenced template, not the whole section: the paragraph arguing
    # for the line also contains the word "Skipped", so an unscoped substring
    # check passed with the template line deleted — the assert survived while the
    # thing it protects did not.
    template = report.split("```")[1]
    assert (
        "Skipped" in template
    ), "the report TEMPLATE must carry a line for skipped mirrors"
    assert (
        "optional" in report.lower()
    ), "the report must say what a skipped entry is, not just print a label"


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


def test_relock_command_is_only_declared_where_something_is_stamped():
    """The real adapters, checked against the rule pinned synthetically below."""
    offenders = []
    for adapter in adapter_files():
        fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
        violation = relock_contract_violation(
            fields.get("version_source"), fields.get("relock_command")
        )
        if violation:
            offenders.append(f"{adapter.relative_to(REPO_ROOT)}: {violation}")
    assert not offenders, "adapters misdeclare relock_command:\n" + "\n".join(offenders)


def test_relock_rule_catches_a_synthetic_tag_only_target():
    """No adapter violates this today, so the failure branch needs exercising."""
    assert (
        relock_contract_violation("pyproject.toml#project.version", "uv lock") is None
    )
    assert relock_contract_violation("null", "null") is None
    assert relock_contract_violation(None, None) is None
    assert relock_contract_violation("null", "uv lock") is not None


def test_adapters_whose_lockfile_carries_their_own_version_declare_a_relock():
    """The bug itself, pinned per adapter.

    This repo's own `uv.lock` carries `version = "…"` for the root project, so
    the dogfooded adapter is the first one the trap bites: stamping
    `pyproject.toml` without refreshing the lock puts an inconsistent pair in the
    release commit (#99).
    """
    declared = {
        f"{adapter.parent.name}/{adapter.stem}": parse_frontmatter(
            adapter.read_text(encoding="utf-8")
        ).get("relock_command")
        for adapter in adapter_files()
    }
    missing = [
        identity
        for identity in LOCKFILE_CARRIES_OWN_VERSION
        if is_null(declared.get(identity))
    ]
    assert not missing, (
        f"adapters whose lockfile records their own version declare no "
        f"relock_command: {missing}"
    )


def test_npm_adapter_body_records_that_it_shares_the_lockfile_shape():
    """`package-lock.json` carries the package's own version exactly as
    `Cargo.lock` does. The stub has never hit it; the body must say it will."""
    body = parse_frontmatter(
        (BUILD_DIR / "typescript" / "npm.md").read_text(encoding="utf-8")
    )["_body"]
    assert "package-lock.json" in body, "the npm body must name its own lockfile"
    assert "relock_command" in body, "the npm body must name the field that fixes it"


def test_no_adapter_recommends_a_forbidden_python_toolchain():
    """uv is canonical: pip/pipx/pyenv must never appear as an instruction."""
    offenders = []
    for adapter in adapter_files():
        fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
        if fields.get("technology") != "python":
            continue
        commands = " ".join(str(fields.get(field, "")) for field in BUILD_FIELDS)
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
    identities = {
        f"{adapter.parent.name}/{adapter.stem}": adapter for adapter in adapter_files()
    }
    identities.update(
        {f"distributions/{adapter.stem}": adapter for adapter in distribution_files()}
    )
    return identities


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

    The contract warns about this in "Adding an adapter" step 6 — detection
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
    disjoint = [("uv", "uv.lock"), ("uv-nobuild", "plugin.json")]
    assert unranked_shared_fingerprints(disjoint, []) == []


def test_every_adapter_fingerprint_matches_its_detection_row():
    """The field and the table must agree, entry for entry (#100.1).

    They disagreed: `fingerprint` was documented as "the file whose presence
    selects this adapter" while the table's `python/git-tag-only` row listed a
    second selector that was not a file at all. A repo matching only the second
    got contradictory instructions and the contract had no tiebreak.
    """
    rowed = level_two_fingerprints(ADAPTER_CONTRACT.read_text(encoding="utf-8"))
    offenders = []
    for adapter in adapter_files():
        identity = (adapter.parent.name, adapter.stem)
        fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
        declared = frozenset(fingerprint_selectors(fields.get("fingerprint")))
        assert declared, f"{identity}: fingerprint declares no selector"
        if identity not in rowed:
            offenders.append(f"{identity[0]}/{identity[1]}: no Level 2 row")
        elif declared != rowed[identity]:
            offenders.append(
                f"{identity[0]}/{identity[1]}: field declares {sorted(declared)}, "
                f"table lists {sorted(rowed[identity])}"
            )
    assert (
        not offenders
    ), "fingerprint field and detection table disagree:\n" + "\n".join(offenders)


def test_the_package_false_case_resolves_without_a_plugin_manifest():
    """The empty square in the 2x2, closed.

    A uv project declaring `package = false` with no `.claude-plugin/` directory
    used to match git-tag-only by predicate, then refuse at the version_source
    check because that adapter addressed plugin manifests the project had not
    got. Under the split it resolves to a build adapter with no distribution
    adapter — which is a legitimate repository, not a dead end.
    """
    contract_text = ADAPTER_CONTRACT.read_text(encoding="utf-8")
    rowed = level_two_fingerprints(contract_text)
    predicate = "pyproject.toml#tool.uv.package==false"
    assert predicate in rowed[("python", "uv-nobuild")]
    assert predicate not in rowed[("python", "uv")]

    python_order = [
        toolchain
        for technology, toolchain in level_two_rows(contract_text)
        if technology == "python"
    ]
    assert python_order.index("uv-nobuild") < python_order.index("uv")

    adapter = BUILD_DIR / "python" / "uv-nobuild.md"
    fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
    assert "derived_manifests" not in fields, (
        "a build adapter names no manifest mirrors; that is the distribution "
        "adapter's field, and conflating them is what this split removed"
    )


def _fingerprint_clause_parts(fields):
    """(path, selector-or-None) for every clause a fingerprint names.

    A bare `pom.xml` and a selecting `pom.xml#/project/distributionManagement`
    name the same *path* but are not the same *claim*: the second names a
    shipping fact recorded inside a file that also carries build facts. Maven,
    Cargo and npm have exactly one manifest each, so the path alone cannot tell
    the two kinds of fact apart — the selector is what does, in both directions.
    See `separation_violations` below.
    """
    parts = []
    for entry in fingerprint_selectors(str(fields.get("fingerprint", ""))):
        for clause in fingerprint_clauses(entry):
            path, separator, selector = clause.partition("#")
            parts.append((path, selector if separator else None))
    return parts


def names_a_shipping_fact(path, selector):
    """Is this clause a *named shipping fact* recorded inside a shared manifest?

    The one carve-out ruling 1 grants, and it is bounded by
    `SHARED_MANIFESTS`: only an ecosystem with a single manifest has no second
    file to redirect a fingerprint to, and only the selectors `SHIPPING_SELECTORS`
    names are shipping facts. `pyproject.toml#project.version` is not one of them
    at any selector, because Python's shipping evidence lives elsewhere.
    """
    if selector is None or path not in SHARED_MANIFESTS:
        return False
    return any(
        selector.startswith(shipping) for shipping in SHIPPING_SELECTORS.get(path, ())
    )


def separation_violations(fields, axis):
    """Every separation-rule offence this `fingerprint` commits, as readable lines.

    The single implementation of the rule, called by both the real guard over the
    shipped adapters and the synthetic mutation proof below. They used to re-type
    the predicate independently, so weakening the real condition left both green —
    the real one passing vacuously, because no adapter violates it today.

    Both directions read *facts*, not files, but they are not symmetric and the
    asymmetry is the point:

    - **distribution → build evidence.** A bare build-evidence path is an
      offence: that reads the file's build identity. A `SHIPPING_SELECTORS`
      selector into a `SHARED_MANIFESTS` file is not: `pom.xml`, `Cargo.toml` and
      `package.json` are each their ecosystem's only manifest, carrying publish
      eligibility in the same file as the version.
    - **build → shipping evidence.** A `SHIPPING_EVIDENCE` path offends at any
      selector — `.claude-plugin/plugin.json#.version` is still the incident. And
      a build adapter naming a *shipping selector inside a shared manifest*
      offends too: deciding how a repository builds from
      `pom.xml#/project/distributionManagement` is the incident's exact shape at
      selector granularity. Ruling 1 taught the contract that a shared manifest
      carries named shipping facts; the build direction has to learn it as well,
      or half the rule reads files while the other half reads facts.
    """
    assert axis in ("build", "distribution"), f"unknown axis: {axis}"
    offences = []
    for path, selector in _fingerprint_clause_parts(fields):
        clause = path if selector is None else f"{path}#{selector}"
        if axis == "build":
            if any(path.startswith(marker) for marker in SHIPPING_EVIDENCE):
                offences.append(
                    f"build adapter fingerprints on shipping evidence {clause!r}"
                )
            elif names_a_shipping_fact(path, selector):
                offences.append(
                    "build adapter fingerprints on the shipping fact "
                    f"{clause!r} recorded inside a shared manifest"
                )
        elif path in BUILD_EVIDENCE and not names_a_shipping_fact(path, selector):
            offences.append(
                f"distribution adapter fingerprints on build evidence {clause!r}"
            )
    return offences


def test_neither_adapter_kind_fingerprints_on_the_others_evidence():
    """The separation rule over every adapter this repository actually ships."""
    offenders = []
    for adapter, axis in [(path, "build") for path in adapter_files()] + [
        (path, "distribution") for path in distribution_files()
    ]:
        fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
        offenders += [
            f"{adapter.relative_to(REPO_ROOT)}: {offence}"
            for offence in separation_violations(fields, axis)
        ]
    assert not offenders, "the separation rule is violated:\n" + "\n".join(offenders)


def test_separation_rule_catches_a_synthetic_violation():
    """The mutation proof, now sharing its implementation with the real guard.

    No shipped adapter violates the rule, so the guard above never executes its
    failure branch. This drives `separation_violations` directly — the same
    function, not a re-typed copy of its predicate.
    """
    # Build direction: shipping evidence, at any selector and inside a conjunction.
    assert separation_violations(
        {"fingerprint": "uv.lock+.claude-plugin/plugin.json"}, "build"
    )
    assert separation_violations(
        {"fingerprint": "uv.lock+.claude-plugin/plugin.json#.version"}, "build"
    )
    assert separation_violations({"fingerprint": ".npmrc"}, "build")
    # Build direction, at selector granularity: a shipping fact inside a shared
    # manifest decides nothing about how the component builds.
    assert separation_violations(
        {"fingerprint": "pom.xml#/project/distributionManagement"}, "build"
    )
    assert separation_violations(
        {"fingerprint": "package.json#.private==false"}, "build"
    )
    # ... while the build fact in the same file is exactly what a build adapter
    # is for.
    assert not separation_violations({"fingerprint": "pom.xml"}, "build")
    assert not separation_violations(
        {"fingerprint": "pyproject.toml#tool.uv.package==false"}, "build"
    )

    # Distribution direction: a bare build-evidence path is a violation ...
    assert separation_violations({"fingerprint": "uv.lock"}, "distribution")
    assert separation_violations({"fingerprint": "pom.xml"}, "distribution")
    assert separation_violations({"fingerprint": "package.json"}, "distribution")
    # ... and so is a selector into a build-evidence file that is NOT one of the
    # single-manifest ecosystems the carve-out was justified for. This is the
    # half an unbounded `selector is None` test let through.
    assert separation_violations(
        {"fingerprint": "pyproject.toml#project.version"}, "distribution"
    )
    assert separation_violations({"fingerprint": "uv.lock#anything"}, "distribution")
    # ... but a named shipping fact inside a shared manifest is not.
    assert not separation_violations(
        {"fingerprint": "pom.xml#/project/distributionManagement"}, "distribution"
    )
    assert not separation_violations(
        {"fingerprint": "Cargo.toml#package.publish"}, "distribution"
    )
    assert not separation_violations(
        {"fingerprint": "package.json#.private==false"}, "distribution"
    )
    assert not separation_violations(
        {"fingerprint": ".claude-plugin/plugin.json"}, "distribution"
    )


def test_build_evidence_covers_the_contracts_level_one_table():
    """Two definitions of "build evidence" existed with nothing comparing them.

    Step 0 tells the agent to walk for the paths the Level 1 table names, so a
    path the table calls build evidence and this tuple omits is a path a
    distribution adapter may fingerprint with the guard silent. `package.json`
    and `build.gradle.kts` were both in that gap.
    """
    missing = sorted(
        path
        for path in level_one_fingerprints(ADAPTER_CONTRACT.read_text(encoding="utf-8"))
        if path not in BUILD_EVIDENCE
    )
    assert not missing, (
        "the contract's Level 1 table names build evidence the separation guard "
        f"does not know about: {missing}"
    )


def test_the_evidence_lists_match_the_contracts_separation_rule():
    """The rule's own prose and the tuples that enforce it, tied together."""
    text = ADAPTER_CONTRACT.read_text(encoding="utf-8")

    build = evidence_bullet_paths(text, "Build evidence")
    assert build, "the contract no longer lists its build evidence"
    assert not sorted(
        path for path in build if path not in BUILD_EVIDENCE
    ), f"contract build evidence missing from BUILD_EVIDENCE: {sorted(build)}"

    shipping = evidence_bullet_paths(text, "Shipping evidence")
    assert shipping, "the contract no longer lists its shipping evidence"
    uncovered = sorted(
        path for path in shipping if path.rstrip("/") not in SHIPPING_EVIDENCE
    )
    assert not uncovered, (
        "the contract names shipping evidence the guard does not match on, so a "
        f"build adapter may fingerprint it: {uncovered}"
    )


def test_contract_states_the_separation_rule():
    text = ADAPTER_CONTRACT.read_text(encoding="utf-8")
    assert "build evidence" in text and "shipping evidence" in text
    assert (
        "Neither may look at the other's" in text
    ), "the rule must be stated, not merely implied by the evidence lists"


def test_fingerprint_selectors_reads_both_written_forms():
    assert fingerprint_selectors("uv.lock") == ("uv.lock",)
    assert fingerprint_selectors(
        ".claude-plugin/plugin.json pyproject.toml#tool.uv.package==false"
    ) == (".claude-plugin/plugin.json", "pyproject.toml#tool.uv.package==false")
    assert fingerprint_selectors(None) == ()


def test_collision_rule_sees_a_shared_selector_inside_a_longer_list():
    """The fail-open the list form would otherwise have introduced.

    Comparing whole folded fields, `("uv", "a b")` and `("poetry", "b")` read as
    disjoint even though both are selected by `b`.
    """
    partly_overlapping = [
        ("uv", "pyproject.toml uv.lock"),
        ("poetry", "pyproject.toml"),
    ]
    assert unranked_shared_fingerprints(partly_overlapping, []) == ["poetry", "uv"]
    assert unranked_shared_fingerprints(partly_overlapping, ["uv", "poetry"]) == []
    assert unranked_shared_fingerprints(partly_overlapping, ["uv"]) == ["poetry"]


def test_contract_declares_a_selector_language_for_every_file_format():
    """Rule stated, not merely demonstrated (#100.2)."""
    text = ADAPTER_CONTRACT.read_text(encoding="utf-8")
    assert "### Selector syntax" in text, "the contract must state the selector rule"
    section = _section_after(text, "### Selector syntax")
    for language in ("jq", "dotted key path", "XPath"):
        assert language in section, f"selector table omits: {language}"
    for suffix in SELECTOR_LANGUAGE_BY_SUFFIX:
        assert suffix in section, f"selector table omits the format: {suffix}"


def test_every_adapter_selector_matches_its_file_formats_syntax():
    """Five build adapters, four distribution adapters, three selector languages.

    `selector_references` is field-set agnostic — it reads whichever of
    `version_source`, `derived_manifests`, `distribution_names` and `fingerprint`
    a given file's frontmatter carries — so a distribution adapter's
    `derived_manifests` selectors (the only place that field lives, post-split)
    get exactly the same check as a build adapter's `version_source`.

    `maven-central.md` and `crates-io.md` have no `version_source`,
    `derived_manifests` or `distribution_names` at all — a stub distribution
    adapter's only field carrying a selector is `fingerprint` itself
    (`pom.xml#/project/distributionManagement`, `Cargo.toml#package.publish`),
    and neither is a `==` predicate. `selector_references` must therefore also
    collect a bare `path#selector` fingerprint clause, not only its predicate
    form, or these two adapters would present nothing to check at all.
    """
    offenders = []
    for adapter in adapter_files() + distribution_files():
        fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
        references = selector_references(fields)
        assert references, f"{adapter.stem}: no selector references found to check"
        offenders += [
            f"{adapter.relative_to(REPO_ROOT)}: {violation}"
            for violation in map(selector_syntax_violation, references)
            if violation
        ]
    assert not offenders, "adapters misuse a selector language:\n" + "\n".join(
        offenders
    )


def test_selector_syntax_rule_catches_each_wrong_language():
    """Every branch, pinned without relying on an adapter being wrong."""
    assert selector_syntax_violation("package.json#.version") is None
    assert selector_syntax_violation("pyproject.toml#project.version") is None
    assert selector_syntax_violation("pom.xml#/project/version") is None
    assert selector_syntax_violation("galaxy.yml#.version") is None
    assert selector_syntax_violation(".claude-plugin/plugin.json#.version") is None

    # A jq selector in a TOML file, and a TOML path in a JSON file.
    assert selector_syntax_violation("pyproject.toml#.project.version") is not None
    assert selector_syntax_violation("package.json#version") is not None
    # XPath outside XML, and a dotted path inside it.
    assert selector_syntax_violation("package.json#/version") is not None
    assert selector_syntax_violation("pom.xml#project.version") is not None
    # A format with no declared language is a refusal, not an improvisation.
    assert selector_syntax_violation("Gemfile#version") is not None
    # And a reference with no selector at all is not a reference.
    assert selector_syntax_violation("uv.lock") is not None


def test_selector_references_collects_from_every_field_that_carries_one():
    fields = {
        "fingerprint": "uv.lock pyproject.toml#tool.uv.package==false",
        "version_source": "pyproject.toml#project.version",
        "derived_manifests": "a.json#.version b.json#.plugins[0].version",
        "distribution_names": "binary: pyproject.toml#project.scripts",
    }
    assert selector_references(fields) == [
        "pyproject.toml#project.version",
        "a.json#.version",
        "b.json#.plugins[0].version",
        "pyproject.toml#project.scripts",
        "pyproject.toml#tool.uv.package",
    ]

    # A bare `path#selector` fingerprint clause — no `==` predicate — is still
    # a reference: `maven-central.md` and `crates-io.md` have no other field
    # to check, and a presence-check selector deserves the same syntax check a
    # predicate gets.
    assert selector_references(
        {"fingerprint": "pom.xml#/project/distributionManagement"}
    ) == ["pom.xml#/project/distributionManagement"]
    # A bare path with no selector at all is not a reference — nothing to
    # check a selector language against.
    assert selector_references({"fingerprint": "uv.lock"}) == []
    # The null and empty-list spellings contribute nothing rather than erroring.
    assert (
        selector_references(
            {
                "fingerprint": "uv.lock",
                "version_source": "null",
                "derived_manifests": "[]",
                "distribution_names": "null",
            }
        )
        == []
    )


def test_level_two_rows_are_parsed_from_the_real_contract():
    """The rule above is only as good as this parse — pin it against the real file."""
    rows = level_two_rows(ADAPTER_CONTRACT.read_text(encoding="utf-8"))
    assert ("python", "uv-nobuild") in rows and ("python", "uv") in rows
    # Order is precedence: uv-nobuild must precede uv (this repo matches both).
    python_order = [
        toolchain for technology, toolchain in rows if technology == "python"
    ]
    assert python_order.index("uv-nobuild") < python_order.index("uv")


def all_build_declared_roles():
    """Every role any build adapter's `distribution_names` map declares.

    A distribution adapter has no map of its own and will not get one — a
    `<distribution-name:role>` token on the distribution side resolves against
    the `distribution_names` of the build adapter that resolves alongside it,
    which is where the toolchain-determined name already lives (see "Where the
    axes tangle" in the contract), so nothing is duplicated. This structural
    check has no notion of pairing — it cannot tell which build adapter
    resolves alongside a given distribution adapter — so it checks against the
    union of every build adapter's declared roles. A role missing from that
    union is a real gap regardless of pairing; a role present in the union but
    declared by the "wrong" build adapter is not something a static file-shape
    check can catch, and is the runtime core's problem, not this contract's.
    """
    roles = set()
    for adapter in adapter_files():
        fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
        roles |= declared_roles(fields.get("distribution_names"))
    return roles


def test_every_placeholder_used_by_an_adapter_is_bound_by_the_contract():
    """A token the contract does not bind is a value the agent has to guess.

    `python/uv` is a working, non-stub adapter, so this bit a real release path:
    `<tool-name>` and `<version>` were both used and neither was bound (#98).

    Because a `<distribution-name:role>` token is bound only by a role the
    adapter declares, this also enforces the contract's `null`-iff rule: a null
    `distribution_names` beside a name-using command leaves the token unbound.

    A distribution adapter has no `distribution_names` map of its own — that
    field stays on the build adapter (see "Where the axes tangle" in the
    contract). Its `<distribution-name:role>` tokens instead bind against the
    union of every build adapter's declared roles (`all_build_declared_roles`)
    — the role the build adapter that resolves alongside it declares, which a
    static per-file check cannot pair but can still verify exists somewhere.
    `npm-registry.md`, `maven-central.md` and `crates-io.md` use `package`,
    `group`/`artifact` and `crate` respectively, and all four are already
    declared by `typescript/npm`, `java/maven` and `rust/cargo` — no build
    adapter needed a new role for this.
    """
    offenders = []
    for adapter in adapter_files():
        fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
        unbound = unbound_placeholders(
            (str(fields.get(field, "")) for field in BUILD_FIELDS),
            declared_roles(fields.get("distribution_names")),
        )
        if unbound:
            offenders.append(f"{adapter.relative_to(REPO_ROOT)}: {unbound}")
    distribution_roles = all_build_declared_roles()
    for adapter in distribution_files():
        fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
        unbound = unbound_placeholders(
            (str(fields.get(field, "")) for field in DISTRIBUTION_FIELDS),
            distribution_roles,
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
        "these belong in references/build/, not the core"
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


def test_core_discovers_components_from_tracked_files_only():
    """The exclusion rule is one rule, not a skip-list.

    Only git-tracked files count as build evidence, which eliminates
    node_modules, .venv, dist, build and target in one move because all of them
    are gitignored — and stays correct as repositories change, which a hardcoded
    list would not.
    """
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8")
    assert "component" in text.lower(), "the core must name the unit it discovers"
    assert "tracked" in text.lower(), "the discovery rule must be stated"
    for skip_listed in ("node_modules", ".venv", "dist/", "target/"):
        assert skip_listed not in text, (
            f"{skip_listed!r} is a skip-list entry; the rule is tracked-files-only, "
            "and naming directories individually is what goes stale"
        )


def test_core_asks_whenever_more_than_one_component_is_found():
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8").lower()
    assert "more than one component" in text
    assert "check only" in text, "the second component kind must be named"
    assert (
        "build and release" in text
    ), "the first component kind must be named alongside it"


def test_the_two_language_refusal_moved_inside_a_component():
    """Strengthened, not weakened.

    mente-apex-memory escaped the old repo-wide refusal only because its
    package.json files happen to sit in subfolders. Scoping the refusal to a
    single component turns that accident into the rule.
    """
    text = ADAPTER_CONTRACT.read_text(encoding="utf-8")
    assert "within a component" in text, (
        "the refusal must be scoped to a component, or the repo-wide version "
        "silently forbids exactly the repositories this design exists to support"
    )


PER_COMPONENT_PHRASES = ("every component", "each component", "per component")

# Which step owns each field's loop. Anchoring here is a deliberate departure
# from the plan's literal test, on a human ruling: the plan windowed ±400
# characters around the *first* mention of each field, and `gate_command`'s first
# mention is Step 0's field list — ~2400 characters from Step 2 — so deleting
# Step 2's loop outright left that leg green.
LOOPING_STEPS = {
    "gate_command": "## Step 2 — Preflight",
    "relock_command": "## Step 5a — Refresh the lockfile",
    "build_command": "## Step 6 — Build and verify the artifacts",
}


def test_gate_relock_and_build_run_per_component():
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8")
    for field, heading in LOOPING_STEPS.items():
        # Emphasis markers are dropped so `**every** component` still reads as a
        # phrase; the rule is about the words, not how they are bolded.
        step = _section_after(text, heading).lower().replace("*", "")
        assert field in step, f"{heading} no longer reads the adapter's {field}"
        looped = [
            phrase
            for occurrence in _occurrences(step, field)
            for phrase in PER_COMPONENT_PHRASES
            if phrase in step[max(0, occurrence - 300) : occurrence + 300]
        ]
        assert looped, (
            f"{field} must be scoped to a component where {heading} runs it; a "
            "single run of it is the assumption this design removes"
        )


def _occurrences(text, needle):
    found = text.find(needle)
    while found != -1:
        yield found
        found = text.find(needle, found + 1)


def test_only_build_and_release_components_are_built():
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8").lower()
    assert "check only" in text
    assert "gate" in text
    # The distinction that must not collapse into build_command: null.
    assert "not the same as" in text or "differs from" in text, (
        "the core must say check-only is not build_command: null — one is a "
        "toolchain claim, the other a component claim"
    )


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


def test_relock_runs_between_the_stamp_and_the_commit():
    """Ordering is the whole fix.

    Refreshing the lockfile after the commit leaves the release commit carrying a
    stale lock; refreshing it before the stamp refreshes nothing. It also has to
    precede the build, which consumes the lockfile it just rewrote.
    """
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8")
    assert "## Step 5a — Refresh the lockfile" in text, "core has no relock step"
    stamp_position = text.index("## Step 5 — Stamp")
    relock_position = text.index("## Step 5a — Refresh the lockfile")
    build_position = text.index("## Step 6 — Build")
    commit_position = text.index("## Step 7 — Commit")
    assert stamp_position < relock_position < build_position < commit_position


def test_commit_step_stages_whatever_the_relock_touched():
    """A relock whose output is not staged is the original bug with extra steps:
    the lockfile is refreshed on disk and the release commit still omits it."""
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8")
    commit_step = text[text.index("## Step 7 — Commit") : text.index("## Step 8 — Tag")]
    assert (
        "relock" in commit_step
    ), "Step 7's staging rule does not mention the relock step's output"


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


def test_tag_step_states_its_precondition_before_the_command():
    """Step 8 read act-then-check: the `git tag -a` fence came first and the
    "already exists → refuse" rule sat below it. Self-protecting in practice, but
    backwards for a step whose entire purpose is a precondition (#102.1)."""
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8")
    tag_step = text[
        text.index("## Step 8 — Tag") : text.index("CONFIRMATION CHECKPOINT")
    ]
    assert (
        "already exists" in tag_step
    ), "Step 8 must carry the tag-already-exists refusal"
    assert "git tag -a" in tag_step, "Step 8 must still show the tagging command"
    assert tag_step.index("already exists") < tag_step.index(
        "git tag -a"
    ), "Step 8 states its precondition after the command it guards"


def test_commit_template_prescribes_no_literal_co_author_trailer():
    """The fenced template hardcoded one model's trailer while the sentence under
    it said to use whatever the harness prescribes. An agent copies the fence
    (#102.2), so the fence is where the placeholder has to live."""
    commit_step = RELEASE_SKILL_MD.read_text(encoding="utf-8")
    commit_step = commit_step[
        commit_step.index("## Step 7 — Commit") : commit_step.index("## Step 8 — Tag")
    ]
    assert (
        "Co-Authored-By: Claude" not in commit_step
    ), "the commit template hardcodes a trailer that outlives the model it names"
    assert (
        "co-author trailer" in commit_step
    ), "the commit template must still call for a trailer"
    assert "harness" in commit_step, "and must say where the trailer comes from"


def test_core_states_which_substitution_notation_means_what():
    """Two notations for the same two values suggested a distinction that does not
    exist: Step 1 uses `"$REMOTE"`, Step 9 and the checkpoint use `<remote>` (#102.3).
    """
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8")
    assert "## Notation" in text, "the core must state its substitution notation rule"
    notation = _section_after(text, "## Notation")
    assert (
        "$REMOTE" in notation and "<remote>" in notation
    ), "the notation rule must name both forms of the same value"
    assert (
        "bash" in notation
    ), "the rule must say which notation belongs in a shell block"


def test_checkpoint_does_not_overstate_reversibility_after_a_build():
    """`git reset --hard` does not remove untracked build output, so the flat
    "everything above was local and reversible" claimed more than the two rollback
    commands deliver (#102.4)."""
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8")
    checkpoint = text[
        text.index("CONFIRMATION CHECKPOINT") : text.index("## Step 9 — Publish")
    ]
    assert (
        "untracked" in checkpoint
    ), "the checkpoint must qualify reversibility for build output git does not track"


def test_single_literal_search_names_no_repository_specific_path():
    """Step 3 excluded `docs/superpowers/` by name — this repo's plan directory —
    from a workflow that otherwise names nothing specific to any project and is
    meant to run against the user's repo (#102.5)."""
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8")
    search_step = text[
        text.index("## Step 3 — Verify") : text.index("## Step 4 — Decide")
    ]
    assert (
        "superpowers" not in search_step
    ), "the exclusion list names a directory particular to this repository"
    for universal in ("Lockfiles", "Build output", "Documentation"):
        assert (
            universal in search_step
        ), f"exclusion list dropped a category: {universal}"


def test_step_three_checks_every_component_manifest_against_the_canonical_version():
    """The bug the old check could not see.

    Step 3 asked: of everything that says the CURRENT version, is each declared?
    That finds an undeclared copy of the current version and is blind by
    construction to a mirror pinned at an older one — which is why
    worker/package.json sat at 0.3.0 against a project at 0.4.0, unseen.

    Scoped to Step 3, a deliberate departure from the plan's literal test on the
    standing human ruling that a weak plan-verbatim guard gets strengthened rather
    than deferred (as at Tasks 2 and 7). The plan searched the whole file, where
    two of its three legs were already green before this check existed: "delete"
    from Step 8's tag rationale, and "component" 55 times over from Tasks 6-7.
    """
    step = _section_after(
        RELEASE_SKILL_MD.read_text(encoding="utf-8"), "## Step 3 — Verify"
    ).lower()
    assert "self-version" in step or "own version field" in step, (
        "the check must read each manifest's own version key, not search for a "
        "version string — a text search cannot see a stale literal"
    )
    assert "field read, not a text search" in step, (
        "Step 3 must say why it is a field read: searching for the current "
        "version string is what made an older mirror invisible"
    )
    assert "every component" in step, "the read runs over every component, not the root"
    assert "delete" in step, (
        "the refusal must name the way out: a version literal nobody reads gets "
        "deleted, not declared"
    )
    assert "#111" in step, "the published case must be named as out of scope"


def test_core_prose_lines_stay_within_the_house_width():
    """One line ran ~100 columns against the file's otherwise consistent ~95 (#102.6).

    Table rows and fenced blocks are exempt: a Markdown table row cannot wrap, and
    a wrapped command is a broken command.
    """
    house_width = 95
    offenders = []
    inside_fence = False
    for line_number, line in enumerate(
        RELEASE_SKILL_MD.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if line.lstrip().startswith("```"):
            inside_fence = not inside_fence
            continue
        if inside_fence or line.lstrip().startswith("|"):
            continue
        if len(line) > house_width:
            offenders.append(f"SKILL.md:{line_number}: {len(line)} columns")
    assert not offenders, "prose exceeds the house width:\n" + "\n".join(offenders)


def test_core_documents_the_rollback():
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8")
    assert "git tag -d" in text, "rollback must show how to delete the local tag"
    assert "git reset --hard" in text, "rollback must show how to undo the commit"


def test_core_verifies_both_the_built_thing_and_the_shipped_thing():
    """Step 10 must run both adapters' install checks, not one compound field.

    Scoped to Step 10, on the same standing ruling as Step 3's guard above: an
    unscoped scan is blind to whether these words are Step 10's own, or a
    coincidence from elsewhere in the file. "distribution adapter" and "no
    distribution adapter" both already occur in Step 0's adapter-resolution
    prose, so an unscoped version of this test would pass against the OLD
    single-command Step 10, unchanged.
    """
    step = _section_after(
        RELEASE_SKILL_MD.read_text(encoding="utf-8"), "## Step 10 — Verify"
    ).lower()
    assert "install_verify_command" in step
    assert (
        "outside" in step and "checkout" in step
    ), "the install check must require the shim to resolve outside the checkout"
    assert "distribution adapter" in step, (
        "the shipped thing is verified by its own command; folding both into one "
        "field is what made that command a compound"
    )
    assert "no distribution adapter" in step, (
        "resolving none is legitimate and the step must say so rather than "
        "failing on an absent field"
    )


def test_the_steps_that_read_distribution_fields_name_the_distribution_adapter():
    """Steps 5 and 9a read `derived_manifests` and `release_command` — both
    *distribution* fields — and both said "the adapter's", left over from the
    single-adapter contract. There is no "the adapter" any more, and in a
    repository resolving no distribution adapter (a shape Step 0 and the contract
    both bless) neither field exists to read at all.

    Scoped per step, on the standing ruling: "distribution adapter" occurs in
    Step 0's resolution prose, so an unscoped scan passes against the old text.
    """
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8")

    # Whitespace-normalised: these are wrapped prose, so a phrase the guard looks
    # for straddles a line break as often as not, and an index lookup that raises
    # instead of asserting reports the wrong thing.
    def normalised(heading):
        section = _section_after(text, heading).lower().replace("*", "")
        return " ".join(section.split())

    stamp = normalised("## Step 5 — Stamp")
    assert "derived_manifests" in stamp, "Step 5 no longer stamps the mirrors"
    assert "distribution adapter" in stamp, (
        "derived_manifests is a distribution field; naming only 'the adapter' is "
        "the axis confusion this split removed"
    )
    assert "no distribution adapter" in stamp, (
        "a repository resolving no distribution adapter has no derived manifests, "
        "and Step 5 must say it stamps version_source alone rather than failing a "
        "lookup on a field that does not exist"
    )

    release_object = normalised("## Step 9a")
    assert "release_command" in release_object, "Step 9a no longer reads the field"
    assert "no distribution adapter" in release_object, (
        "9a's skip condition read release_command off nothing when no distribution "
        "adapter resolved"
    )
    assert "`release_command` is `null`" in release_object, (
        "9a must still name the null case; it is the second skip condition, not a "
        "condition to drop"
    )
    assert release_object.index("no distribution adapter") < release_object.index(
        "`release_command` is `null`"
    ), (
        "the absent-adapter case must be the FIRST skip condition: reading `null` "
        "off an adapter that does not exist is the failure, not a second variant "
        "of the same check"
    )


# A count of contract fields, in the three shapes SKILL.md wrote one in:
# `the fourteen-field adapter contract`, `hold its fourteen contract fields`,
# `the contract stays fourteen fields wide`, `not a fifteenth contract field`.
# `one field` is deliberately not a count claim — Step 10's "folding both into one
# field" is about compounding a command, not about how wide the contract is.
_COUNT_WORD = (
    r"(?:\d+|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen"
    r"|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty"
    r"|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh"
    r"|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth|eighteenth"
    r"|nineteenth|twentieth)"
)
_FIELD_COUNT_CLAIM = re.compile(
    rf"\b{_COUNT_WORD}[- ](?:contract|adapter)[- ]?fields?\b"
    rf"|\b{_COUNT_WORD}[- ]fields?\s+wide\b"
    rf"|\b{_COUNT_WORD}-field\b",
    re.IGNORECASE,
)

NUMBER_WORDS = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
    "twenty",
]


def test_field_count_claim_rule_catches_every_shape_the_core_wrote_one_in():
    """The rule, pinned directly — including the prose it must not condemn."""
    assert _FIELD_COUNT_CLAIM.search("the fourteen-field adapter contract")
    assert _FIELD_COUNT_CLAIM.search("hold its fourteen contract fields")
    assert _FIELD_COUNT_CLAIM.search("the contract stays fourteen fields wide")
    assert _FIELD_COUNT_CLAIM.search("not a fifteenth contract field")
    assert _FIELD_COUNT_CLAIM.search("its 14 contract fields")

    assert not _FIELD_COUNT_CLAIM.search("folding both into one field is what made")
    assert not _FIELD_COUNT_CLAIM.search("those two fields sit on different axes")
    assert not _FIELD_COUNT_CLAIM.search("every later step reads through those fields")


def test_core_states_no_field_count_of_its_own():
    """The core said "fourteen" three times through the split that made it twelve
    plus five, and no test counted anything — `test_adapter_contract_documents_
    every_field` checks each name is backticked somewhere and never totals them.

    The fix is not a corrected number here: a count restated in two files rots in
    whichever one nobody edits. The contract owns the field sets, so it owns the
    count, and the core is forbidden one. The guard below pins the contract's.
    """
    offenders = []
    for line_number, line in enumerate(
        RELEASE_SKILL_MD.read_text(encoding="utf-8").splitlines(), start=1
    ):
        for match in _FIELD_COUNT_CLAIM.finditer(line):
            offenders.append(f"SKILL.md:{line_number}: {match.group(0)!r}")
    assert not offenders, (
        "the core states a contract field count, which is the contract's to state "
        "and the core's to rot:\n" + "\n".join(offenders)
    )


def test_contract_field_counts_match_the_declared_field_sets():
    """The positive counterpart: the contract *does* count, and its counts are the
    real ones. "with the twelve build adapter fields" is the sentence an author
    uses to confirm they held the right set, so it must be checked, not trusted.
    """
    text = " ".join(ADAPTER_CONTRACT.read_text(encoding="utf-8").split())
    for axis, fields in (
        ("build", BUILD_FIELDS),
        ("distribution", DISTRIBUTION_FIELDS),
    ):
        claimed = re.findall(rf"(\S+) \[{axis} adapter fields\]", text)
        assert claimed, f"the contract states no count for the {axis} adapter fields"
        expected = NUMBER_WORDS[len(fields)]
        assert set(claimed) == {expected}, (
            f"the contract calls the {axis} adapter fields {sorted(set(claimed))}; "
            f"there are {len(fields)} of them ({expected})"
        )


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
    "multi_component_repo_asks_before_proceeding",
    "plugin_manifest_never_decides_the_build",
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
    """Three cases narrate a fixture adapter at `references/build/fixture/echo.md`
    that does not exist, with an empty `files` array — against a real checkout
    Step 0's "nothing matches → refuse" fires instead of the asserted behaviour.

    Shipping the fixture for real is the wrong fix: anything under
    `references/build/` is a live adapter that detection can select during an
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
