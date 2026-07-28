# `/release`: two-axis adapters and multi-component repositories

Design for [#109](https://github.com/menteapex/mente-apex-plugin/issues/109). Defers
[#111](https://github.com/menteapex/mente-apex-plugin/issues/111).

## The defect

The adapter contract puts two unrelated questions in one file: **how a folder builds and
tests itself**, and **what the repository sends out**. Nothing forced them apart while every
repository had one build system and one thing to ship.

They are independent. Building with `uv` says nothing about whether the result is a wheel, a
Claude plugin, or only a tag. Shipping a plugin says nothing about what built it.

Because they share a file, an adapter is needed per *combination*, and the Python column is
a 2×2 with a hole:

| | no plugin manifest | ships plugin manifest |
|---|---|---|
| **builds a wheel (uv)** | `uv` | `uv-plugin` |
| **builds nothing (`package = false`)** | *(no adapter)* | `git-tag-only` |

The empty square is not hypothetical. `ADAPTER-CONTRACT.md` documents it at lines 414–415
and 157–163: a `package = false` repository with no `.claude-plugin/` directory matches row
1 of the Level 2 table, then hits the `version_source`-does-not-exist check and refuses. A
legitimate repository shape reaches a dead end because the table multiplies two axes instead
of factoring them. Adding poetry would owe two files, not one.

### The failure it already caused

In `mente-apex-memory`, `/release` cut a tag and never built the wheel.

Detection resolved `python/git-tag-only`, whose fingerprint at the time included
`.claude-plugin/plugin.json`. That file is a fact about **what ships**. It was used to decide
a question about **how the repository builds**, and the answer it produced — `build_command:
null` — was wrong: that repository has a setuptools backend and a `mem` console script, so it
builds a wheel perfectly well.

This is the exact failure the contract warns about at lines 417–424 — *"the failure of a
too-broad fingerprint is not that nothing matches; it is that the wrong thing matches
silently."* The contract wrote that warning and then walked into it, because the field it was
reasoning about carried two axes at once.

The release survived only by luck. `install.py` installs from `git+https://…@<tag>` — source
at the tag — and reads only `tag_name` from the releases API, so nothing consumed the wheel
that was never built. The safety came from an unrelated implementation detail, not from the
contract. A repository of the same shape installing from the wheel would have shipped `0.3.0`
under a `0.4.0` tag.

The fix that landed (`python/uv-plugin`, commit `01c6218`) fills in the fourth square. The
cause is that a build decision was allowed to fingerprint on shipping evidence at all.

### The second symptom

`python/uv-plugin` inlines npm commands into a Python adapter:

```yaml
gate_command: uv sync && uv run pytest && uv run ruff check . && uv run black --check .
  && npm --prefix dashboard/web ci && npm --prefix dashboard/web test
  && npm --prefix worker ci && npm --prefix worker test
```

Those commands are not wrong, they are mislocated — and they name paths only one checkout
has. The adapter's own Traps section concedes it: *"A second repo of this shape without a
`worker/` or `dashboard/web` directory splits this adapter."*

## Design

### Part 1 — Split the adapter in two

**Build adapter** — `references/build/<technology>/<toolchain>.md`. How a component builds
and tests itself.

| Field | Notes |
|---|---|
| `technology`, `toolchain` | unchanged; must match directory and filename stem |
| `fingerprint` | build evidence only — see the separation rule below |
| `version_source` | where this toolchain keeps the version literal |
| `relock_command` | unchanged |
| `gate_command` | unchanged |
| `build_command` | unchanged |
| `artifact_pattern` | unchanged |
| `distribution_names` | unchanged — see "where the axes tangle" below |
| `install_verify_command` | proves the *built* thing installs |
| `tag_pattern` | repo-level in effect; read only from the root component |
| `publish_command` | repo-level in effect; read only from the root component |

**Distribution adapter** — `references/distributions/<kind>.md`. What else goes out, and how
you confirm it arrived.

| Field | Notes |
|---|---|
| `kind` | must match the filename stem |
| `fingerprint` | shipping evidence only |
| `derived_manifests` | mirrors of the canonical version, including the `?` optional marker |
| `install_verify_command` | proves the *shipped* thing arrived |
| `release_command` | the forge's release object |

A repository may resolve **no** distribution adapter. That is the empty square: it builds, it
tags, and nothing further mirrors or ships.

#### Where the axes tangle, and how it resolves

Two fields do not cleanly belong to one side, and pretending otherwise would be the same
mistake at smaller scale.

**`distribution_names` goes on the build adapter, not the distribution adapter** — despite the
name. Every value it holds is a path the *toolchain* determines: `pyproject.toml#project.scripts`,
`package.json#.name` and `#.bin`, `pom.xml#/project/groupId`. None is decided by what the
repository ships. The naming coincidence is not evidence.

**`install_verify_command` goes on both, and both run.** `uv tool install --force . && which
<distribution-name:binary>` verifies what the build produced; `claude plugin list` verifies
what the distribution shipped. They are two checks of two different things, and `uv-plugin.md`'s
own verification section already treats them that way — *"Three things were released, so check
all three."* Forcing them into one field is what made that command a compound in the first
place.

**`release_command`** stays as the contract already has it, forge wart intact (lines 281–287).
It moves to the distribution adapter, where the wart gets cheaper by accident: fewer files copy
it than copied it across every build adapter.

#### The separation rule

> A build adapter may fingerprint only on build evidence. A distribution adapter may
> fingerprint only on shipping evidence. Neither may look at the other's.

- **Build evidence:** `uv.lock`, `package-lock.json`, `Cargo.lock`, `pom.xml`, `Cargo.toml`,
  `pyproject.toml`, the build backend, `[tool.uv] package == false`.
- **Shipping evidence:** `.claude-plugin/plugin.json`, registry configuration, publish
  targets.

Under this rule the wheel incident cannot recur: `plugin.json` has no path by which to reach
`build_command`. This is a stronger claim than "we added the missing adapter," and it is the
thing worth writing into the contract.

#### Migration of the six existing adapters

| today | build adapter | distribution adapter |
|---|---|---|
| `python/uv` | `python/uv` | — |
| `python/uv-plugin` | `python/uv` | `claude-plugin` |
| `python/git-tag-only` | `python/uv-nobuild` | `claude-plugin` |
| `typescript/npm` | `typescript/npm` | `npm-registry` |
| `java/maven` | `java/maven` | `maven-central` |
| `rust/cargo` | `rust/cargo` | `crates-io` |

Three Python files become two. `uv-plugin` ceases to exist. The empty square becomes a build
adapter with no distribution adapter — a repository that builds nothing and ships nothing but
a tag — and stops being a dead end.

`python/uv-nobuild` is a real find rather than a rename. The repository that prompted "why
wasn't the wheel rebuilt" is `python/uv` + `claude-plugin`; `uv-nobuild` is for a genuinely
different repository (`[tool.uv] package = false`, like this one). Splitting the axes is what
makes those two distinguishable at all — today they resolve to the same file.

### Part 2 — Components

#### Stage 1 — find them

Walk the repository for build evidence. One exclusion rule, not a list: **only files tracked
by git count.** That eliminates `node_modules`, `.venv`, `dist`, `build` and `target` in one
move, because all of them are gitignored, and it stays correct as repositories change in a
way a hardcoded skip-list would not.

#### Stage 2 — the ask

- **One component** (the root) → proceed silently. This is every repository today; nothing
  changes for them.
- **More than one** → stop, show what was found and what is planned for each, and proceed
  only on confirmation.

```
Found 3 components:
  .              python/uv        build and release
  dashboard/web  typescript/vite  check only
  worker         typescript/npm   check only
Correct?
```

No configuration file is needed. `/release` is already interactive — it has a confirmation
checkpoint before it pushes — so one further question, asked only in repositories of this
shape, is cheap. Asking also beats a recorded list in one specific way: a file goes stale
silently when someone adds a folder, whereas the walk finds it and asks.

Tracked-but-not-a-component (`tests/fixtures/sample-project/package.json`) is the real risk,
and the ask is precisely what handles it. Nothing is guessed.

#### Stage 3 — resolve each one

Unchanged. The existing Level 1 + Level 2 procedure, run inside each component directory
rather than at the repository root. No new detection procedure.

This is where the old *"more than one technology matches → refuse"* rule goes, without being
weakened: it now applies **within a component**. A single folder holding both a
`pyproject.toml` and a `package.json` still refuses. What used to be an accident —
`mente-apex-memory` escaping the refusal only because its `package.json` files sit in
subfolders — becomes the actual rule.

#### Component kinds

- **build and release** — gate it, build it; its output is part of this release.
- **check only** — gate it, nothing else. Something else ships it on its own cadence.

Default: the root builds and releases, every other component is check-only. Correct for
`mente-apex-memory`; the confirmation catches any repository where it is not.

**Check-only is not `build_command: null`.** That is a build adapter claiming "this toolchain
builds nothing, ever." Check-only is a component claiming "this release is not building me."
Different statements at different levels, so nothing is overloaded.

The definition is about **who owns the outward step**, not about visibility. `worker/` is
`private: true` *and* deployed to Cloudflare — it goes outward, but by `wrangler`, on its own
cadence, when someone decides. `/release` only refuses to leave it broken. This is already
the settled position in `uv-plugin.md` lines 100–103: folding the deploy in would put a
deploy failure *after* the tag is public.

### Part 3 — One version

There is exactly one real version per release, from the root component's build adapter
`version_source`. Everything else either mirrors it or carries no version at all.

**Why the current check cannot catch a stale mirror.** Step 3 today asks: *of everything that
says `0.4.0`, is each one declared?* That finds an undeclared copy of the **current** version.
It is blind by construction to `worker/package.json` pinned at `0.3.0`, because it never
examines anything that does not already say `0.4.0`.

**The new question:** for every component manifest, does its own version field match the
canonical version? Not a text search — the self-version key each format already defines
(`.version` in `package.json`, `project.version` in `pyproject.toml`), so dependency pins are
not swept in.

A mismatch is a refusal, and the message names the two ways out:

1. **Nothing consumes it** → delete the field. This is `worker/package.json`; nothing anywhere
   reads that number, it exists because `npm init` wrote it. `uv-plugin.md` lines 114–119
   already reached this conclusion in prose; the design makes the tool enforce it.
2. **Something consumes it** → that component is published, which makes it a released
   component, which is [#111](https://github.com/menteapex/mente-apex-plugin/issues/111).

The rule is closed: a version literal is either read by someone or it is not. No configuration
is required, because nothing is declared — the repository is simply not allowed to hold a
number nobody reads.

**Known limit.** A component manifest that legitimately should be stamped in lockstep has
nowhere to say so, because its path is repository-specific and shared adapters cannot hold
paths. No such case exists today, and when one appears it is #111 — the same trigger, since a
manifest worth stamping is a manifest something publishes.

## What changes

1. **`references/ADAPTER-CONTRACT.md`** — the fourteen-field table becomes two tables plus
   three repo-level fields; new components section; detection section gains stage 1; the
   separation rule is written down as the thing that makes the wheel incident impossible.
2. **`SKILL.md`** — Step 0 resolves a component list and a distribution adapter instead of one
   adapter. Gate (2), relock (5a) and build (6) become loops. Step 3 takes the new version
   check. Step 10 runs the build adapter's `install_verify_command` and then the distribution
   adapter's, where one resolved. One new confirmation, only when there is more than one
   component.
3. **Adapter files** — `targets/` → `build/`; `distributions/` is new; `uv-plugin` deleted;
   `git-tag-only` split into `build/python/uv-nobuild` + `distributions/claude-plugin`.
4. **`tests/test_release_skill_structure.py`** — field-set checks split by adapter kind, plus
   a new check enforcing the separation rule in both directions. Selector-syntax and
   placeholder-vocabulary checks are unchanged.
5. **This repository releases itself with `/release`** — it becomes `python/uv-nobuild` +
   `claude-plugin` and must keep working.
6. **`mente-apex-memory`** — a separate issue in that repository: `python/uv` +
   `claude-plugin` + two check-only components, and `worker/package.json` loses its version
   field.

### One PR, not two

Splitting the axes first and adding components second leaves a worse halfway state than
either end. With the axes split alone, `uv-plugin`'s npm gates have nowhere to live, so
`mente-apex-memory` loses its JavaScript gating until the second PR lands. Keeping
`uv-plugin` alive as a deliberate stepping stone would work but means writing a file already
agreed to be wrong and then unpicking it. And because this repository releases *itself* with
this skill, a half-migrated state is a state in which no release can be cut.

### `status: stub`

Nothing live becomes a stub. `build/python/uv`'s fields are unchanged from the verified
original; `uv-nobuild` and `claude-plugin` are the two halves of adapters already exercised on
real releases — which is exactly what the contract's "inherited from a verified sibling"
clause (lines 353–355) covers. The npm, maven and cargo distribution adapters are stubs, as
their build halves already are.

The component machinery itself is genuinely unexercised. `status: stub` does not apply — it is
not an adapter — but it must not be claimed as working until it has been run against
`mente-apex-memory` for real, per the contract's rule that the exit from unexercised is
exercising it.

## Deferred

**[#111](https://github.com/menteapex/mente-apex-plugin/issues/111) — publishing several
components to several registries under one tag.** No component in the one multi-stack
repository available has its outward step owned by `/release`, except the repo-level git push,
which cannot half-fail. There is nothing to exercise a two-registry publish against, and
shipping unverified commands is what `status: stub` exists to prevent. The field layout must
not foreclose it: `publish_command` remains a field a component *could* carry, even though
this design only ever resolves one at the repository level.

## Housekeeping

#109's "Current state" section states that `python/uv-plugin` and its `gate_command` are
uncommitted work in progress. They are committed (`01c6218`). The issue should be corrected so
a later reader does not go looking for an unstaged diff that does not exist.
