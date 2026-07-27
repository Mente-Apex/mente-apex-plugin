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

Declared as YAML frontmatter. Every field is required; four may be `null`.

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

A `null` `version_source` is not a shortcut for "we have not filled this in yet" — it is a
positive claim that the repository stores the version nowhere, because the git tag *is*
the version. Some ecosystems work this way: no manifest exists to stamp. The core skips
its single-literal check, its stamp, and its release commit for such a target; the tag is
created on the existing `HEAD` and nothing else changes. `derived_manifests` must then be
the empty list, since there is no source for anything to be derived from.

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
