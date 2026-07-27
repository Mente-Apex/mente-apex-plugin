# `/release` skill — design

**Issue:** [#93](https://github.com/menteapex/mente-apex-plugin/issues/93)
**Date:** 2026-07-27
**Status:** approved, ready for planning

## Problem

`/ship` owns **commit → push → open PR** and deliberately stops at the PR. Everything
after it — running the pre-release gate, stamping derived manifests, building artifacts,
tagging, publishing, and verifying that the *installed* tool is the thing just cut — is
retyped from memory, per repo, every time.

Cutting a release by hand in `menteapex-memory-system` (Mente-Apex/menteapex-memory-system#202)
surfaced four repeatable failure modes:

1. **Procedure drift across N places.** The release procedure lived in four locations that
   had silently diverged, all still describing pre-uv tooling.
2. **The stamp-before-tag trap.** Stamping a version into a derived manifest dirties the
   tree; tag first and the tag points at a commit whose manifest carries the old version.
3. **Stale artifact facts nothing verified.** Install docs named a wheel that the build
   never produced, wrong for a long time because no step compared documentation against a
   real build.
4. **Installed-but-undeclared dependency, hidden for weeks.** A test imported `uvicorn`
   with no dev dependency declaring it. The suite only broke on a clean rebuild from the
   lockfile.

Failure 4 is the generalisable one: **a clean rebuild from the lockfile is a latent-
dependency detector**, and a release is the natural place to run it.

All four are the kind of thing a skill should make structurally impossible rather than
rely on the operator remembering.

## Scope boundary vs `/ship`

|  | `/ship` | `/release` |
|---|---|---|
| Owns | commit → push → open PR | gate → stamp → build → tag → publish → verify install |
| Ends at | an open PR | a published tag + a verified installed artifact |
| Touches version | never | it is the whole point |
| Opens/merges PRs | yes / no | no / no |

**The boundary in one line:** `/ship` never touches versions; `/release` never opens or
merges pull requests.

### Are they orthogonal? Not entirely — and the overlap is handled

The two skills are disjoint in **responsibility** but adjacent in **mechanism**. Recording
the contact points so nobody later assumes a clean separation that does not exist:

| Contact point | Status |
|---|---|
| Version handling | `/release` only — disjoint |
| PR lifecycle | `/ship` only — disjoint |
| Branch derivation, collision guards, worktree handling, upstream setting | `/ship` only — `/release` commits to an already-verified default branch |
| Gate / build / tag / publish / install-verify | `/release` only — disjoint |
| `git commit` + `git push` as primitives | **shared** — accepted; a shared primitive, not shared logic |
| Resolving `<remote>` and `<default>` | **shared** — extracted, see below |
| Ordering in the lifecycle | sequential: `/ship` → human merges → `/release`. A workflow dependency, not a code one |
| Trigger space | adjacent ("ship the new version", "push it up and tag it") — covered by eval 7 |

### Shared remote/default-branch resolution

`/ship` Step 1 resolves the remote and the default branch through a four-layer fallback
(local `symbolic-ref` → `git remote show` → `gh` → guess `main`/`master`), because
`origin/HEAD` is unset on any repo that was not freshly cloned. `/release` needs exactly
that resolution twice: to verify it is on an up-to-date default branch, and to run
`publish_command`.

Restating it inline would reproduce **failure mode 1 from the issue** — procedure drift
across N places — inside the very skill written to prevent it.

Resolution: extract it to `docs/git-remote-resolution.md` as the single canonical version,
linked from both `skills/ship/SKILL.md` Step 1 and `skills/release/SKILL.md` Step 1. This
follows the existing `docs/git-convention.md` precedent (a shared doc linked from `/tdd`
and `/ddd`), and `test_skill_integrity.py` already guards those links from dangling.

The extraction edits `/ship`'s working body, not just its description. It therefore lands
as **its own commit, before any `/release` work begins**, so a regression in `/ship` stays
bisectable and is not entangled with a new skill.

### Deviation from the issue, recorded deliberately

The issue proposes that `/release` hand its version-bump commit to `/ship`. That is not
possible under the chosen release shape (below): `/ship`'s core invariant is *never commit
to the default branch*, and the release commit must land on the default branch for the tag
to be correct. Handing off would either break `/ship`'s invariant or strand the bump on a
feature branch requiring a PR.

Resolution: `/release` owns exactly one narrow commit — `chore(release): v<version>`, on
the default branch. This is not duplicated logic; `/release` re-implements no branch
derivation, no PR drafting, no push-with-upstream. It is one `git commit` that `/ship` is
structurally forbidden to make.

This also inverts one line of the issue: preflight **requires** an up-to-date default
branch rather than refusing the default branch.

## Release shape

Direct-to-default. No release PR.

```
$ /release            # on an up-to-date default branch, clean tree
 → gate → bump → stamp → build → commit → tag
 → [one confirmation]
 → push --follow-tags → gh release create → verify install
```

Everything before the confirmation is local and reversible with two commands.

## Architecture

```
docs/git-remote-resolution.md       # shared with /ship — extracted first, own commit
skills/release/
  SKILL.md                          # target-agnostic core. No technology-specific commands.
  references/
    ADAPTER-CONTRACT.md             # the abstraction, defined once
    targets/
      python/
        uv.md                       # WORKING — from memory-system#202
        git-tag-only.md             # WORKING — this repo, dogfooded
      typescript/
        npm.md                      # stub
      java/
        maven.md                    # stub
tests/test_release_skill_structure.py
evals/release-evals.json
```

Poetry, pnpm, and Gradle are deliberately absent (YAGNI). Two working adapters plus two
stubs across three technologies prove the seam both within a technology and across one.
Adding `poetry.md` later is a new file — which is the point of the seam.

### How DIP shaped this

The abstraction is the ten-field **adapter contract**, defined once in
`ADAPTER-CONTRACT.md`. The core workflow in `SKILL.md` names only contract *fields*
(`gate_command`, `artifact_pattern`), never a concrete command.

Injection happens exactly once, at Step 0: detection resolves one adapter file, and every
later step reads through it. Nothing in the core instantiates or hardcodes a technology.

The seam is substitutable: an eval points the core at a fixture adapter whose commands are
harmless echoes, and the workflow runs unchanged.

**OCP, made mechanical.** The structural test asserts `SKILL.md` contains no `uv `, `pip`,
`npm `, `mvn`, `pyproject`, or `plugin.json` literal outside fenced illustrative blocks.
Extending the core by editing it *fails CI*. That test is why this seam will not rot.

**SRP.** One adapter file is exactly one command set — one reason to change. A single
`python.md` branching uv-vs-poetry would have two, which is why the tree is
technology-directory → toolchain-file rather than one file per technology.

## The adapter contract — ten fields

| Field | Meaning | `null` allowed |
|---|---|---|
| `technology` | must match the parent directory name | no |
| `toolchain` | must match the filename stem | no |
| `fingerprint` | the file whose presence selects this adapter | no |
| `version_source` | `file#path` — the one canonical version literal | no |
| `derived_manifests` | list of `file#path` stamped from the source | yes (empty list) |
| `gate_command` | clean rebuild from lockfile + the red/green check | no |
| `build_command` | produce distributable artifacts | yes (no-build targets) |
| `artifact_pattern` | glob the build must emit — verified, not assumed | yes iff no build |
| `publish_command` | the outward-facing step | no |
| `install_verify_command` | proves the installed thing is what was cut | no |

Stub adapters additionally declare `status: stub`, so a half-written adapter can never be
mistaken for a working one and silently drive a real release.

Frontmatter carries the fields. The prose body carries the traps that key/value cannot
express — for example that `.claude-plugin/plugin.json` is canonical while the other two
manifests are stamped, or that `[tool.uv] package = false` means there is no wheel.

### `python/git-tag-only.md` (this repo)

```yaml
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
install_verify_command: claude plugin list | grep mente-apex
```

## Detection — two levels, declared precedence

**Level 1 — technology.** `pom.xml` or `build.gradle[.kts]` → java · `package.json` →
typescript · `pyproject.toml` or `setup.py` → python. More than one match (a Python
backend beside a TS frontend) → **ask**, never guess.

**Level 2 — toolchain within that technology, first match wins:**

- `python`: `.claude-plugin/plugin.json` or `[tool.uv] package = false` → `git-tag-only`;
  else `uv.lock` → `uv`; else ask.
- `typescript`: `package-lock.json` → `npm`; else ask.
- `java`: `pom.xml` → `maven`; else ask.

Precedence is **declared** in `ADAPTER-CONTRACT.md`, not emergent from file ordering. The
structural test asserts fingerprints within a technology directory are disjoint or
explicitly ranked, so a new adapter cannot silently shadow an existing one.

No match at all → refuse with guidance on writing an adapter. `/release` does not generate
adapters interactively; that is a separate concern.

## Workflow

```
0.  Detect      adapter by two-level fingerprint; ask if ambiguous; refuse if unmatched
1.  Inspect     resolve remote + default per docs/git-remote-resolution.md, then:
                on that default branch & up to date · tree clean · tags · current version
2.  Preflight   clean rebuild from lockfile → gate_command          ← latent-dep detector
3.  Single-lit  scan repo for the current version string; every hit must be
                version_source or a declared derived manifest
4.  Version     propose bump from Conventional Commits; user overrides
5.  Stamp       write version_source + derived_manifests; show the diff explicitly
6.  Build       build_command → verify emitted files against artifact_pattern
7.  Commit      chore(release): v<version>                 ┐  all local,
8.  Tag         annotated tag v<version>                   ┘  all reversible
──────────────────── ⚠ ONE CONFIRMATION ────────────────────   first outward-facing action
9.  Publish     publish_command → gh release create (degrades to tag-only)
10. Verify      install_verify_command; shim must resolve outside the checkout
11. Report      version · artifacts · tag URL · installed version · rollback command
```

**Why the confirmation sits at step 9.** It is immediately before the first outward-facing
command, and by that point it can show the *real* artifact names and the *real* tag rather
than predictions. Everything above it undoes with the two commands printed at the prompt:

```sh
git tag -d v<version>
git reset --hard <remote>/<default>
```

**Bump derivation.** Conventional Commits since the last tag. With no tags (this repo's
current state), fall back to commits since the last `chore(release):` commit, else full
history. Always show the reasoning; the user can override.

### Hard refusals — no confirmation overrides these

- not on the default branch, or the default branch is behind the remote
- dirty tree at entry
- gate command exits non-zero
- an undeclared second hardcoded version literal found in the repo
- built artifacts do not match `artifact_pattern`
- the tag already exists
- the resolved adapter declares `status: stub`

### Graceful degradation

`gh` missing or unauthenticated → complete the tag push, skip the GitHub Release, and
report the release-creation URL plus a suggestion to run `gh auth login`. Same fallback
shape `/ship` already uses.

## Invariants the skill encodes

These are the durable lessons, not repo trivia:

- **uv is canonical for Python.** Never `pip`, `pipx`, `pyenv`, Homebrew/system Python, or
  a hand-activated `.venv`.
- **One version literal.** Everything else derives or is stamped. Refuse on a second
  hardcoded version string.
- **Stamp → commit → tag, in that order.** Never tag a dirty tree.
- **Verify artifacts against `artifact_pattern`** before publishing or documenting them.
- **Publishing is separately authorized.** Building and tagging are local and reversible;
  pushing a tag is not.
- **Dependency layout is a release concern.** Tooling deps in `[dependency-groups] dev`;
  user-facing runtime extras in `[project.optional-dependencies]`. This is what makes the
  clean-rebuild latent-dependency check meaningful.
- **Verify the install, not just the build.** The installed shim must resolve outside the
  development checkout.

## Testing

### `tests/test_release_skill_structure.py`

Follows the existing `test_<skill>_skill_structure.py` convention.

- frontmatter declares `name`, `description`, `user-invocable: true`,
  `disable-model-invocation: true`, `allowed-tools`, `metadata.version`
- `metadata.version` passes the shared `skill_version_policy` floor check
- every `.md` under `targets/**` (recursive) fills all ten contract fields
- each adapter's `technology` matches its parent directory; `toolchain` matches its filename
- fingerprints within a technology directory are disjoint or explicitly ranked
- stub adapters declare `status: stub`
- **the core `SKILL.md` contains no technology-specific literal** outside fenced blocks
- the description disclaims `/ship`'s territory and vice versa
- both `/ship` and `/release` link `docs/git-remote-resolution.md`, and neither restates
  the four-layer fallback inline — the duplication cannot silently return

### `evals/release-evals.json`

The issue's six, plus a seventh:

1. happy path (fixture adapter, echo commands)
2. dirty-tree refusal
3. failing-gate refusal
4. stamp-before-tag ordering
5. a second hardcoded version literal → refusal
6. artifact name not matching `artifact_pattern` → refusal
7. `/ship` vs `/release` trigger collision — neither fires on the other's phrasing

Evals and the description-triggering optimization are authored via `/skill-creator`;
`SKILL.md` and the adapters are hand-authored to match this repo's voice.

## Integration checklist

- `docs/git-remote-resolution.md` extracted and `/ship` relinked — **first commit, before
  any `/release` work**
- `README.md` skills table gains a `/release` row
- `.claude-plugin/plugin.json` description + keywords updated
- `.claude-plugin/marketplace.json` description updated (stays in lockstep — the very
  invariant this skill enforces)
- `/ship`'s description updated so the boundary is unambiguous from trigger text alone

## Reference

`docs/RELEASE.md` in Mente-Apex/menteapex-memory-system#202 is a concrete, verified
instance of this workflow for the uv-Python target. It seeds `python/uv.md`, but it is one
*instance* — the core stays technology-agnostic.
