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

## The fourteen fields

Declared as YAML frontmatter. Every field is required; seven may be `null`.

| Field | Meaning | `null` allowed |
|---|---|---|
| `technology` | Must equal the parent directory name. | no |
| `toolchain` | Must equal the filename stem. | no |
| `fingerprint` | The file whose presence selects this adapter. | no |
| `version_source` | `path/to/file#selector` — the one canonical version literal. | yes — targets where the tag itself is the version and no manifest carries it |
| `derived_manifests` | List of `path#selector` stamped *from* the source. | yes — empty list |
| `relock_command` | Regenerates the lockfile the stamp just invalidated. | yes — targets whose lockfile does not record the project's own version |
| `gate_command` | Clean rebuild from the lockfile, then the red/green check. | no |
| `build_command` | Produce distributable artifacts. | yes — no-build targets |
| `artifact_pattern` | Glob the build must emit. Verified, never assumed. | yes — iff no build |
| `tag_pattern` | The tag this target's ecosystem expects. Expands to `<tag>`. | no |
| `publish_command` | The outward-facing step. | no |
| `release_command` | Creates the forge's release *object* from the pushed tag. | yes — targets where the tag is the whole release |
| `install_verify_command` | Proves the installed thing is what was just cut. | no |
| `distribution_names` | Map of *role* → `path/to/file#selector`, naming the installed thing. | yes — iff no command references `<distribution-name:…>` |

A `null` `version_source` is not a shortcut for "we have not filled this in yet" — it is a
positive claim that the repository stores the version nowhere, because the git tag *is*
the version. Some ecosystems work this way: no manifest exists to stamp. The core skips
its single-literal check, its stamp, and its release commit for such a target; the tag is
created on the existing `HEAD` and nothing else changes. `derived_manifests` must then be
the empty list, since there is no source for anything to be derived from.

A `null` `distribution_names` is likewise a positive claim: nothing this adapter runs needs
to name the installed thing. `python/git-tag-only` verifies with `claude plugin list`,
which names no distribution, so it declares `null`. Any adapter whose commands contain
`<distribution-name:…>` must declare every role it references.

### Why a map and not a single name

One ecosystem's "name" is often several. npm installs by *package* name
(`package.json#.name`) and verifies the *binary* on `PATH`, which is a key under
`package.json#.bin` and frequently differs — `@scope/my-tool` can install a binary called
`mt`. Maven addresses a distribution by *two* coordinates, group and artifact.

A single field forces those cases either to be wrong or to smuggle syntax into the value —
encoding `groupId:artifactId` as one selector puts Maven's coordinate separator inside a
field the contract defines as one path and one selector. The map keeps each role a clean
selector and puts the ecosystem's joining syntax back in the command, where it belongs:

```yaml
distribution_names:
  group:    pom.xml#/project/groupId
  artifact: pom.xml#/project/artifactId
```
```
-Dartifact=<distribution-name:group>:<distribution-name:artifact>:<version>
```

Role names are the adapter's own vocabulary. A new naming role is a new key, never a new
contract field.

**A selector may address a table rather than a value** — `python/uv`'s binary name is the
*key* under `[project.scripts]`, not a value anywhere. When a selector resolves to a
mapping, the role's value is that mapping's single key. **If it holds more than one entry,
refuse and ask which** — do not pick. Guessing here is the whole failure this field exists
to prevent, and it would arrive at Step 10 where nothing else is checking.

### `relock_command` — a lockfile that records its own project's version

Most lockfiles pin *dependencies*, and a version bump does not touch them. Several pin the
project **itself**: `Cargo.lock` carries an entry for the crate being built, this repo's
own `uv.lock` carries `version = "…"` for the root project, and `package-lock.json` repeats
the package's version twice. For those targets the stamp in Step 5 makes the lockfile stale
the moment it lands, and nothing downstream notices until the toolchain refuses to publish
from a dirty tree — after the confirmation checkpoint, on a branch that is already
committed and tagged.

**Why this is not just another `derived_manifests` entry.** Entries there are `path#selector`
files the core *stamps*, by rewriting the addressed field. A lockfile is not stamped: it is
**regenerated** by the toolchain, from the manifest, with a hash and a resolution the core
has no business hand-editing. Listing it as derived would also collide with the core's
single-version-literal check, which excludes lockfiles precisely because they legitimately
repeat versions the adapter never declared.

So the adapter names a *command*, and the core runs it in the one window where its output
can still be staged — after the stamp, before the build that consumes it, before the commit:

```yaml
relock_command: uv lock                             # uv
relock_command: npm install --package-lock-only     # npm
relock_command: cargo generate-lockfile --offline   # cargo
relock_command: null                                # nothing pins this project's version
```

`null` is a positive claim, exactly like the other nullable fields: **stamping this target's
manifests cannot make anything stale.** Maven declares it — it has no lockfile at all.

The core stages whatever the command modified, so the command must be *narrow*. A relock
that also upgrades dependencies (`npm install`, `cargo update`) sweeps an unreviewed
dependency change into the release commit; prefer the offline, manifest-only form of your
toolchain's command and keep the resolution unchanged.

`relock_command` requires a non-`null` `version_source`: a target that stamps nothing
invalidates nothing, and `tests/test_release_skill_structure.py` fails the pair.

### `tag_pattern` — the tag convention is the target's, not the core's

`v<version>` looks universal and is not. A Go module at the repository root wants exactly
that; a Go **submodule** wants `sub/module/v1.2.3`, and the path prefix is not decoration —
the proxy resolves the module by it. `maven-release-plugin` defaults to
`<artifactId>-<version>`. Ruby gems and many monorepo conventions differ again.

So the pattern is the adapter's, and the core reads it as `<tag>` wherever it names a tag:
the annotated tag itself, the release commit's subject, the confirmation checkpoint, the
rollback commands, and the report. **`tag_pattern` is expanded once**, as soon as the
version settles in Step 4 — before the tag exists — because Step 4's "this tag is already
taken" refusal needs the resolved string too.

The pattern may use any placeholder in the vocabulary below **except `<tag>` itself**,
which is what it defines. Nothing else in the vocabulary is self-referential, so the
substitution has no cycle detection and is not going to grow any.

There is no `null` case. A target that builds nothing is ordinary; a target that publishes
nothing outward is conceivable; a release with no tag is not a release.

### `release_command` — the forge is a detail too

`publish_command` sends the version outward. What follows it — the *release object* on
GitHub, GitLab, Gitea, or a self-hosted forge — is a separate act, and it is the one the
core used to perform itself with a hardcoded `gh release create`. That made every non-
GitHub repository unreleasable without editing the core, which is precisely what this
contract exists to prevent.

`null` is a real value here, and a positive claim: **the tag is the whole release.** A
target publishing to a registry that has no notion of a release page declares `null`, and
the core skips the step exactly as it skips a `null` `build_command`.

```yaml
# GitHub
release_command: gh release create <tag> --title <tag> --notes-file <release-notes-file>

# GitLab — illustrative, never exercised here; verify the flags against your `glab`
release_command: glab release create <tag> --name <tag> --notes-file <release-notes-file>

# a registry-only target with no release page
release_command: null
```

**A failure here is not a failed release.** `release_command` runs after the push, so by
the time it can fail the tag is public and the version is installable. The core reports it
as a release that shipped without its release object — never as a release to re-cut. That
degradation is the core's rule, not the adapter's, so an adapter does not restate it.

**The known wart of putting this in the technology adapter.** The forge is genuinely
orthogonal to the language: a Python project and a Go project on the same GitLab instance
want the identical command, and here each would declare its own copy. That is accepted for
now — a second resolution axis costs a second detection procedure, a second precedence
table, and a merge rule, for a duplication that today spans four adapters and one forge. If
a third forge arrives and the copies start disagreeing, this field is the thing that gets
hoisted into a forge adapter; nothing here has to be unpicked first.

## The placeholder vocabulary

Commands and patterns may contain these tokens and **no others**. The list is closed: a
token outside it is a value the running agent has to guess, and a guessed distribution name
is exactly the error `artifact_pattern` exists to catch, arriving one step later at the
point where nobody is checking.

| Placeholder | Substituted from |
|---|---|
| `<remote>` | the resolution in [../../../docs/git-remote-resolution.md](../../../docs/git-remote-resolution.md) |
| `<default>` | the same resolution — the default branch |
| `<version>` | the version being released, as computed in Step 4 |
| `<tag>` | expanding this adapter's own `tag_pattern`; unavailable *inside* `tag_pattern` |
| `<release-notes-file>` | a path the core writes the grouped Conventional Commit notes to |
| `<distribution-name:role>` | reading the `role` key of this adapter's `distribution_names` |

`<release-notes-file>` is a *path* rather than the notes themselves for a reason worth
stating: release notes are multi-line and routinely contain quotes, backticks and `$`.
Substituting them into a command string would make every adapter author responsible for
shell quoting, and the failure mode of getting it wrong is a release note that silently
executes part of a commit message.

Only roles the adapter actually declares are bound. `<distribution-name:binary>` in an
adapter whose map has no `binary` key is an unbound token, exactly like `<tool-name>` would
be — which is also what makes a `null` map with a name-using command a failure rather than
an omission.

`tests/test_release_skill_structure.py` scans every field of every adapter for `<…>` tokens
and fails on any this table does not bind, so the vocabulary cannot drift open again. It
matches tokens permissively and subtracts the bound set — the inverse (matching only
well-formed tokens) would let `<TOOL_NAME>` or `<gemName>` through as "not a placeholder".

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
| `Cargo.toml` | `rust` |

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
| `rust` | `Cargo.lock` | `cargo` |

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

1. Create `references/targets/<technology>/<toolchain>.md` with all fourteen fields.
   `tag_pattern` is the one people forget, because `v<version>` feels like a default
   rather than a choice. `relock_command` is the one people get wrong: check whether your
   lockfile records the project's *own* version before declaring it `null`.
2. Declare `status: stub` until you have cut a real release with it.
3. Add its fingerprint row to the Level 2 table above, positioned so its precedence
   against existing adapters is explicit.
4. **If the technology is new** — the first adapter under that directory — add a Level 1
   row for it as well, again positioned deliberately. A Level 2 row alone is unreachable:
   detection resolves the technology first, so an adapter whose technology no Level 1
   fingerprint selects is never considered, and the run refuses with "nothing matches"
   while the adapter sits right there. Adding a toolchain to an *existing* technology
   needs Level 2 only.
5. Run `uv run pytest tests/test_release_skill_structure.py` — the guard checks the field
   set, the directory/filename agreement, and fingerprint disjointness.

You do not touch `SKILL.md`. If you find yourself wanting to, the contract is missing a
field — add it here, to every adapter, and to the test, in that order.
