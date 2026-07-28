# `/release` Two-Axis Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the `/release` adapter contract into build adapters and distribution adapters, and let one repository hold several build components.

**Architecture:** `references/targets/` becomes `references/build/` (how a component builds and tests) and gains a sibling `references/distributions/` (what the repository ships and how you confirm it arrived). Neither may fingerprint on the other's evidence — the rule that makes the skipped-wheel incident impossible. Detection gains a stage in front: walk git-tracked files for build evidence, proceed silently on one component, stop and ask on more than one.

**Tech Stack:** Markdown skill files with YAML frontmatter; `pytest` structural tests over them; `uv` for everything.

**Spec:** `docs/superpowers/specs/2026-07-28-release-two-axis-adapters-design.md`

## Global Constraints

- Every command runs under `uv`: `uv run pytest`, `uv run ruff check --fix .`, `uv run black .`. Never bare `python3`, never hand-activate `.venv`.
- `skills/release/SKILL.md` prose lines must stay within **95 columns**. Table rows and fenced blocks are exempt (`test_core_prose_lines_stay_within_the_house_width`).
- `skills/release/SKILL.md` must name **no** technology, forge CLI, or tag convention. `TECHNOLOGY_LITERALS`, `FORGE_CLIS` (`gh`, `glab`, `tea`), `FORGE_LITERALS`, and `TAG_CONVENTION_LITERALS` (`v<version>`, `v<new>`, `v<old>`) are all forbidden outside fenced blocks.
- The placeholder vocabulary is closed: `<remote>`, `<default>`, `<version>`, `<tag>`, `<release-notes-file>`, `<distribution-name:role>`. Any other `<…>` token fails `test_every_placeholder_used_by_an_adapter_is_bound_by_the_contract`.
- Selector language follows the **file format**, never the field: `.json`/`.yaml` → jq path (leading `.`), `.toml` → dotted key path, `.xml` → XPath (leading `/`).
- Commit messages are Conventional Commits, and carry no literal co-author trailer in templates (`test_commit_template_prescribes_no_literal_co_author_trailer`).
- Branch: `design/release-two-axis-adapters`. One PR.
- After every task: `uv run pytest tests/test_release_skill_structure.py -q` must be **green** before committing.

---

### Task 1: Rename `references/targets/` to `references/build/`

Pure rename. No field changes, no adapter content changes beyond the contract's own path prose. This isolates the churn so later diffs are readable.

**Files:**
- Rename: `skills/release/references/targets/` → `skills/release/references/build/` (6 files)
- Modify: `skills/release/references/ADAPTER-CONTRACT.md:12-22` (the "Where adapters live" section)
- Modify: `skills/release/references/ADAPTER-CONTRACT.md:439` (step 1 of "Adding an adapter")
- Test: `tests/test_release_skill_structure.py:18`, `:488-494`

**Interfaces:**
- Produces: module constant `BUILD_DIR` replacing `TARGETS_DIR`; fixture `adapter_files()` now globs `BUILD_DIR`.

- [ ] **Step 1: Point the test at the new path (this is the failing test)**

In `tests/test_release_skill_structure.py`, replace line 18:

```python
BUILD_DIR = RELEASE_SKILL_DIR / "references" / "build"
```

Then replace every `TARGETS_DIR` occurrence with `BUILD_DIR` (5 sites: the constant, `adapter_files()`, `test_git_tag_only_adapter_stamps_all_three_version_mirrors`, `test_uv_adapter_verifies_a_real_artifact_pattern`, and `adapters_by_technology()`). Update the docstring and assertion message in `adapter_files()`:

```python
def adapter_files():
    """Every build adapter under references/build/, recursively, sorted."""
    return sorted(BUILD_DIR.rglob("*.md"))
```

```python
    assert adapters, "no adapters found under references/build/"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_release_skill_structure.py -q`
Expected: FAIL — `assert adapters, "no adapters found under references/build/"`, because the directory does not exist yet.

- [ ] **Step 3: Move the directory**

```bash
git mv skills/release/references/targets skills/release/references/build
```

- [ ] **Step 4: Update the contract's path prose**

In `ADAPTER-CONTRACT.md`, the "Where adapters live" fenced block becomes:

```
references/build/<technology>/<toolchain>.md
```

And in "Adding an adapter", step 1's opening becomes:

```markdown
1. Create `references/build/<technology>/<toolchain>.md` with all fourteen fields.
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_release_skill_structure.py -q`
Expected: PASS, all 71 tests.

- [ ] **Step 6: Commit**

```bash
git add -A skills/release/references tests/test_release_skill_structure.py
git commit -m "refactor(release): rename references/targets to references/build

Pure rename ahead of the axis split. The word 'target' never said which
axis it named, which is the ambiguity that let a plugin manifest decide a
build question.

Refs #109"
```

---

### Task 2: Add the distribution adapter and split the field sets

The axis split. Distribution fields leave the build adapters and land in `references/distributions/claude-plugin.md`.

**Files:**
- Create: `skills/release/references/distributions/claude-plugin.md`
- Modify: `skills/release/references/build/python/git-tag-only.md` (frontmatter)
- Modify: `skills/release/references/build/python/uv-plugin.md` (frontmatter)
- Modify: `skills/release/references/build/python/uv.md`, `typescript/npm.md`, `java/maven.md`, `rust/cargo.md` (frontmatter)
- Modify: `skills/release/references/ADAPTER-CONTRACT.md:23-55` (the fourteen-field table)
- Test: `tests/test_release_skill_structure.py:22-37`, `:492-501`, `:522-547`

**Interfaces:**
- Consumes: `BUILD_DIR`, `adapter_files()` from Task 1.
- Produces: `DISTRIBUTIONS_DIR`, `BUILD_FIELDS`, `DISTRIBUTION_FIELDS`, `distribution_files()`.

**Field allocation** (from the spec, including the two tangles it resolves):

| Build adapter | Distribution adapter |
|---|---|
| `technology`, `toolchain`, `fingerprint` | `kind`, `fingerprint` |
| `version_source` | `derived_manifests` |
| `relock_command`, `gate_command` | `install_verify_command` |
| `build_command`, `artifact_pattern` | `release_command` |
| `distribution_names` | |
| `install_verify_command` | |
| `tag_pattern`, `publish_command` | |

`distribution_names` stays on the **build adapter** despite its name — every value it holds is a toolchain-determined path. `install_verify_command` appears on **both**, and both run: the build one proves what was built installs, the distribution one proves what shipped arrived.

- [ ] **Step 1: Write the failing test**

In `tests/test_release_skill_structure.py`, replace the `CONTRACT_FIELDS` tuple (lines 22-37) with two tuples, and add the distributions constant next to `BUILD_DIR`:

```python
DISTRIBUTIONS_DIR = RELEASE_SKILL_DIR / "references" / "distributions"

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
```

Replace `test_every_adapter_declares_all_contract_fields` with two tests:

```python
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
        extra = [field for field in DISTRIBUTION_FIELDS if field in fields
                 and field not in BUILD_FIELDS]
        if missing:
            offenders.append(f"{adapter.relative_to(REPO_ROOT)}: missing {missing}")
        if extra:
            offenders.append(
                f"{adapter.relative_to(REPO_ROOT)}: carries distribution fields "
                f"{extra} — those belong in references/distributions/"
            )
    assert not offenders, "build adapters violate the contract:\n" + "\n".join(offenders)


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
    assert not offenders, (
        "distribution adapters violate the contract:\n" + "\n".join(offenders)
    )
```

Then update `test_adapter_contract_documents_every_field` (line 458) to iterate `BUILD_FIELDS + DISTRIBUTION_FIELDS` instead of `CONTRACT_FIELDS`.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_release_skill_structure.py -q`
Expected: FAIL — `no adapters found under references/distributions/`, plus `carries distribution fields` for all six build adapters.

- [ ] **Step 3: Create the distribution adapter**

Create `skills/release/references/distributions/claude-plugin.md`:

```markdown
---
kind: claude-plugin
fingerprint: .claude-plugin/plugin.json
derived_manifests:
  - .claude-plugin/plugin.json#.version
  - .claude-plugin/marketplace.json#.plugins[0].version?
install_verify_command: claude plugin list
release_command: gh release create <tag> --title <tag> --notes-file <release-notes-file>
---

# claude-plugin

A repository that ships a Claude Code plugin manifest. The manifest tells the marketplace
which version to load, so it must be stamped in lockstep with whatever the build adapter
declares canonical — never lead it.

## Why the manifest is stamped and never canonical

`uv build` reads `[project].version` and bakes it into the wheel filename and its metadata,
so a version the plugin manifest led would be a version the build ignores. The stamp
direction follows whatever the toolchain actually reads.

Where the build adapter builds nothing (`python/uv-nobuild`), no toolchain reads either
literal, and the direction becomes a free choice. It still resolves the same way, so the
rule stays uniform: the build adapter always supplies `version_source`, and this file is
always downstream of it.

## `marketplace.json` is optional, and the `?` is load-bearing

A plugin repository that is also its own marketplace source carries a third mirror; one
publishing through somebody else's marketplace carries two. Both are this kind. Required-
and-absent would fail the stamp on the second; omitted entirely would let the third
mirror's literal read as undeclared drift and refuse at Step 3, mid-release, after the
gate. The marker is the only form under which both release correctly.

`plugin.json` has no `?` on purpose — a repository of this shape without one is not this
shape at all, and the strict entry is what says so.

## Verifying

`claude plugin list` must show the version just cut. A list still showing the previous
version is a consumer-side marketplace cache, not a failed release — the tag and the
manifests are correct, and the report says so. A *wheel* at the previous version is the
opposite: a real failure, and the one the axis split exists to make impossible.
```

- [ ] **Step 4: Strip distribution fields from the six build adapters**

From each file in `skills/release/references/build/`, delete the `derived_manifests` and `release_command` frontmatter keys. Leave `install_verify_command` in place — it is on both field sets.

`git-tag-only.md` additionally flips its version arrow, per the spec:

```yaml
version_source: pyproject.toml#project.version
```

(Its `derived_manifests` entries move wholesale to `claude-plugin.md`, already written in Step 3.)

- [ ] **Step 5: Update the contract's field table**

In `ADAPTER-CONTRACT.md`, replace the single "The fourteen fields" table with two tables under headings `## Build adapter fields` and `## Distribution adapter fields`, using the allocation table above. Add a `### Where the axes tangle` subsection carrying the `distribution_names` and dual-`install_verify_command` reasoning verbatim from the spec.

- [ ] **Step 6: Retarget the stamping test**

Replace `test_git_tag_only_adapter_stamps_all_three_version_mirrors` (line 522) with:

```python
def test_claude_plugin_distribution_stamps_both_manifest_mirrors():
    """This repo's own distribution adapter must name every manifest the guard checks."""
    adapter = DISTRIBUTIONS_DIR / "claude-plugin.md"
    assert adapter.is_file(), "the dogfooded distribution adapter must exist"
    fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
    # Read the parsed fields, never the file text. A substring search is satisfied
    # by body prose that *discusses* these paths, and this adapter's prose names
    # every one of them.
    declared = {
        split_optional_marker(entry)[0].partition("#")[0]
        for entry in str(fields.get("derived_manifests") or "").split()
    }
    assert declared == {
        ".claude-plugin/plugin.json",
        ".claude-plugin/marketplace.json",
    }, f"both plugin mirrors must be stamped; got {sorted(declared)}"
    assert "status" not in fields, "the dogfooded adapter is not a stub"


def test_the_no_build_adapter_makes_the_build_manifest_canonical():
    """The version arrow points out of the build adapter, with no exception.

    git-tag-only previously made .claude-plugin/plugin.json canonical while
    uv-plugin made pyproject.toml canonical — a disagreement about direction that
    reopened the axis tangle. Nothing reads either literal when there is no build,
    so the direction is free, and uniform beats faithful.
    """
    adapter = BUILD_DIR / "python" / "git-tag-only.md"
    fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
    assert fields.get("version_source") == "pyproject.toml#project.version"
    assert fields.get("build_command") == "null", "a package = false target builds nothing"
    assert fields.get("artifact_pattern") == "null", "no build means no artifact pattern"
```

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/test_release_skill_structure.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add -A skills/release/references tests/test_release_skill_structure.py
git commit -m "feat(release): split the adapter contract into build and distribution

derived_manifests, release_command and the shipped-thing verification move
to references/distributions/. distribution_names stays on the build adapter
despite its name — every value it holds is a toolchain-determined path.
install_verify_command lands on both and both run.

git-tag-only's version arrow flips: pyproject.toml is now canonical and the
plugin manifest derived. Nothing reads either literal when there is no
build, so the direction is free, and a uniform rule beats a faithful one.

Refs #109"
```

---

### Task 3: Delete `python/uv-plugin`, rename `git-tag-only` to `uv-nobuild`

Fills the empty square in the Python grid: a repository that builds nothing and ships nothing but a tag is now a build adapter with no distribution adapter, rather than a dead end.

**Files:**
- Delete: `skills/release/references/build/python/uv-plugin.md`
- Rename: `skills/release/references/build/python/git-tag-only.md` → `uv-nobuild.md`
- Modify: `skills/release/references/ADAPTER-CONTRACT.md:392-424` (Level 2 table and its prose)
- Modify: `README.md` (skills table adapter rows)
- Test: `tests/test_release_skill_structure.py:67-91`, `:981-1006`, `:1624-1642`

**Interfaces:**
- Consumes: `BUILD_FIELDS`, `DISTRIBUTIONS_DIR` from Task 2.
- Produces: adapter identity `python/uv-nobuild`; identity `python/uv-plugin` no longer exists.

- [ ] **Step 1: Write the failing test**

Update `ADAPTER_CLASSIFICATIONS` (line 67) — drop `uv-plugin`, rename `git-tag-only`:

```python
ADAPTER_CLASSIFICATIONS = {
    "python/uv-nobuild": "working",
    "python/uv": "working",
    "typescript/npm": "stub",
    "java/maven": "stub",
    "rust/cargo": "stub",
}
```

Update `LOCKFILE_CARRIES_OWN_VERSION` (line 86) — same rename:

```python
LOCKFILE_CARRIES_OWN_VERSION = (
    "python/uv-nobuild",
    "python/uv",
    "typescript/npm",
    "rust/cargo",
)
```

Replace `test_the_package_false_case_resolves_to_exactly_one_adapter` (line 981) with:

```python
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


def test_no_build_adapter_fingerprints_on_a_plugin_manifest():
    """The concrete regression: mente-apex-memory's skipped wheel.

    `.claude-plugin/plugin.json` is shipping evidence. It was a git-tag-only
    fingerprint entry, so it decided `build_command: null` for a repository that
    builds a wheel perfectly well, and the release cut a tag without one.
    """
    offenders = []
    for adapter in adapter_files():
        fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
        if ".claude-plugin" in str(fields.get("fingerprint", "")):
            offenders.append(str(adapter.relative_to(REPO_ROOT)))
    assert not offenders, (
        "build adapters fingerprinting on shipping evidence:\n" + "\n".join(offenders)
    )
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_release_skill_structure.py -q`
Expected: FAIL — `test_every_adapter_is_classified_exactly_once` reports `python/git-tag-only` and `python/uv-plugin` as unclassified, and `rowed[("python", "uv-nobuild")]` raises `KeyError`.

- [ ] **Step 3: Delete and rename**

```bash
git rm skills/release/references/build/python/uv-plugin.md
git mv skills/release/references/build/python/git-tag-only.md \
       skills/release/references/build/python/uv-nobuild.md
```

- [ ] **Step 4: Update the renamed adapter's frontmatter and prose**

In `uv-nobuild.md`, set `toolchain: uv-nobuild` and `fingerprint: pyproject.toml#tool.uv.package==false`. Retitle the body `# python / uv-nobuild` and rewrite its opening to state what it now claims: a uv-managed project that deliberately builds no wheel. Delete any prose asserting that the plugin manifest is canonical — Task 2 flipped that arrow.

- [ ] **Step 5: Update the Level 2 table**

In `ADAPTER-CONTRACT.md`, the python rows become two:

```markdown
| `python` | `pyproject.toml#tool.uv.package==false` | `uv-nobuild` |
| `python` | `uv.lock` | `uv` |
```

Rewrite the following prose (currently three numbered points about narrowing order) to two, and delete the "Row 2 is the one that was missing" paragraph — that row is gone, and its lesson is now carried by the separation rule instead. Add a `### Distribution detection` subsection stating that distribution adapters resolve by shipping evidence at the repository root, and that resolving none is legitimate.

- [ ] **Step 6: Update the README skills table**

Replace the `python/uv-plugin` and `python/git-tag-only` rows with a single `python/uv-nobuild` row, and add a row naming `distributions/claude-plugin`. Match the existing row format exactly — `test_readme_skills_table_row_documents_every_adapter` parses it.

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/test_release_skill_structure.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add -A skills/release/references tests/test_release_skill_structure.py README.md
git commit -m "feat(release): dissolve uv-plugin, rename git-tag-only to uv-nobuild

The three python adapters were a 2x2 with a hole. Factoring the axes fills
it: a package = false repo with no plugin manifest is now a build adapter
with no distribution adapter, rather than a fingerprint match that refuses
at the version_source check.

Refs #109"
```

---

### Task 4: Pin the separation rule in both directions

Task 3 added the build-side half opportunistically. This makes it a general, symmetric rule with the evidence sets named.

**Files:**
- Modify: `skills/release/references/ADAPTER-CONTRACT.md` (new section after the field tables)
- Test: `tests/test_release_skill_structure.py`

**Interfaces:**
- Consumes: `adapter_files()`, `distribution_files()`.
- Produces: `BUILD_EVIDENCE`, `SHIPPING_EVIDENCE`.

- [ ] **Step 1: Write the failing test**

Add near the other constants:

```python
# The separation rule. A build adapter may fingerprint only on build evidence; a
# distribution adapter only on shipping evidence; neither may look at the other's.
#
# This is what makes the skipped-wheel incident impossible rather than patched.
# `.claude-plugin/plugin.json` is shipping evidence, and it was deciding
# `build_command: null` for a repository with a setuptools backend and a console
# script — one that builds a wheel perfectly well. Adding a fourth adapter filled
# in the missing square; it did not remove the cause.
BUILD_EVIDENCE = (
    "uv.lock",
    "package-lock.json",
    "Cargo.lock",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    "pyproject.toml",
    "setup.py",
)
SHIPPING_EVIDENCE = (".claude-plugin",)
```

And the symmetric test:

```python
def _fingerprint_paths(fields):
    """Every bare path named by a fingerprint, predicates and conjunctions unwrapped."""
    paths = set()
    for entry in fingerprint_selectors(str(fields.get("fingerprint", ""))):
        for clause in fingerprint_clauses(entry):
            paths.add(clause.partition("#")[0])
    return paths


def test_neither_adapter_kind_fingerprints_on_the_others_evidence():
    offenders = []
    for adapter in adapter_files():
        fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
        for path in _fingerprint_paths(fields):
            if any(path.startswith(marker) for marker in SHIPPING_EVIDENCE):
                offenders.append(
                    f"{adapter.relative_to(REPO_ROOT)}: build adapter fingerprints "
                    f"on shipping evidence {path!r}"
                )
    for adapter in distribution_files():
        fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
        for path in _fingerprint_paths(fields):
            if path in BUILD_EVIDENCE:
                offenders.append(
                    f"{adapter.relative_to(REPO_ROOT)}: distribution adapter "
                    f"fingerprints on build evidence {path!r}"
                )
    assert not offenders, "the separation rule is violated:\n" + "\n".join(offenders)


def test_separation_rule_catches_a_synthetic_violation():
    """The rule must be observable, or it is decoration."""
    plugin_fingerprinted_build = {"fingerprint": "uv.lock+.claude-plugin/plugin.json"}
    paths = _fingerprint_paths(plugin_fingerprinted_build)
    assert any(path.startswith(".claude-plugin") for path in paths)

    lock_fingerprinted_distribution = {"fingerprint": "uv.lock"}
    assert "uv.lock" in _fingerprint_paths(lock_fingerprinted_distribution)


def test_contract_states_the_separation_rule():
    text = ADAPTER_CONTRACT.read_text(encoding="utf-8")
    assert "build evidence" in text and "shipping evidence" in text
    assert (
        "Neither may look at the other's" in text
    ), "the rule must be stated, not merely implied by the evidence lists"
```

Then delete `test_no_build_adapter_fingerprints_on_a_plugin_manifest` from Task 3 — this pair supersedes it.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_release_skill_structure.py -q`
Expected: FAIL on `test_contract_states_the_separation_rule` — the contract has no such section yet.

- [ ] **Step 3: Write the contract section**

Add after the two field tables in `ADAPTER-CONTRACT.md`:

```markdown
### The separation rule

> A build adapter may fingerprint only on **build evidence**. A distribution adapter may
> fingerprint only on **shipping evidence**. Neither may look at the other's.

- **Build evidence** — `uv.lock`, `package-lock.json`, `Cargo.lock`, `Cargo.toml`,
  `pom.xml`, `build.gradle`, `pyproject.toml`, `setup.py`, and predicates over them such
  as `pyproject.toml#tool.uv.package==false`.
- **Shipping evidence** — `.claude-plugin/plugin.json`, registry configuration, publish
  targets.

**This rule exists because the contract already walked into the failure it warned about.**
`.claude-plugin/plugin.json` — a fact about what ships — was a `git-tag-only` fingerprint
entry, so it decided a question about how a repository builds. The answer it produced,
`build_command: null`, was wrong: that repository has a setuptools backend and a console
script and builds a wheel perfectly well. `/release` cut a tag and never built it.

The release survived only because that project installs from source at the tag, so nothing
consumed the wheel that was never built. The safety came from an unrelated implementation
detail, not from this contract.

Adding a fourth adapter filled in the missing square. It did not remove the cause. Under
this rule the manifest has no path by which to reach `build_command`, which is a stronger
claim than "the missing adapter now exists".
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_release_skill_structure.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A skills/release/references tests/test_release_skill_structure.py
git commit -m "feat(release): pin the fingerprint separation rule in both directions

Build adapters may fingerprint only on build evidence, distribution
adapters only on shipping evidence. This is what makes the skipped-wheel
incident impossible rather than patched.

Refs #109"
```

---

### Task 5: Stub distribution adapters for npm, maven and cargo

Their build halves are already `status: stub`; their shipping halves inherit it.

**Files:**
- Create: `skills/release/references/distributions/npm-registry.md`
- Create: `skills/release/references/distributions/maven-central.md`
- Create: `skills/release/references/distributions/crates-io.md`
- Test: `tests/test_release_skill_structure.py:67-80`, `:870-886`

**Interfaces:**
- Consumes: `DISTRIBUTION_FIELDS`, `distribution_files()`.
- Produces: distribution identities `npm-registry`, `maven-central`, `crates-io`.

- [ ] **Step 1: Write the failing test**

Extend `ADAPTER_CLASSIFICATIONS` with the distribution kinds, keyed by `distributions/<kind>` so build and distribution identities cannot collide:

```python
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
```

Update `adapter_identities()` (line 848) to yield distribution identities too:

```python
def adapter_identities():
    identities = {
        f"{adapter.parent.name}/{adapter.stem}": adapter for adapter in adapter_files()
    }
    identities.update(
        {f"distributions/{adapter.stem}": adapter for adapter in distribution_files()}
    )
    return identities
```

`test_every_adapter_is_classified_exactly_once` and `test_stub_adapters_are_marked_and_working_ones_are_not` both consume `adapter_identities()` and need no further change.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_release_skill_structure.py -q`
Expected: FAIL — `test_every_adapter_is_classified_exactly_once` reports three classified identities with no file.

- [ ] **Step 3: Create the three stubs**

`skills/release/references/distributions/npm-registry.md`:

```markdown
---
kind: npm-registry
status: stub
fingerprint: package.json#.private==false
derived_manifests: null
install_verify_command: npm view <distribution-name:package> version
release_command: gh release create <tag> --title <tag> --notes-file <release-notes-file>
---

# npm-registry

Sketched, never exercised. `status: stub` means exactly that, and the core refuses to run
against it — see the contract's `status: stub` section for why "cut a release with it
first" cannot be the exit condition.

`derived_manifests` is `null` because `package.json` is the build adapter's
`version_source`, not a mirror of something else.

**Unverified:** the `npm view` flags, and whether `#.private==false` is the right
fingerprint or whether the absence of the key should also match.
```

`skills/release/references/distributions/maven-central.md`:

```markdown
---
kind: maven-central
status: stub
fingerprint: pom.xml#/project/distributionManagement
derived_manifests: null
install_verify_command: mvn dependency:get -Dartifact=<distribution-name:group>:<distribution-name:artifact>:<version>
release_command: gh release create <tag> --title <tag> --notes-file <release-notes-file>
---

# maven-central

Sketched, never exercised. See the contract's `status: stub` section.

**Unverified:** whether `distributionManagement` is present in every repository that
publishes to Central, and whether `dependency:get` is the right reachability check given
Central's sync delay.
```

`skills/release/references/distributions/crates-io.md`:

```markdown
---
kind: crates-io
status: stub
fingerprint: Cargo.toml#package.publish
derived_manifests: null
install_verify_command: cargo install <distribution-name:crate> --version <version>
release_command: gh release create <tag> --title <tag> --notes-file <release-notes-file>
---

# crates-io

Sketched, never exercised. See the contract's `status: stub` section.

**Unverified:** the fingerprint is inverted from what it should probably be —
`package.publish` is usually present only to *disable* publishing (`publish = false`), so
this likely needs a predicate rather than a presence check. Resolve it by running the
thing, not by reasoning about it.
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_release_skill_structure.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A skills/release/references tests/test_release_skill_structure.py
git commit -m "feat(release): add stub distribution adapters for npm, maven and cargo

Their build halves are already stubs; the shipping halves inherit it. Each
names what specifically is unverified rather than claiming inheritance from
a verified sibling covers it.

Refs #109"
```

---

### Task 6: Component discovery in Step 0

**Files:**
- Modify: `skills/release/SKILL.md:64-105` (Step 0)
- Modify: `skills/release/references/ADAPTER-CONTRACT.md` (Detection section, new stage 1)
- Test: `tests/test_release_skill_structure.py`

**Interfaces:**
- Consumes: the two-kind adapter model from Tasks 2-5.
- Produces: the vocabulary `component`, `build and release`, `check only` in both files.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_release_skill_structure.py -q`
Expected: FAIL — `the core must name the unit it discovers`.

- [ ] **Step 3: Rewrite Step 0**

In `SKILL.md`, Step 0 becomes "Resolve the components and the distribution". Keep every existing refusal (`status: stub`, absent `version_source` file, no toolchain matches, no technology matches) and add the discovery stages. Prose must stay within 95 columns and name no technology. The confirmation block, in a fence (fences are exempt from both the width and the technology-literal checks):

```
Found 3 components:
  .              python/uv        build and release
  dashboard/web  typescript/vite  check only
  worker         typescript/npm   check only
Correct?
```

State the three rules in prose: only git-tracked files count as build evidence; one component proceeds silently; more than one stops and asks. State that the root component supplies `tag_pattern` and `publish_command`, and that resolving no distribution adapter is legitimate.

- [ ] **Step 4: Add the detection stage to the contract**

In `ADAPTER-CONTRACT.md`'s Detection section, add `### Stage 1 — components` before the existing Level 1, and change Level 1's multi-technology refusal to read *"More than one technology matches **within a component** → ask the user"*, with a sentence explaining that scoping it to a component is what turns `mente-apex-memory`'s accidental escape into the rule.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_release_skill_structure.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A skills/release tests/test_release_skill_structure.py
git commit -m "feat(release): discover components and ask when there is more than one

Only git-tracked files count as build evidence — one rule rather than a
skip-list that goes stale. One component proceeds silently, which is every
repository today; more than one stops and asks.

The two-language refusal moves inside a component, which strengthens it:
what mente-apex-memory escaped by accident becomes the rule.

Refs #109"
```

---

### Task 7: Loop the gate, relock and build steps

**Files:**
- Modify: `skills/release/SKILL.md:170-181` (Step 2, gate)
- Modify: `skills/release/SKILL.md:282-314` (Step 5a, relock)
- Modify: `skills/release/SKILL.md:315-344` (Step 6, build)
- Test: `tests/test_release_skill_structure.py`

**Interfaces:**
- Consumes: the component list from Task 6.

- [ ] **Step 1: Write the failing test**

```python
def test_gate_relock_and_build_run_per_component():
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8").lower()
    for field in ("gate_command", "relock_command", "build_command"):
        window = text[text.index(field) - 400 : text.index(field) + 400]
        assert "component" in window, (
            f"{field} must be scoped to a component; a single run of it is the "
            "assumption this design removes"
        )


def test_only_build_and_release_components_are_built():
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8").lower()
    assert "check only" in text
    assert "gate" in text
    # The distinction that must not collapse into build_command: null.
    assert "not the same as" in text or "differs from" in text, (
        "the core must say check-only is not build_command: null — one is a "
        "toolchain claim, the other a component claim"
    )
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_release_skill_structure.py -q`
Expected: FAIL — `gate_command must be scoped to a component`.

- [ ] **Step 3: Rewrite the three steps**

Step 2 gates **every** component in the order listed, reporting which one failed. Step 5a relocks every component whose `relock_command` is non-`null`. Step 6 builds only components marked *build and release*, and expands `artifact_pattern` per component.

Add a short paragraph to Step 2 stating that check-only is a **component** claim ("this release is not building me") and is not the same as `build_command: null`, which is a **toolchain** claim ("this toolchain builds nothing, ever").

Preserve the existing ordering guarantees — `test_stamp_precedes_commit_which_precedes_tag` and `test_relock_runs_between_the_stamp_and_the_commit` both still apply.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_release_skill_structure.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A skills/release/SKILL.md tests/test_release_skill_structure.py
git commit -m "feat(release): gate, relock and build every component

Gate runs across all components; build runs only for those marked build and
release. Check-only is a component claim and is not build_command: null,
which is a toolchain claim — different statements at different levels.

Refs #109"
```

---

### Task 8: The version check that catches a stale mirror

**Files:**
- Modify: `skills/release/SKILL.md:182-230` (Step 3)
- Test: `tests/test_release_skill_structure.py:1477-1493`

**Interfaces:**
- Consumes: the component list from Task 6.

- [ ] **Step 1: Write the failing test**

```python
def test_step_three_checks_every_component_manifest_against_the_canonical_version():
    """The bug the old check could not see.

    Step 3 asked: of everything that says the CURRENT version, is each declared?
    That finds an undeclared copy of the current version and is blind by
    construction to a mirror pinned at an older one — which is why
    worker/package.json sat at 0.3.0 against a project at 0.4.0, unseen.
    """
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8").lower()
    assert "self-version" in text or "own version field" in text, (
        "the check must read each manifest's own version key, not search for a "
        "version string — a text search cannot see a stale literal"
    )
    assert "component" in text
    assert "delete" in text, (
        "the refusal must name the way out: a version literal nobody reads gets "
        "deleted, not declared"
    )
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_release_skill_structure.py -q`
Expected: FAIL — `the check must read each manifest's own version key`.

- [ ] **Step 3: Rewrite Step 3**

Keep the existing single-literal check for the root component's declared manifests. Add: for every component, read its manifest's own version key (`.version` in a JSON manifest, `project.version` in a TOML one — expressed generically, since the core names no technology) and compare to the canonical version. A mismatch refuses, and the message names the two ways out:

1. Nothing consumes it → delete the field.
2. Something consumes it → that component is published, which is issue #111.

State explicitly that this is not a text search, and why: searching for the current version string is what made a mirror pinned at an older version invisible.

`test_single_literal_search_names_no_repository_specific_path` still applies — name no paths.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_release_skill_structure.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A skills/release/SKILL.md tests/test_release_skill_structure.py
git commit -m "feat(release): check every component manifest against the canonical version

The old check asked whether every literal equal to the CURRENT version was
declared, so it was blind by construction to a mirror pinned at an older
one. Reading each manifest's own version key catches it.

Refs #109, #111"
```

---

### Task 9: Dual install-verify in Step 10

**Files:**
- Modify: `skills/release/SKILL.md:499-520` (Step 10)
- Test: `tests/test_release_skill_structure.py:1522-1529`

**Interfaces:**
- Consumes: `install_verify_command` on both adapter kinds, from Task 2.

- [ ] **Step 1: Write the failing test**

Replace `test_core_verifies_the_install_not_just_the_build` (line 1522) with the wider version — the old name goes, its two assertions are carried forward:

```python
def test_core_verifies_both_the_built_thing_and_the_shipped_thing():
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8").lower()
    assert "install_verify_command" in text
    assert (
        "outside" in text and "checkout" in text
    ), "the install check must require the shim to resolve outside the checkout"
    assert "distribution adapter" in text, (
        "the shipped thing is verified by its own command; folding both into one "
        "field is what made that command a compound"
    )
    assert "no distribution adapter" in text, (
        "resolving none is legitimate and the step must say so rather than "
        "failing on an absent field"
    )
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_release_skill_structure.py -q`
Expected: FAIL — `the shipped thing is verified by its own command`.

- [ ] **Step 3: Rewrite Step 10**

Run the root component's build adapter `install_verify_command` first, then the distribution adapter's if one resolved. Keep the shim-outside-the-checkout requirement. State that a repository resolving no distribution adapter runs only the first, and that this is not a degraded release.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_release_skill_structure.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A skills/release/SKILL.md tests/test_release_skill_structure.py
git commit -m "feat(release): verify the built thing and the shipped thing separately

Two checks of two different things, which is why that command was a
compound. A repo resolving no distribution adapter runs only the first.

Refs #109"
```

---

### Task 10: Evals, contract housekeeping, and the full green run

**Files:**
- Modify: `evals/release-evals.json`
- Modify: `skills/release/references/ADAPTER-CONTRACT.md` (the "Adding an adapter" section)
- Test: `tests/test_release_skill_structure.py:1533-1543`

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Write the failing test**

Add to `REQUIRED_EVAL_NAMES` (line 1533):

```python
    "multi_component_repo_asks_before_proceeding",
    "plugin_manifest_never_decides_the_build",
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_release_skill_structure.py -q`
Expected: FAIL — `test_release_evals_cover_every_required_scenario` reports both names missing.

- [ ] **Step 3: Add the two eval cases**

Add to `evals/release-evals.json`, matching the existing schema exactly (`id`, `skill`, `prompt`, `expected_output`, `assertions`). The first asserts that a repository with build evidence in three directories stops and lists them before doing anything. The second asserts that a repository with both `uv.lock` and `.claude-plugin/plugin.json` resolves a build adapter that builds, never one that skips the build — the regression case.

Mark any case narrating a fixture as illustrative, per `test_cases_narrating_a_fixture_declare_themselves_illustrative`.

- [ ] **Step 4: Update "Adding an adapter"**

Rewrite the numbered list to cover both kinds: which field set applies, that the separation rule constrains the fingerprint, and that a new distribution kind needs no Level 1 or Level 2 row because distribution detection has no precedence table — it matches shipping evidence directly, and resolving none is legitimate.

Update the closing line, which currently reads "with all fourteen fields", to name the two field sets.

- [ ] **Step 5: Full verification**

```bash
uv run pytest -q
uv run ruff check --fix .
uv run black .
uv run pytest -q
```

Expected: all green, no ruff findings, black reports no reformatting on the second run.

- [ ] **Step 6: Verify the skill still releases this repository**

This repository is now `python/uv-nobuild` + `distributions/claude-plugin`. Confirm by hand, without cutting a release:

```bash
grep -n 'version' pyproject.toml .claude-plugin/plugin.json .claude-plugin/marketplace.json
```

Expected: all three carry the same version. `pyproject.toml` is now the canonical one and the other two are derived — the reverse of before this branch, with the same values.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(release): cover components and the separation rule in evals

Adds the regression case directly: a repo with both a lockfile and a plugin
manifest must resolve a build adapter that builds. That is the release that
cut a tag without a wheel.

Closes #109"
```

---

## Follow-up, not in this PR

- **`mente-apex-memory`** — becomes `python/uv` + `claude-plugin` + two check-only components, and `worker/package.json` loses its version field. Its own repository, its own issue.
- **The component machinery is unexercised** until run against `mente-apex-memory` for real. `status: stub` does not apply — it is not an adapter — but the contract must not claim the machinery works before then, per its own rule that the exit from unexercised is exercising it.
- **[#111](https://github.com/menteapex/mente-apex-plugin/issues/111)** — publishing several components to several registries under one tag. `publish_command` stays a field a component *could* carry, so this stays open.
