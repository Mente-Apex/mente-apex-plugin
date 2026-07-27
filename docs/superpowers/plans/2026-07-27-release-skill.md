# `/release` Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/release` skill owning the gate → stamp → build → tag → publish → verify-install pipeline, with a technology/toolchain adapter seam that makes adding a release target a new file rather than an edit to the core.

**Architecture:** A target-agnostic `SKILL.md` depends only on a ten-field adapter contract defined once in `ADAPTER-CONTRACT.md`. Concrete adapters live under `references/targets/<technology>/<toolchain>.md`, resolved by two-level fingerprint detection at Step 0 — the single injection point. A structural test asserts the core contains no technology-specific literal, so extending by editing the core fails CI.

**Tech Stack:** Authored Markdown skills (no runtime code), pytest structural guards, `uv` for the environment, `gh` for GitHub operations.

**Spec:** [`docs/superpowers/specs/2026-07-27-release-skill-design.md`](../specs/2026-07-27-release-skill-design.md)
**Issue:** [#93](https://github.com/menteapex/mente-apex-plugin/issues/93)

## Global Constraints

- **Python is managed by `uv`.** Every command in this plan runs as `uv run <cmd>`. Never `pip`, `pipx`, `pyenv`, Homebrew/system Python, or a hand-activated `.venv`.
- **Full gate before every commit:** `uv run pytest && uv run ruff check . && uv run black --check .`. Never commit with outstanding lint.
- **Tests are dependency-free.** No PyYAML — frontmatter is parsed with the `re`-based helper copied in Task 2. This matches every existing `test_*_skill_structure.py`.
- **Skill frontmatter keys** required by house style: `name`, `description`, `user-invocable: true`, `disable-model-invocation: true`, `allowed-tools`, `metadata.version`.
- **`metadata.version` starts at `"0.1.0"`** and is asserted with a *floor*, never an equality — use `assert_version_at_least(frontmatter_text, (0, 1, 0))` from `tests/skill_version_policy.py`.
- **Conventional Commits** for every commit subject: `type(scope): summary`.
- **Every commit ends with:** `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`
- **Never commit to `main`.** All work happens on the branch created in Task 0.
- **The ten contract fields, verbatim and in this order:** `technology`, `toolchain`, `fingerprint`, `version_source`, `derived_manifests`, `gate_command`, `build_command`, `artifact_pattern`, `publish_command`, `install_verify_command`. Stub adapters additionally declare `status: stub`.
- **Repo version is `0.21.0`** and is mirrored in three files that `test_version_mirrors_match` keeps in lockstep. Do **not** bump it in Tasks 1–9; Task 10 does that through the new skill.

---

## File Structure

| File | Responsibility |
|---|---|
| `docs/git-remote-resolution.md` | **New.** The canonical four-layer remote/default-branch resolution, shared by `/ship` and `/release`. |
| `skills/ship/SKILL.md` | **Modify** lines 66–86: replace the inline resolution with a link to the shared doc. Description tweak in Task 9. |
| `skills/release/SKILL.md` | **New.** The target-agnostic core workflow. Contains no technology-specific command. |
| `skills/release/references/ADAPTER-CONTRACT.md` | **New.** The abstraction: ten fields, their meaning, and the declared detection precedence. |
| `skills/release/references/targets/python/git-tag-only.md` | **New.** Working adapter — this repo. |
| `skills/release/references/targets/python/uv.md` | **New.** Working adapter — wheel-building uv projects. |
| `skills/release/references/targets/typescript/npm.md` | **New.** Stub. |
| `skills/release/references/targets/java/maven.md` | **New.** Stub. |
| `tests/test_release_skill_structure.py` | **New.** Structural guard; grows across Tasks 1–8. |
| `tests/test_skill_integrity.py` | **Modify:** add the new paths to `INTEGRITY_SCAN_GLOBS` so the dangling-link guard covers them. |
| `evals/release-evals.json` | **New.** Seven eval cases. |
| `README.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` | **Modify.** Register the skill. |

---

## Task 0: Open the working branch

**Files:** none — branch setup only.

- [ ] **Step 1: Confirm you are starting from the spec branch and it is clean**

```bash
git status --short
git branch --show-current
```

Expected: no output from `status`, and the branch is `docs/release-skill-spec`.

- [ ] **Step 2: Create the implementation branch**

```bash
git checkout -b feat/release-skill
```

- [ ] **Step 3: Verify the suite is green before changing anything**

```bash
uv sync && uv run pytest && uv run ruff check . && uv run black --check .
```

Expected: all pass. If anything fails now, stop — you must know the baseline is green, or you cannot attribute a later failure to your own change.

---

## Task 1: Extract the shared remote/default-branch resolution

This lands **first and alone** so a regression in `/ship` stays bisectable. `/ship` is heavily used; this task changes its working body, not just prose.

**Files:**
- Create: `docs/git-remote-resolution.md`
- Modify: `skills/ship/SKILL.md:66-86`
- Modify: `tests/test_skill_integrity.py:53-67` (the `INTEGRITY_SCAN_GLOBS` tuple)
- Test: `tests/test_release_skill_structure.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `docs/git-remote-resolution.md` containing the shell block that defines `REMOTE` and `DEFAULT`. Task 6 links this file from `skills/release/SKILL.md` Step 1. The doc's two required headings are `## Resolve the remote` and `## Resolve the default branch`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_release_skill_structure.py`:

```python
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


def test_shared_git_resolution_doc_exists_and_defines_both_variables():
    assert GIT_RESOLUTION_DOC.is_file(), "docs/git-remote-resolution.md must exist"
    text = GIT_RESOLUTION_DOC.read_text(encoding="utf-8")
    for heading in ("## Resolve the remote", "## Resolve the default branch"):
        assert heading in text, f"shared doc missing section: {heading}"
    # The four layers that make this worth sharing at all.
    for layer in ("symbolic-ref", "git remote show", "gh repo view", "main master"):
        assert layer in text.replace("\n", " "), f"shared doc lost fallback layer: {layer}"


def test_ship_links_the_shared_doc_instead_of_restating_it():
    text = SHIP_SKILL.read_text(encoding="utf-8")
    assert "docs/git-remote-resolution.md" in text, (
        "/ship must link the shared resolution doc"
    )
    # The duplication must not silently return: /ship no longer carries the
    # gh-repo-view fallback line itself.
    assert "gh repo view --json defaultBranchRef" not in text, (
        "/ship still restates the resolution inline — it must link the shared doc"
    )
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_release_skill_structure.py -v`
Expected: FAIL — `AssertionError: docs/git-remote-resolution.md must exist`.

- [ ] **Step 3: Create the shared doc**

Create `docs/git-remote-resolution.md`:

````markdown
# Resolving the remote and the default branch

Shared by every skill in this plugin that pushes, targets a base branch, or checks
whether the working branch is current — today `/ship` (Step 1) and `/release` (Step 1).

This lives in one file for a specific reason. The resolution is fifteen lines of
non-obvious shell, and the failure it guards against is silent: `refs/remotes/<remote>/HEAD`
is set only by a fresh `git clone`. Any repo created with `git init` + `git remote add`
has no such ref, so `git symbolic-ref` alone returns nothing and a skill that trusts it
targets the wrong base branch. Restating this per skill is how the copies drift.

## Resolve the remote

Prefer `origin`; otherwise take the first configured remote. Never hardcode `origin` —
forks and upstream-tracking repos name theirs differently.

```bash
REMOTE=$(git remote | grep -qx origin && echo origin || git remote | head -1)
echo "=== remote ===" ; echo "${REMOTE:-(none)}"
```

An empty result means there is no remote at all. The calling skill decides what that
means for it: `/ship` can still branch and commit; `/release` cannot publish and must
refuse.

## Resolve the default branch

Four layers, cheapest first. Each runs only if the previous produced nothing.

```bash
DEFAULT=""
if [ -n "$REMOTE" ]; then
  # 1. Local ref — instant, but only exists on a freshly cloned repo.
  DEFAULT=$(git symbolic-ref "refs/remotes/$REMOTE/HEAD" 2>/dev/null | sed 's@.*/@@')
  # 2. Ask the remote directly — a network round-trip, always authoritative.
  [ -z "$DEFAULT" ] && DEFAULT=$(git remote show "$REMOTE" 2>/dev/null | sed -n 's/.*HEAD branch: //p')
  # 3. Ask GitHub — works when the remote is unreachable but gh is authenticated.
  [ -z "$DEFAULT" ] && DEFAULT=$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name 2>/dev/null)
fi
# 4. Guess from local branches, last resort.
for candidate in main master; do
  [ -z "$DEFAULT" ] && git show-ref --verify --quiet "refs/heads/$candidate" && DEFAULT="$candidate"
done
echo "=== default ===" ; echo "${DEFAULT:-(unknown — confirm with the user)}"
```

`(unknown)` means detection found no signal at all. **Never guess past this point** — ask
the user which branch to target. A wrong default branch silently opens a PR against the
wrong base, or pushes a release to the wrong line of development.

## Optional: set the local ref once

A user hitting layer 2 or 3 repeatedly can make layer 1 succeed from then on:

```bash
git remote set-head <remote> --auto
```

Suggest it; never run it unasked. It writes to their repo config.
````

- [ ] **Step 4: Replace the inline block in `/ship`**

In `skills/ship/SKILL.md`, the Step 1 code block currently spans the remote and default
resolution (lines 66–86). Replace **only** those lines — the `git rev-parse` guard above
and the `BRANCH=`/worktree/status lines below stay exactly as they are.

Delete from the `# Resolve the remote ONCE` comment through the
`echo "=== default ==="` line, and put in its place:

````markdown
Resolve the remote and the base branch using the shared procedure in
[docs/git-remote-resolution.md](../../docs/git-remote-resolution.md) — run that file's two
blocks to set `REMOTE` and `DEFAULT`, then continue with the rest of this block. Both
values are used throughout the steps below; never reintroduce a literal `origin`.

```bash
# REMOTE and DEFAULT are now set — see docs/git-remote-resolution.md.
````

The remainder of the original block (from `# Current branch.` onward) follows unchanged
inside that same fence.

- [ ] **Step 5: Add the new paths to the link guard**

In `tests/test_skill_integrity.py`, extend the `INTEGRITY_SCAN_GLOBS` tuple (line ~53) so
the dangling-link guard covers the new doc and, from Task 6 onward, the release skill:

```python
    "skills/gof/**/*.md",
    "skills/solid/**/*.md",
    "skills/tdd/**/*.md",
    "skills/ship/SKILL.md",
    "skills/release/**/*.md",
    "docs/refactor-workflow.md",
    "docs/refactor-agents/*.md",
    "docs/lens-overlap.md",
    "docs/git-convention.md",
    "docs/git-remote-resolution.md",
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_release_skill_structure.py tests/test_skill_integrity.py -v`
Expected: PASS. In particular `test_relative_markdown_links_resolve` must pass — it now
resolves `/ship`'s new link to `../../docs/git-remote-resolution.md`. If it fails with a
dangling link, the relative depth is wrong: `skills/ship/SKILL.md` is two levels below the
repo root, so `../../docs/` is correct.

- [ ] **Step 7: Run the full gate**

```bash
uv run pytest && uv run ruff check . && uv run black --check .
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add docs/git-remote-resolution.md skills/ship/SKILL.md \
        tests/test_skill_integrity.py tests/test_release_skill_structure.py
git commit -F - <<'MSG'
refactor(ship): extract the remote/default resolution to a shared doc

/release needs the same four-layer fallback, and restating it would
reproduce the procedure-drift failure that /release exists to prevent.
Lands alone, before any /release work, so a regression here stays
bisectable.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

## Task 2: Define the adapter contract

**Files:**
- Create: `skills/release/references/ADAPTER-CONTRACT.md`
- Test: `tests/test_release_skill_structure.py`

**Interfaces:**
- Consumes: nothing.
- Produces: the ten field names every adapter must declare, exported to later tasks as the module constant `CONTRACT_FIELDS` in the test file; and the declared detection precedence Task 6's core reads.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_release_skill_structure.py` (add `RELEASE_SKILL_DIR` and the
frontmatter parser to the module header — later tasks reuse both):

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_release_skill_structure.py -v`
Expected: FAIL — `AssertionError: ADAPTER-CONTRACT.md must exist`.

- [ ] **Step 3: Create the contract**

Create `skills/release/references/ADAPTER-CONTRACT.md`:

````markdown
# Release-target adapter contract

The `/release` core workflow knows **nothing** about uv, npm, Maven, or wheels. It knows
only this contract. Every concrete release target supplies one adapter file filling these
fields; the core reads whichever file detection resolves and never names a technology
itself.

That is the whole design: **adding a release target means adding a file here, never
editing the core.** `tests/test_release_skill_structure.py` enforces it — the core failing
to stay technology-agnostic is a test failure, not a code-review opinion.

## Where adapters live

```
references/targets/<technology>/<toolchain>.md
```

The directory is the technology (the detection axis). The filename is the toolchain (the
actual command set). One file is exactly one command set — one reason to change. A single
`python.md` branching uv-versus-poetry would have two, which is why the tree has two
levels.

## The ten fields

Declared as YAML frontmatter. Every field is required; three may be `null`.

| Field | Meaning | `null` allowed |
|---|---|---|
| `technology` | Must equal the parent directory name. | no |
| `toolchain` | Must equal the filename stem. | no |
| `fingerprint` | The file whose presence selects this adapter. | no |
| `version_source` | `path/to/file#selector` — the one canonical version literal. | no |
| `derived_manifests` | List of `path#selector` stamped *from* the source. | yes — empty list |
| `gate_command` | Clean rebuild from the lockfile, then the red/green check. | no |
| `build_command` | Produce distributable artifacts. | yes — no-build targets |
| `artifact_pattern` | Glob the build must emit. Verified, never assumed. | yes — iff no build |
| `publish_command` | The outward-facing step. | no |
| `install_verify_command` | Proves the installed thing is what was just cut. | no |

`<remote>` and `<default>` appearing in a command are substituted from the resolution in
[../../../docs/git-remote-resolution.md](../../../docs/git-remote-resolution.md).

### `status: stub`

An adapter that has been sketched but never exercised against a real release declares:

```yaml
status: stub
```

The core **refuses to run** against a stub. A half-written adapter driving a real release
is exactly the failure this contract exists to prevent, so the refusal is unconditional —
no confirmation overrides it. Remove the marker only after cutting a real release with it.

## The prose body

Frontmatter carries values. The body carries what key/value cannot: the traps.

`gate_command: uv sync && uv run pytest` does not say *why* the clean sync comes first —
that it is a latent-dependency detector, and that a test importing an undeclared package
passes for weeks on the machine that happens to have it installed. Put that in the body.
A field a future reader misapplies is a field that was documented as a value when it
needed to be documented as a reason.

## Detection

Two levels. Precedence is **declared here**, never emergent from directory listing order.

### Level 1 — technology

First match wins:

| Fingerprint | Technology |
|---|---|
| `pom.xml` or `build.gradle` / `build.gradle.kts` | `java` |
| `package.json` | `typescript` |
| `pyproject.toml` or `setup.py` | `python` |

**More than one technology matches** — a Python backend beside a TypeScript frontend — →
**ask the user**. Never guess; the wrong guess publishes the wrong thing.

### Level 2 — toolchain within that technology

First match wins:

| Technology | Fingerprint | Toolchain |
|---|---|---|
| `python` | `.claude-plugin/plugin.json`, or `[tool.uv] package = false` | `git-tag-only` |
| `python` | `uv.lock` | `uv` |
| `typescript` | `package-lock.json` | `npm` |
| `java` | `pom.xml` | `maven` |

Note the ordering within `python` is load-bearing: this very repo matches **both**
`git-tag-only` and `uv`. `git-tag-only` is listed first because it is the more specific
signal — a repo with `[tool.uv] package = false` builds no wheel, so the `uv` adapter's
`build_command` and `artifact_pattern` would both be wrong for it.

**No toolchain matches** within a detected technology → ask the user which adapter to use,
listing what is available.

**No technology matches at all** → refuse, and point the user at this file to write an
adapter. `/release` does not generate adapters interactively; authoring one is a separate,
deliberate act.

## Adding an adapter

1. Create `references/targets/<technology>/<toolchain>.md` with all ten fields.
2. Declare `status: stub` until you have cut a real release with it.
3. Add its fingerprint row to the Level 2 table above, positioned so its precedence
   against existing adapters is explicit.
4. Run `uv run pytest tests/test_release_skill_structure.py` — the guard checks the field
   set, the directory/filename agreement, and fingerprint disjointness.

You do not touch `SKILL.md`. If you find yourself wanting to, the contract is missing a
field — add it here, to every adapter, and to the test, in that order.
````

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_release_skill_structure.py -v`
Expected: PASS (2 new tests).

- [ ] **Step 5: Commit**

```bash
git add skills/release/references/ADAPTER-CONTRACT.md tests/test_release_skill_structure.py
git commit -F - <<'MSG'
feat(release): define the release-target adapter contract

The abstraction the core workflow depends on: ten fields, the two-level
detection precedence, and the stub marker that keeps a half-written
adapter from driving a real release.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

## Task 3: The `python/git-tag-only` adapter (this repo)

The dogfooded one. Write it first so the contract is proven against a real target before
the second adapter generalises it.

**Files:**
- Create: `skills/release/references/targets/python/git-tag-only.md`
- Test: `tests/test_release_skill_structure.py`

**Interfaces:**
- Consumes: `CONTRACT_FIELDS` and `parse_frontmatter` from Task 2.
- Produces: `adapter_files()` — a helper later tasks reuse to iterate every adapter.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_release_skill_structure.py`:

```python
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
    assert fields.get("artifact_pattern") == "null", "no build means no artifact pattern"
    assert "status" not in fields, "the dogfooded adapter is not a stub"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_release_skill_structure.py -v`
Expected: FAIL — `AssertionError: no adapters found under references/targets/`.

- [ ] **Step 3: Create the adapter**

Create `skills/release/references/targets/python/git-tag-only.md`:

````markdown
---
technology: python
toolchain: git-tag-only
fingerprint: .claude-plugin/plugin.json
version_source: .claude-plugin/plugin.json#.version
derived_manifests:
  - .claude-plugin/marketplace.json#.plugins[0].version
  - pyproject.toml#project.version
gate_command: uv sync && uv run pytest && uv run ruff check . && uv run black --check .
build_command: null
artifact_pattern: null
publish_command: git push <remote> <default> --follow-tags
install_verify_command: claude plugin list
---

# python / git-tag-only

A Python-tooled repository that ships **no package**. The git tag *is* the release: a
Claude Code plugin, a config bundle, a skills collection. `uv` manages the development
environment, but nothing is ever built or uploaded to an index.

This is the adapter for the `mente-apex-plugin` repo itself, which means it is the one
adapter exercised on every release of this skill. Treat it as the reference instance.

## Traps

**`.claude-plugin/plugin.json` is canonical. The other two are stamped.** All three
manifests carry the same version literal, and `tests/test_skill_integrity.py::test_version_mirrors_match`
fails the build if they drift. Stamp all three or none — a partial stamp is a red suite,
which is the correct outcome but a confusing one to debug mid-release.

**There is no wheel.** `pyproject.toml` declares `[tool.uv] package = false`, so `uv build`
would either fail or emit something nobody installs. `build_command` and
`artifact_pattern` are both `null`, and the core skips its build and artifact-verification
steps entirely. Do not "helpfully" add a build here.

**Do not confuse this with `python/uv`.** That adapter's fingerprint (`uv.lock`) is also
present in this repo — every uv project has one. `git-tag-only` wins on precedence because
its fingerprint is the more specific signal. If you ever find `/release` proposing a
`dist/*.whl` for this repo, detection picked the wrong adapter; fix the precedence table
in the contract rather than editing this file.

**`uv sync` before the tests is not decoration.** It rebuilds the environment from
`uv.lock`, which is the only way a dependency that is installed-but-undeclared shows
itself. A test importing a package that no `[dependency-groups] dev` entry declares passes
indefinitely on the machine that happens to have it, and fails the first time anyone
rebuilds cleanly. A release is the worst moment to discover that, so the gate forces it
early and on purpose.

## Verifying the install

`claude plugin list` shows the installed marketplace plugins and their versions. Confirm
the entry for this plugin reads the version just cut. There is no shim or venv to check —
the plugin is loaded from the marketplace checkout, not installed into an environment.

If the version still shows the previous release, the marketplace has not re-fetched. That
is a consumer-side cache, not a failed release: the tag and the manifests are correct, and
the report should say so rather than implying the release failed.
````

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_release_skill_structure.py -v`
Expected: PASS (4 new tests).

- [ ] **Step 5: Commit**

```bash
git add skills/release/references/targets/python/git-tag-only.md \
        tests/test_release_skill_structure.py
git commit -F - <<'MSG'
feat(release): add the python/git-tag-only adapter

This repo's own release target and the one exercised on every release of
the skill. Proves the contract against a real, no-build case before the
wheel-building adapter generalises it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

## Task 4: The `python/uv` adapter

**Files:**
- Create: `skills/release/references/targets/python/uv.md`
- Test: `tests/test_release_skill_structure.py`

**Interfaces:**
- Consumes: `adapter_files()`, `parse_frontmatter`, `CONTRACT_FIELDS` from Tasks 2–3.
- Produces: the second working adapter; Task 5's disjointness test needs at least two adapters in one technology directory to be meaningful.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_release_skill_structure.py`:

```python
def test_uv_adapter_verifies_a_real_artifact_pattern():
    """The wheel-name check is the whole point of artifact_pattern."""
    adapter = TARGETS_DIR / "python" / "uv.md"
    assert adapter.is_file(), "the uv adapter must exist"
    fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
    assert fields.get("build_command") == "uv build", "uv projects build with uv build"
    assert "dist/" in fields.get("artifact_pattern", ""), (
        "artifact_pattern must name the real build output directory"
    )
    assert fields.get("build_command") != "null", "a uv package target does build"


def test_no_adapter_recommends_a_forbidden_python_toolchain():
    """uv is canonical: pip/pipx/pyenv must never appear as an instruction."""
    offenders = []
    for adapter in adapter_files():
        fields = parse_frontmatter(adapter.read_text(encoding="utf-8"))
        if fields.get("technology") != "python":
            continue
        commands = " ".join(
            str(fields.get(field, "")) for field in CONTRACT_FIELDS
        )
        for forbidden in ("pip install", "pipx", "pyenv", "python -m build"):
            if forbidden in commands:
                offenders.append(f"{adapter.relative_to(REPO_ROOT)}: {forbidden}")
    assert not offenders, "adapters use forbidden Python tooling:\n" + "\n".join(offenders)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_release_skill_structure.py -v`
Expected: FAIL — `AssertionError: the uv adapter must exist`.

- [ ] **Step 3: Create the adapter**

Create `skills/release/references/targets/python/uv.md`:

````markdown
---
technology: python
toolchain: uv
fingerprint: uv.lock
version_source: pyproject.toml#project.version
derived_manifests: []
gate_command: uv sync && uv run pytest && uv run ruff check . && uv run black --check .
build_command: uv build
artifact_pattern: dist/*-<version>-py3-none-any.whl
publish_command: git push <remote> <default> --follow-tags
install_verify_command: uv tool install --force . && which <tool-name>
---

# python / uv

A `uv`-managed Python project that builds a wheel. `pyproject.toml` holds the single
version literal; package metadata derives from it, so there is usually nothing to stamp —
`derived_manifests` is empty. If a project grows a second manifest carrying the version,
add it here rather than letting the core find an undeclared literal and refuse.

Derived from the verified release procedure in Mente-Apex/menteapex-memory-system#202.

## Traps

**The wheel name is not the project name.** `uv build` derives the artifact from
`[project].name` with dots and hyphens normalised to underscores, so a project named
`mente-apex-memory` emits `mente_apex_memory-0.4.0-py3-none-any.whl`. Install docs in that
repo told users to install `mente_apex_mem-*` for a long time, and nothing caught it
because no step ever compared the documented name against a real build. That is why
`artifact_pattern` exists and why the core *verifies* rather than assumes: expand the glob
after building and refuse if it matches nothing.

**`uv sync` before the tests is the latent-dependency detector.** It rebuilds from
`uv.lock`. A test importing a package that no dependency declares — `uvicorn`, in the
reference repo — passes for weeks on the machine that happens to have it and fails the
moment anyone rebuilds cleanly. Running the sync first means the release discovers it,
not the user.

**Dependency layout is a release concern, not a style preference.** Tooling
(`pytest`, `ruff`, `black`) belongs in `[dependency-groups] dev`: `uv sync` installs it by
default and it never ships in the wheel. User-facing runtime extras belong in
`[project.optional-dependencies]`. Getting this backwards either ships test tooling to
users or makes `uv run` need flags — and it makes the clean-sync check meaningless,
because the wrong set gets installed.

**Never `pip`, `pipx`, `pyenv`, or `python -m build`.** There is one documented exception
in the reference repo — a pipx fallback inside install *code*, for foreign machines — and
it is not a path for cutting a release. Do not generalise it into this adapter.

## Verifying the install

Building a wheel proves nothing about what a user ends up running. Install the artifact
into an isolated tool environment and confirm the shim resolves **outside** the
development checkout:

```bash
uv tool install --force .
which <tool-name>                 # must be under ~/.local/bin, not the checkout
head -1 "$(which <tool-name>)"    # shebang must point at the tool venv
<tool-name> --version             # must print the version just cut
```

A shim whose shebang points into the development checkout means the "installed" tool is
the working tree — it will appear to work perfectly for you and be broken for everyone
else. That check is the difference between a build that succeeded and a release that works.
````

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_release_skill_structure.py -v`
Expected: PASS (6 new tests total in the file).

- [ ] **Step 5: Commit**

```bash
git add skills/release/references/targets/python/uv.md tests/test_release_skill_structure.py
git commit -F - <<'MSG'
feat(release): add the python/uv wheel-building adapter

Derived from the verified procedure in menteapex-memory-system#202,
including the wheel-name trap that artifact_pattern exists to catch.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

## Task 5: The stub adapters and fingerprint disjointness

**Files:**
- Create: `skills/release/references/targets/typescript/npm.md`
- Create: `skills/release/references/targets/java/maven.md`
- Test: `tests/test_release_skill_structure.py`

**Interfaces:**
- Consumes: `adapter_files()`, `parse_frontmatter`.
- Produces: three populated technology directories, so Task 6's core has something real to be agnostic *about*.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_release_skill_structure.py`:

```python
def test_three_technologies_are_represented():
    """The seam must be proven across a technology boundary, not just within one."""
    technologies = {adapter.parent.name for adapter in adapter_files()}
    assert {"python", "typescript", "java"} <= technologies, (
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_release_skill_structure.py -v`
Expected: FAIL — `expected python, typescript and java adapters; found ['python']`.

- [ ] **Step 3: Create the TypeScript stub**

Create `skills/release/references/targets/typescript/npm.md`:

````markdown
---
technology: typescript
toolchain: npm
fingerprint: package-lock.json
version_source: package.json#.version
derived_manifests: []
gate_command: npm ci && npm test && npm run lint
build_command: npm run build && npm pack
artifact_pattern: "*-<version>.tgz"
publish_command: npm publish && git push <remote> <default> --follow-tags
install_verify_command: npm install -g <package-name>@<version> && which <bin-name>
status: stub
---

# typescript / npm  (STUB)

**This adapter has never driven a real release.** `/release` refuses to run against it.
Remove `status: stub` only after cutting a release with it and correcting whatever the
commands below get wrong.

Its job right now is structural: it proves the adapter seam holds across a technology
boundary, not merely between two toolchains inside Python. If adding a second technology
had required editing the core, the seam would have been wrong — and this file is what
demonstrated it did not.

## What to verify before removing the stub marker

**`npm ci`, not `npm install`.** `ci` installs strictly from `package-lock.json` and fails
if the lockfile and `package.json` disagree. That is the latent-dependency detector for
this technology — the direct analogue of `uv sync`, and the same reason: a dependency that
is installed but undeclared has to fail *here*, not at a user's first install.

**`npm publish` is irreversible in a way tagging is not.** A published version cannot be
re-published, and unpublish windows are narrow. It sits after the confirmation checkpoint
for that reason. Verify the ordering against the core before trusting this adapter.

**Two-step publish.** Unlike the Python adapters, publishing touches a registry *and* the
git remote. Confirm the core handles a compound `publish_command` — or split it into a
registry step and a tag step and update the contract.

**`artifact_pattern` is a guess.** `npm pack` names the tarball from `name` and `version`
with scoped packages mangled (`@scope/pkg` → `scope-pkg-1.0.0.tgz`). Run a real `npm pack`
and correct the pattern before this adapter is trusted.
````

- [ ] **Step 4: Create the Java stub**

Create `skills/release/references/targets/java/maven.md`:

````markdown
---
technology: java
toolchain: maven
fingerprint: pom.xml
version_source: pom.xml#/project/version
derived_manifests: []
gate_command: mvn -B clean verify
build_command: mvn -B package
artifact_pattern: target/*-<version>.jar
publish_command: mvn -B deploy && git push <remote> <default> --follow-tags
install_verify_command: mvn -B dependency:get -Dartifact=<group>:<artifact>:<version>
status: stub
---

# java / maven  (STUB)

**This adapter has never driven a real release.** `/release` refuses to run against it.
Remove `status: stub` only after cutting a release with it.

## What to verify before removing the stub marker

**Maven's version literal is not a leaf.** `pom.xml` has both `/project/version` and
`/project/parent/version`, and multi-module builds repeat the version in every child POM.
The core's single-literal check will find those and refuse. Decide before trusting this
adapter whether child POMs are `derived_manifests` (stamped) or whether the project uses
`${revision}` with a single property — the latter fits the contract cleanly, the former
needs every child listed.

**`mvn versions:set` exists and should probably be the stamp mechanism** rather than
editing XML directly. Confirm against the core's stamp step, which assumes a file rewrite.

**`clean verify` versus `clean test`.** `verify` runs integration tests and the full
packaging lifecycle, which is what a release gate should do. Do not weaken it to `test`.

**Deploying to Maven Central is not one command.** It needs GPG signing, a staging
repository, and a release action that is often manual. `publish_command` above is the
happy path for an internal repository only; a Central release needs the adapter — or the
contract — extended before it is honest.
````

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_release_skill_structure.py -v`
Expected: PASS (9 tests in the file).

- [ ] **Step 6: Commit**

```bash
git add skills/release/references/targets/typescript skills/release/references/targets/java \
        tests/test_release_skill_structure.py
git commit -F - <<'MSG'
feat(release): add npm and maven stub adapters

Proves the seam holds across a technology boundary, not just between two
toolchains inside Python. Both declare status: stub, which the core
refuses to run against.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

## Task 6: The core workflow — frontmatter, detection, and preflight

`SKILL.md` is written in two tasks because it is the largest file and its two halves fail
differently: this task is about *refusing correctly*, Task 7 is about *executing
correctly*.

**Files:**
- Create: `skills/release/SKILL.md`
- Test: `tests/test_release_skill_structure.py`

**Interfaces:**
- Consumes: `ADAPTER-CONTRACT.md` (Task 2), `docs/git-remote-resolution.md` (Task 1).
- Produces: `skills/release/SKILL.md` with sections `## Step 0 — Resolve the adapter` through `## Step 4 — Decide the version`, and the frontmatter Task 9's registration depends on.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_release_skill_structure.py`. **The import goes in the block at the
top of the file, beside `import re` — not here.** `ruff` E402 rejects a module-level
import placed after code, so an inline import fails the gate:

```python
# --- top of file, with the existing imports ---
from skill_version_policy import assert_version_at_least

# --- appended below the existing tests ---
RELEASE_SKILL_MD = RELEASE_SKILL_DIR / "SKILL.md"

# Literals that would mean the core stopped being technology-agnostic.
TECHNOLOGY_LITERALS = ("uv build", "uv sync", "npm ci", "npm publish", "mvn ", "pyproject")


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
    assert "pull request" in description or "PR" in description, (
        "description must disclaim /ship's territory explicitly"
    )


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
    assert "git-remote-resolution.md" in text, (
        "core must link the shared resolution rather than restating it"
    )
    assert "gh repo view --json defaultBranchRef" not in text, (
        "core restates the resolution inline — link the shared doc instead"
    )
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_release_skill_structure.py -v`
Expected: FAIL — `AssertionError: skills/release/SKILL.md must exist`.

- [ ] **Step 3: Create `SKILL.md` with frontmatter and Steps 0–4**

Create `skills/release/SKILL.md`. Note `metadata.version` is `"0.1.0"` and the description
must both attract release phrasings and repel `/ship` phrasings:

````markdown
---
name: release
description: >
  Use when the user wants a new version cut and published — the
  gate → stamp → build → tag → publish → verify-install pipeline. Invoke on
  "cut a release," "release this," "release 1.2.0," "tag and publish,"
  "bump and release," "publish the new version," "ship a release," or "/release."
  This skill OWNS versioning: it is the only place a version literal is bumped,
  derived manifests are stamped, artifacts are built and verified, a tag is
  created, and the installed tool is checked against what was just cut.
  Do NOT use for turning working changes into a commit and a pull request — that
  is /ship, which never touches versions. This skill never opens, reviews, or
  merges a pull request, and never runs a code review. It requires an
  up-to-date default branch: if a release PR is still open, merge it first, then
  invoke this.
user-invocable: true
disable-model-invocation: true
allowed-tools: Bash, Read, Edit, AskUserQuestion
metadata:
  version: "0.1.0"
---

# release

Cut a version and get it out — gate, stamp, build, tag, publish, and then prove the
*installed* thing is the thing you just cut.

`/ship` ends at an open pull request. Everything after it is this skill. The boundary is
one line: **`/ship` never touches versions; `/release` never opens or merges pull
requests.**

Launching this skill is not consent to publish. Everything up to and including the local
tag is reversible with two commands; exactly one confirmation sits immediately before the
first thing that leaves the machine.

## The seam

This workflow names no technology. It knows only the ten-field adapter contract in
[references/ADAPTER-CONTRACT.md](references/ADAPTER-CONTRACT.md); the concrete commands
live in `references/targets/<technology>/<toolchain>.md`.

That is deliberate and it is enforced: `tests/test_release_skill_structure.py` fails if
this file names a build tool. **Adding a release target means adding an adapter file, never
editing this workflow.** If you find yourself wanting to special-case a target here, the
contract is missing a field — extend the contract, not the core.

## Step 0 — Resolve the adapter

Read [references/ADAPTER-CONTRACT.md](references/ADAPTER-CONTRACT.md) and follow its
two-level detection: technology first, then toolchain, both by declared precedence.

Load the resolved adapter file and hold its ten fields. **Every later step reads through
those fields.** This is the only place a concrete target enters the workflow.

Stop here if:

- **Several technologies match** → ask which to release. Never guess.
- **No toolchain matches** inside a detected technology → ask, listing the available
  adapters for that technology.
- **Nothing matches at all** → refuse. Point the user at the contract's "Adding an
  adapter" section. Do not improvise commands.
- **The resolved adapter declares `status: stub`** → refuse, unconditionally. A stub has
  never driven a real release and its commands are unverified. Say which adapter was
  resolved and what it would take to promote it.

Report the resolution before continuing, so a wrong detection is visible immediately:

```
Target : python / git-tag-only   (fingerprint: .claude-plugin/plugin.json)
```

## Step 1 — Inspect

Resolve `REMOTE` and `DEFAULT` with the shared procedure in
[../../docs/git-remote-resolution.md](../../docs/git-remote-resolution.md). Then gather
the rest in one pass:

```bash
git fetch --quiet "$REMOTE" "$DEFAULT"
echo "=== branch ==="  ; git branch --show-current
echo "=== status ==="  ; git status --short
echo "=== behind ==="  ; git rev-list --count "HEAD..$REMOTE/$DEFAULT"
echo "=== ahead ==="   ; git rev-list --count "$REMOTE/$DEFAULT..HEAD"
echo "=== tags ==="    ; git tag --sort=-v:refname | head -5
```

Read the adapter's `version_source` to get the current version.

### Hard refusals

These are not confirmable. Say what is wrong and what would fix it, then stop.

- **Not on the default branch.** This workflow commits the version bump directly to the
  default branch, so the tag points at a commit that is actually on the release line.
  Being on a feature branch means the bump would be stranded.
- **The default branch is behind the remote** (`behind` is non-zero). Someone merged
  something you have not pulled. Tell the user to `git pull --ff-only` and re-run.
- **Dirty working tree.** List the modified paths. A release must be reproducible from
  what is committed; uncommitted work would either be swept into the release commit or
  silently excluded.
- **No remote.** There is nowhere to publish.

**A merged pull request is not something the user has to announce.** After the fetch, a
merge is visible locally — it is why `behind` is checked rather than asked about. Never
ask "did you merge it?"; look.

## Step 2 — Preflight

Run the adapter's `gate_command`. It begins with a clean rebuild from the lockfile for a
reason worth stating in the report: **that rebuild is a latent-dependency detector.** A
test importing a package that nothing declares passes indefinitely on the machine that
happens to have it installed, and fails the first time the environment is rebuilt. A
release is the worst possible moment to find out.

Non-zero exit → **refuse**. Show the failing output verbatim. Do not offer to fix it here;
a red gate is a different job, and mixing a fix into a release is how an unrelated change
ships unreviewed.

## Step 3 — Verify there is exactly one version literal

Search the repository for the current version string. Every occurrence must be either the
adapter's `version_source` or a declared entry in `derived_manifests`.

An undeclared occurrence → **refuse**, listing the file and line. It means either a
manifest that will silently keep the old version after stamping, or an adapter that is out
of date. Both are the procedure-drift failure this skill exists to prevent, and both are
one-line fixes once seen.

Exclude lockfiles, build output, and `docs/superpowers/` — plans and specs quote versions
as prose and are not stamped.

## Step 4 — Decide the version

Derive the proposed bump from Conventional Commits since the last tag:

- any `feat:` → minor
- only `fix:` / `refactor:` / `chore:` / `docs:` → patch
- any `!` or `BREAKING CHANGE:` → major

With no tags, fall back to commits since the last `chore(release):` commit; failing that,
the full history.

Show the reasoning, then let the user override — the derivation is a proposal, not a
ruling:

```
Version : 0.21.0 → 0.22.0   (minor: 4 feat, 2 fix since v0.21.0)
```
````

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_release_skill_structure.py -v`
Expected: PASS (14 tests). If `test_core_workflow_contains_no_technology_specific_command`
fails, you named a build tool in the core — move it to the adapter.

- [ ] **Step 5: Commit**

```bash
git add skills/release/SKILL.md tests/test_release_skill_structure.py
git commit -F - <<'MSG'
feat(release): add the core workflow's detection and refusal half

Steps 0-4: adapter resolution through version derivation, plus every
hard refusal. The seam is enforced by test rather than convention — the
core naming a build tool fails CI.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

## Task 7: The core workflow — stamp, build, confirm, publish, verify

**Files:**
- Modify: `skills/release/SKILL.md` (append Steps 5–11)
- Test: `tests/test_release_skill_structure.py`

**Interfaces:**
- Consumes: the frontmatter and Steps 0–4 from Task 6.
- Produces: the complete workflow. Task 8's evals assert against the step ordering defined here.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_release_skill_structure.py`:

```python
def test_stamp_precedes_commit_which_precedes_tag():
    """The stamp-before-tag trap: tagging a tree whose manifests still carry the
    old version produces a tag that is wrong at the commit it points to."""
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8")
    stamp_position = text.index("## Step 5 — Stamp")
    commit_position = text.index("## Step 7 — Commit")
    tag_position = text.index("## Step 8 — Tag")
    assert stamp_position < commit_position < tag_position, (
        "stamp must precede commit, which must precede tag"
    )


def test_exactly_one_confirmation_checkpoint_before_publishing():
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8")
    assert text.count("CONFIRMATION CHECKPOINT") == 1, (
        "there must be exactly one confirmation checkpoint"
    )
    checkpoint_position = text.index("CONFIRMATION CHECKPOINT")
    assert checkpoint_position < text.index("## Step 9 — Publish"), (
        "the checkpoint must precede the first outward-facing action"
    )
    assert checkpoint_position > text.index("## Step 8 — Tag"), (
        "the checkpoint must follow the local, reversible work"
    )


def test_core_documents_the_rollback():
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8")
    assert "git tag -d" in text, "rollback must show how to delete the local tag"
    assert "git reset --hard" in text, "rollback must show how to undo the commit"


def test_core_verifies_the_install_not_just_the_build():
    text = RELEASE_SKILL_MD.read_text(encoding="utf-8").lower()
    assert "install_verify_command" in text
    assert "outside" in text and "checkout" in text, (
        "the install check must require the shim to resolve outside the checkout"
    )
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_release_skill_structure.py -v`
Expected: FAIL — `ValueError: substring not found` on `## Step 5 — Stamp`.

- [ ] **Step 3: Append Steps 5–11 to `skills/release/SKILL.md`**

````markdown
## Step 5 — Stamp

Write the new version to the adapter's `version_source`, then to every entry in
`derived_manifests`. All of them or none — a partial stamp leaves the manifests
inconsistent, which in a repo with a lockstep guard is a red suite and in a repo without
one is a silent wrong release.

Show the resulting diff explicitly:

```bash
git --no-pager diff
```

The tree is now dirty. That is expected and temporary — Step 7 commits it, and nothing is
tagged until it is committed. This ordering is the point of Steps 5 → 7 → 8.

## Step 6 — Build and verify the artifacts

Skip this step entirely when the adapter's `build_command` is `null`.

Otherwise run it, then **expand `artifact_pattern` and check what actually landed**:

```bash
ls -1 <expanded artifact_pattern>
```

No match → **refuse**. Report the pattern and what the build actually emitted.

This is not defensive padding. In the reference repo the install documentation named a
wheel the build had never produced, and it stayed wrong for a long time because no step
ever compared the documented artifact against a real one. Assuming the artifact name is
how that happens; verifying it is how it stops.

## Step 7 — Commit

One commit, on the default branch, containing only the stamp:

```bash
git add <version_source> <each derived manifest>
git commit -F - <<'MSG'
chore(release): v<version>

Co-Authored-By: Claude <noreply@anthropic.com>
MSG
```

Use the co-author trailer the harness prescribes for the active model this session.

This is the one commit this skill makes, and it is the one commit `/ship` is structurally
forbidden to make — `/ship` never commits to the default branch. That is the whole reason
the work is not delegated.

## Step 8 — Tag

Annotated, never lightweight — an annotated tag carries an author, a date, and a message:

```bash
git tag -a "v<version>" -m "v<version>"
```

**The tag already exists** → refuse. Re-tagging a released version is how two different
commits end up claiming to be the same release. If the user genuinely means to re-cut,
they delete the tag deliberately, first.

Everything up to here is local. Nothing has left the machine.

---

## ⚠ CONFIRMATION CHECKPOINT

The single stop in this workflow. Everything above was local and reversible; everything
below is not.

Show exactly what will leave the machine:

```
Release plan
  Target    : <technology> / <toolchain>
  Version   : <old> → <new>
  Stamped   : <version_source>, <derived manifests>
  Artifacts : <verified artifact names, or "none — no build for this target">
  Tag       : v<new>  (created locally)
  Will push : <publish_command>
  Then      : gh release create v<new>

  Not yet pushed. To abandon:
    git tag -d v<new>
    git reset --hard <remote>/<default>
```

Ask via **AskUserQuestion**. Anything other than a clear yes → stop and print the rollback
commands. Do not proceed on ambiguity.

---

## Step 9 — Publish

Run the adapter's `publish_command`, substituting the resolved `<remote>` and `<default>`.
Stop and report on any failure — never paper over a failed push, and never retry blindly.

Then create the GitHub release, with notes grouped from the Conventional Commits since the
previous tag:

```bash
gh release create "v<version>" --title "v<version>" --notes "<grouped notes>"
```

**`gh` missing or unauthenticated** → this is not a failed release. The tag is pushed and
the release is real. Report the tag, skip the GitHub release, give the user the
`releases/new` URL, and suggest `gh auth login` for next time.

## Step 10 — Verify the install

Run the adapter's `install_verify_command` and confirm two things:

1. The reported version is the one just cut.
2. The resolved binary lives **outside** the development checkout.

Point 2 is the one people skip. A shim whose path or shebang points into the working tree
means the "installed" tool is your checkout: it works perfectly for you and is broken for
everyone else. Building an artifact proves nothing about what a user ends up running.

A failure here does not un-publish anything — the tag is out. Report it plainly as a
release that shipped with an install problem, and say what is wrong.

## Step 11 — Report

```
✓ Released <version>
  Target    : <technology> / <toolchain>
  Commit    : <sha>  chore(release): v<version>
  Tag       : v<version>  (pushed)
  Artifacts : <names, or "none">
  Release   : <url>
  Installed : <verified version>  → <resolved path>
```

If anything stopped early, say exactly where and what the user must do to finish. A
partially completed release is worse than a refused one *only* if nobody says so.

## Scope — what /release does not do

- It does **not** commit or push ordinary work, and does **not** open a pull request. That
  is `/ship`.
- It does **not** merge pull requests, and does **not** run a code review.
- It does **not** fix a red gate. A failing suite refuses the release; repairing it is a
  separate job with separate review.
- It does **not** write adapters. Authoring one is deliberate — see the contract.
````

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_release_skill_structure.py -v`
Expected: PASS (18 tests).

- [ ] **Step 5: Run the full gate**

```bash
uv run pytest && uv run ruff check . && uv run black --check .
```

Expected: all pass. `test_relative_markdown_links_resolve` now also checks
`skills/release/**/*.md` — if it reports a dangling link, check the relative depth:
`skills/release/SKILL.md` needs `../../docs/`, and files under
`references/targets/<tech>/` need `../../../../docs/`.

- [ ] **Step 6: Commit**

```bash
git add skills/release/SKILL.md tests/test_release_skill_structure.py
git commit -F - <<'MSG'
feat(release): add the core workflow's execution half

Steps 5-11: stamp, build with artifact verification, commit, tag, the one
confirmation checkpoint, publish, and install verification. Ordering is
asserted by test — stamp before commit before tag is the trap this skill
exists to close.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

## Task 8: Evals

Authored with `/skill-creator`, which owns eval format and description-trigger
optimization. The cases below are the required coverage; `/skill-creator` may add more.

**Files:**
- Create: `evals/release-evals.json`
- Test: `tests/test_release_skill_structure.py`

**Interfaces:**
- Consumes: the workflow from Tasks 6–7; eval case keys must match `EVAL_CASE_KEYS` in `tests/test_skill_integrity.py:239` — `{"id", "skill", "prompt", "expected_output", "assertions"}`.
- Produces: `evals/release-evals.json` with `skill_name: "release"` and seven cases.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_release_skill_structure.py`:

**`import json` goes in the import block at the top of the file**, beside `import re` —
`ruff` E402 rejects a module-level import after code.

```python
# --- top of file, with the existing imports ---
import json

# --- appended below the existing tests ---
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


def test_release_evals_cover_every_required_scenario():
    data = json.loads(RELEASE_EVALS.read_text(encoding="utf-8"))
    present = {eval_case.get("eval_name") for eval_case in data["evals"]}
    missing = REQUIRED_EVAL_NAMES - present
    assert not missing, f"eval coverage gaps: {sorted(missing)}"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_release_skill_structure.py -v`
Expected: FAIL — `AssertionError: evals/release-evals.json must exist`.

- [ ] **Step 3: Invoke `/skill-creator` to author the evals**

Give it this brief:

> Author `evals/release-evals.json` for the `/release` skill at `skills/release/SKILL.md`.
> Follow the schema in `evals/gof-evals.json`: top-level `skill_name` and `evals`, each
> case carrying `id`, `eval_name`, `skill`, `prompt`, `expected_output`, `files`, and
> `assertions`. The seven `eval_name` values are fixed and asserted by
> `tests/test_release_skill_structure.py`:
>
> 1. `happy-path` — a clean repo on an up-to-date default branch with a fixture adapter
>    whose commands are harmless echoes. Assert the workflow reaches the confirmation
>    checkpoint with the stamp diff shown, and does not publish before the confirmation.
> 2. `dirty-tree-refusal` — uncommitted changes present. Assert refusal at Step 1, the
>    modified paths listed, and nothing stamped.
> 3. `failing-gate-refusal` — the fixture adapter's `gate_command` exits non-zero. Assert
>    refusal with the failing output shown verbatim, and no offer to fix the failure.
> 4. `stamp-before-tag-ordering` — assert the stamp is committed before `git tag` runs, and
>    that no tag is created while the tree is dirty.
> 5. `second-version-literal-refusal` — a second hardcoded version string exists in a file
>    the adapter does not declare. Assert refusal naming the file and line.
> 6. `artifact-pattern-mismatch-refusal` — the fixture build emits a name that does not
>    match `artifact_pattern`. Assert refusal comparing expected pattern to actual output.
> 7. `ship-release-trigger-boundary` — given "ship my changes and open a PR", `/release`
>    must NOT fire; given "cut a 0.22.0 release and publish it", `/ship` must NOT fire.
>
> Also run the description-triggering optimization against `skills/ship/SKILL.md` to
> confirm the two descriptions do not collide, and report any wording change it recommends
> for either skill.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_release_skill_structure.py tests/test_skill_integrity.py -v`
Expected: PASS.

- [ ] **Step 5: Apply any description change `/skill-creator` recommends**

If it recommends wording changes to `skills/ship/SKILL.md` or `skills/release/SKILL.md`,
apply them and re-run `uv run pytest tests/test_release_skill_structure.py` — the
description-trigger assertions from Task 6 must still pass.

- [ ] **Step 6: Commit**

```bash
git add evals/release-evals.json tests/test_release_skill_structure.py \
        skills/release/SKILL.md skills/ship/SKILL.md
git commit -F - <<'MSG'
test(release): add the release eval suite

Seven cases: the happy path, four refusals, the stamp-before-tag
ordering, and the /ship trigger boundary that keeps the two skills from
both firing.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

## Task 9: Register the skill

**Files:**
- Modify: `README.md` (skills table)
- Modify: `.claude-plugin/plugin.json` (description, keywords)
- Modify: `.claude-plugin/marketplace.json` (description)
- Modify: `skills/ship/SKILL.md` (description boundary)
- Test: `tests/test_release_skill_structure.py`

**Interfaces:**
- Consumes: the finished skill from Tasks 6–8.
- Produces: a discoverable, documented skill. No later task depends on this.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_release_skill_structure.py`:

```python
README = REPO_ROOT / "README.md"
PLUGIN_JSON = REPO_ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE_JSON = REPO_ROOT / ".claude-plugin" / "marketplace.json"


def test_release_is_registered_everywhere_a_skill_must_be():
    assert "/release" in README.read_text(encoding="utf-8"), "README omits /release"
    plugin = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))
    assert "release" in plugin["keywords"], "plugin.json keywords omit release"
    assert "/release" in plugin["description"], "plugin.json description omits /release"
    marketplace = json.loads(MARKETPLACE_JSON.read_text(encoding="utf-8"))
    assert "/release" in marketplace["plugins"][0]["description"], (
        "marketplace.json description omits /release"
    )


def test_ship_description_disclaims_release_territory():
    fields = parse_frontmatter(
        (REPO_ROOT / "skills" / "ship" / "SKILL.md").read_text(encoding="utf-8")
    )
    description = fields.get("description", "")
    assert "version" in description.lower(), (
        "/ship must disclaim versioning so /release's territory is unambiguous"
    )
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_release_skill_structure.py -v`
Expected: FAIL — `AssertionError: README omits /release`.

- [ ] **Step 3: Add the README row**

In the skills table in `README.md`, after the `ship` row:

```markdown
| release | `/release` | Cut and publish a version: gate → stamp → build → tag → publish → verify-install. Technology/toolchain adapters (`python/uv`, `python/git-tag-only`, plus `typescript/npm` and `java/maven` stubs) supply the commands; the core names none, so a new target is a new file. Refuses a dirty tree, a red gate, a second hardcoded version literal, or an artifact that does not match the declared pattern. Exactly one confirmation, immediately before anything leaves the machine |
```

Then extend the convention note below the table:

```markdown
> `/ship` and `/release` are complementary and never overlap: `/ship` owns commit → push →
> open PR and never touches a version; `/release` owns the version, the tag, and everything
> outward-facing, and never opens or merges a PR. Both resolve the remote and default
> branch through [docs/git-remote-resolution.md](docs/git-remote-resolution.md).
```

- [ ] **Step 4: Update the two manifests**

In `.claude-plugin/plugin.json`, append to `description` (before the closing quote):

```
, and a release pipeline (/release: gate, stamp, build, tag, publish, verify-install) driven by per-technology adapters
```

and add `"release"` plus `"versioning"` to `keywords`.

In `.claude-plugin/marketplace.json`, append the same clause to the plugin's `description`.

**Do not change any `version` field.** All three must stay at `0.21.0` —
`test_version_mirrors_match` enforces the lockstep, and Task 10 bumps them through the new
skill.

- [ ] **Step 5: Tighten `/ship`'s description**

In `skills/ship/SKILL.md`, extend the existing `Do NOT use for` clause:

```
  Do NOT use for merging or closing a PR, reviewing/commenting on someone's PR,
  rebasing/squashing/force-pushing history, syncing config across machines, emailing
  files, or cutting a release — bumping a version, stamping manifests, tagging, or
  publishing is /release, and this skill never touches a version literal.
```

- [ ] **Step 6: Run the full gate**

```bash
uv run pytest && uv run ruff check . && uv run black --check .
```

Expected: all pass, including `test_version_mirrors_match`.

- [ ] **Step 7: Commit**

```bash
git add README.md .claude-plugin/plugin.json .claude-plugin/marketplace.json \
        skills/ship/SKILL.md tests/test_release_skill_structure.py
git commit -F - <<'MSG'
docs(release): register /release and sharpen the /ship boundary

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

## Task 10: Ship the branch, then dogfood the skill

The real acceptance test. A release skill that has never cut a release is a stub, and this
plan refuses to ship stubs.

**Files:** none directly — this task exercises the skill.

**Interfaces:**
- Consumes: everything.
- Produces: version `0.22.0`, tagged and released; and whatever defect the first real run exposes.

- [ ] **Step 1: Ship the branch**

Invoke `/ship`. It opens the PR for `feat/release-skill`. Note the boundary in action —
`/ship` will not touch a version, which is exactly why Task 10 exists.

- [ ] **Step 2: Merge the PR**

The user merges it. `/release` will detect this itself in the next step; nobody needs to
announce it.

- [ ] **Step 3: Return to the default branch**

```bash
git checkout main && git pull --ff-only
```

- [ ] **Step 4: Invoke `/release`**

Expected behaviour, in order:

1. Detects `python / git-tag-only` (`.claude-plugin/plugin.json` wins over `uv.lock`).
2. Confirms the tree is clean and `main` is current.
3. Runs the gate — green.
4. Finds exactly three version literals, all declared.
5. Proposes `0.21.0 → 0.22.0` (minor: this branch is all `feat:`).
6. Stamps all three manifests and shows the diff.
7. Skips the build (`build_command: null`).
8. Commits `chore(release): v0.22.0`, tags `v0.22.0`.
9. **Stops at the confirmation checkpoint.**

- [ ] **Step 5: Verify the refusals are real before confirming**

Before approving, abandon and probe two of them — a refusal that has never fired is an
untested branch:

```bash
git tag -d v0.22.0 && git reset --hard origin/main
echo "stray" >> README.md
```

Re-invoke `/release`. Expected: refusal at Step 1, `README.md` listed as dirty, nothing
stamped. Then:

```bash
git checkout README.md
git checkout -b scratch/refusal-probe
```

Re-invoke `/release`. Expected: refusal — not on the default branch. Then:

```bash
git checkout main && git branch -D scratch/refusal-probe
```

- [ ] **Step 6: Cut the release for real**

Invoke `/release` and confirm at the checkpoint. Expected: tag pushed, GitHub release
created, `claude plugin list` reporting `0.22.0`, and a report ending with the rollback
command.

- [ ] **Step 7: Record what the first real run got wrong**

It will get something wrong — a first run always does. File each defect as an issue
against the skill rather than hot-patching mid-release, and close #93 referencing the
release URL.

---

## Self-Review

**Spec coverage.** Every spec section maps to a task: the `/ship` boundary and shared
resolution → Tasks 1 and 9; the ten-field contract and detection precedence → Task 2;
adapters → Tasks 3–5; the eleven-step workflow, the six hard refusals, the single
checkpoint, and graceful `gh` degradation → Tasks 6–7; the structural test → grown across
Tasks 1–9; evals → Task 8; the integration checklist → Task 9. The spec's note that
`/release` self-detects a merged PR is implemented in Task 6 Step 1 and exercised in
Task 10 Step 4. Issue #94 is out of scope by design.

**Type consistency.** `CONTRACT_FIELDS`, `parse_frontmatter`, `adapter_files()`,
`strip_fenced_code_blocks`, and `EVAL_CASE_KEYS` are each defined once and reused by name
in later tasks. The ten field names are identical in the contract, all four adapters, and
the test. Step headings referenced by Task 7's ordering assertions (`## Step 5 — Stamp`,
`## Step 7 — Commit`, `## Step 8 — Tag`, `## Step 9 — Publish`) match the headings written
in Tasks 6–7 exactly, em dash included.

**Lint trap, called out at both sites.** Tasks 6 and 8 each need a new module-level import
(`assert_version_at_least`, `json`). Both must go in the import block at the top of the
file: `ruff` E402 rejects an import placed after code, so appending it beside the new
tests turns a green suite into a failed gate. `ruff` F401 equally forbids adding them
early in Task 1, where they would be unused — hence one import per task, at the top, when
that task first needs it.

**Known ordering constraint.** Task 1 must land before Task 6: the core links
`docs/git-remote-resolution.md`, and `test_relative_markdown_links_resolve` fails on a
dangling link. Tasks 3–5 may be done in any order among themselves.
