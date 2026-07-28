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

## The eleven fields

Declared as YAML frontmatter. Every field is required; five may be `null`.

| Field | Meaning | `null` allowed |
|---|---|---|
| `technology` | Must equal the parent directory name. | no |
| `toolchain` | Must equal the filename stem. | no |
| `fingerprint` | The file whose presence selects this adapter. | no |
| `version_source` | `path/to/file#selector` — the one canonical version literal. | yes — targets where the tag itself is the version and no manifest carries it |
| `derived_manifests` | List of `path#selector` stamped *from* the source. | yes — empty list |
| `gate_command` | Clean rebuild from the lockfile, then the red/green check. | no |
| `build_command` | Produce distributable artifacts. | yes — no-build targets |
| `artifact_pattern` | Glob the build must emit. Verified, never assumed. | yes — iff no build |
| `publish_command` | The outward-facing step. | no |
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

Role names are the adapter's own vocabulary. A new naming role is a new key, never a
twelfth field.

**A selector may address a table rather than a value** — `python/uv`'s binary name is the
*key* under `[project.scripts]`, not a value anywhere. When a selector resolves to a
mapping, the role's value is that mapping's single key. **If it holds more than one entry,
refuse and ask which** — do not pick. Guessing here is the whole failure this field exists
to prevent, and it would arrive at Step 10 where nothing else is checking.

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
| `<distribution-name:role>` | reading the `role` key of this adapter's `distribution_names` |

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

1. Create `references/targets/<technology>/<toolchain>.md` with all eleven fields.
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
