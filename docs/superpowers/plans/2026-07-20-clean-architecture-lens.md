# Clean-Architecture Lens + Overlap Hub — Implementation Plan (Plan 2 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `clean-architecture` — a deliberate **audit lens** on the shared refactor engine covering the net-new component/dependency-graph residue of *Clean Architecture* (dependency-rule/boundary audit, cycles, stability) — and migrate the pairwise `solid-gof-overlap.md` into a shared `docs/lens-overlap.md` hub so the fourth lens doesn't force an O(n²) map explosion.

**Architecture:** `clean-architecture` follows the house pattern (`SKILL.md` orchestrator + `references/` rubric + `agents/` roles) and plugs into `docs/refactor-workflow.md` like `solid`/`gof`. It is **audit-first, no build mode** (building the layered shape stays `ddd`'s job). Its checks are tiered: **headline** (dependency-direction, cycles, stability — robust, tool-assisted via `grimp`/`import-linter` with graceful agent-driven fallback) run by default; **secondary** (packaging REP/CCP/CRP, Screaming Architecture, composition root) and the **appendix** (abstractness / Main-Sequence metrics, caveated in Python) are opt-in. It emits an `importlinter` contract as a leave-behind CI tripwire. Correctness is enforced by a dependency-free structural pytest guard + evals.

**Tech Stack:** Markdown skill/doc files; Python 3.14 stdlib for the structural test (`pathlib`, `re`, `json` — no PyYAML); `pytest`. Runtime graph tooling (`grimp`/`import-linter`, or `dependency-cruiser` for TS) is detected-and-used-or-degraded-from at skill runtime, never a hard install. **Depends on Plan 1** (the `docs/reports/<lens>/` convention and the greened baseline).

## Global Constraints

- **Source spec:** `docs/superpowers/specs/2026-07-20-clean-code-and-clean-architecture-integration-design.md`.
- **Prerequisite:** Plan 1 (`2026-07-20-clean-code-substrate.md`) is applied — baseline green, reports at `docs/reports/<lens>/`, three version mirrors at `0.12.0`.
- **Test runner (pinned):** `.venv/bin/python -m pytest` — repo targets **Python 3.14**; bare `python3` (3.9) lacks `tomllib` and breaks `test_skill_integrity.py` collection.
- **Three version mirrors** must stay equal: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `pyproject.toml`. This plan bumps all three `0.12.0` → `0.13.0` (minor: new skill) in one task.
- **House skill layout (verbatim):** `skills/<name>/SKILL.md`, `references/*.md`, `agents/*.md`.
- **SKILL.md frontmatter (verbatim):** `name:`, `description:` (block scalar), `user-invocable: true`, `metadata:` → `version: "0.1.0"`.
- **Overlap hub:** `docs/lens-overlap.md` replaces `docs/solid-gof-overlap.md`. It **must keep all 23 GoF pattern names** (`test_skill_integrity.py::test_overlap_map_covers_all_23_patterns`) and the SOLID↔GoF table, and add `clean-architecture` rows. **Every one of the 11 references** must be repointed, including the two inside `tests/test_skill_integrity.py` (`INTEGRITY_SCAN_GLOBS` line ~38 and `OVERLAP_MAP` line ~120).
- **Link-resolution guard:** `test_skill_integrity.py::test_relative_markdown_links_resolve` scans `skills/{gof,solid,tdd}/**` + `docs/refactor-workflow.md` + `docs/refactor-agents/*.md` + the overlap map + `docs/git-convention.md`. After the migration those files must link `lens-overlap.md` (which exists) and `solid-gof-overlap.md` must be gone with no dangling reference left.
- **Tooling posture:** detect `grimp`/`import-linter` (Py) or `dependency-cruiser`/`madge` (TS) via any available runner (`uvx`, `pipx run`, or a project-local install); if none is available, **degrade to agent-driven import reading** and say so in the report. Never require a hard install. (Note: `uv` is not installed in the dev environment — the degrade path must be real, not theoretical.)
- **Reports:** `docs/reports/clean-architecture/` (git-excluded), per Plan 1's convention.
- **Descriptive names only** — no single-letter/abbreviated variables, including in comprehensions.
- **Git convention:** work on `clean-architecture/skills`; offer (never auto) commit + PR at the very end.

---

## File Structure

- `docs/lens-overlap.md` — **renamed** from `solid-gof-overlap.md`; retitled hub, 23 patterns kept, `clean-architecture` rows added.
- `docs/solid-gof-overlap.md` — **deleted** (migrated).
- `tests/test_skill_integrity.py` — **modified**: repoint `OVERLAP_MAP` + `INTEGRITY_SCAN_GLOBS` to `lens-overlap.md`.
- `skills/{solid,gof}/**`, `docs/refactor-workflow.md`, `docs/refactor-agents/reviewer.md`, `README.md` — **modified**: overlap-map link repointed.
- `skills/clean-architecture/SKILL.md` — orchestrator: tiers, opt-in flags, tooling posture, audit-first, carve, guardrails, file map.
- `skills/clean-architecture/references/principles.md` — tiered rubric + violation signatures + when-NOT-to + tier assignment.
- `skills/clean-architecture/references/python.md` — `grimp`/`import-linter` detection, metric how-to, the `importlinter` artifact, graceful degrade.
- `skills/clean-architecture/references/report-template.md` — report format + contract section.
- `skills/clean-architecture/agents/analyzer.md`, `reviewer.md`, `implementer.md` — the three roles (pointers into the shared roles + CA rubric).
- `evals/clean-architecture-evals.json` — trigger + behaviour evals.
- `tests/test_clean_architecture_skill_structure.py` — **NEW** structural guard.
- `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `pyproject.toml` — register + bump to `0.13.0`.
- `solid-reports/` (repo root, stale/git-ignored) — housekeeping delete.

**Task boundaries:** one file (or tightly-coupled group) per task; each ends green + committed.

---

## Task 0: Working branch

- [ ] **Step 1: Ensure the working branch**

Run:
```bash
cd /Users/ai/Projects/mente-apex-plugin
git checkout clean-architecture/skills
git status
```
Expected: on `clean-architecture/skills` (holds the spec + Plan 1 commits), clean tree. Confirm Plan 1 is applied: `test -f docs/clean-code-standard.md && echo "plan1 applied"`.

---

## Task 1: Migrate the overlap map to a shared hub + structural harness

**Files:**
- Create: `tests/test_clean_architecture_skill_structure.py`
- Rename: `docs/solid-gof-overlap.md` → `docs/lens-overlap.md` (+ content)
- Modify: `tests/test_skill_integrity.py`, `docs/refactor-workflow.md`, `docs/refactor-agents/reviewer.md`, `skills/solid/**`, `skills/gof/**`, `README.md`

**Interfaces:**
- Produces: `REPO_ROOT`, `read_skill_file(relative_path)`, `parse_frontmatter(text)` reused by later tasks; and the shared `docs/lens-overlap.md`.

- [ ] **Step 1: Write the failing test (harness + hub)**

Create `tests/test_clean_architecture_skill_structure.py`:
```python
"""Structural guard for the clean-architecture lens and the shared overlap hub.

Authored prose, not runtime code: assert files exist and carry the sections the
orchestration and the plugin loader depend on. Dependency-free (no PyYAML).
"""
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CA_SKILL_DIR = REPO_ROOT / "skills" / "clean-architecture"
LENS_OVERLAP = REPO_ROOT / "docs" / "lens-overlap.md"


def read_skill_file(relative_path):
    """Read a file under skills/clean-architecture/, failing the test if absent."""
    target = CA_SKILL_DIR / relative_path
    assert target.is_file(), f"expected skill file missing: {target}"
    return target.read_text(encoding="utf-8")


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


def test_lens_overlap_hub_replaces_pairwise_map():
    assert LENS_OVERLAP.is_file(), "docs/lens-overlap.md must exist"
    assert not (REPO_ROOT / "docs" / "solid-gof-overlap.md").exists(), \
        "docs/solid-gof-overlap.md must be gone (migrated to lens-overlap.md)"
    text = LENS_OVERLAP.read_text(encoding="utf-8")
    # the hub adds clean-architecture as a participating lens
    assert "clean-architecture" in text.lower(), "hub must carry clean-architecture rows"
    # the SOLID<->GoF content survives the move (spot-check canonical entries)
    for kept in ["Strategy", "Singleton", "Abstract Factory", "DIP"]:
        assert kept in text, f"hub lost SOLID/GoF content: {kept}"


def test_no_stale_overlap_references_remain():
    offenders = []
    scan_dirs = ["skills/solid", "skills/gof", "docs/refactor-workflow.md",
                 "docs/refactor-agents", "README.md", "tests/test_skill_integrity.py"]
    for scan in scan_dirs:
        target = REPO_ROOT / scan
        files = target.rglob("*") if target.is_dir() else [target]
        for candidate in files:
            if candidate.is_file() and candidate.suffix in {".md", ".py"}:
                if "solid-gof-overlap" in candidate.read_text(encoding="utf-8"):
                    offenders.append(str(candidate.relative_to(REPO_ROOT)))
    assert not offenders, f"stale solid-gof-overlap references remain: {offenders}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_clean_architecture_skill_structure.py -q`
Expected: FAIL — `docs/lens-overlap.md must exist`.

- [ ] **Step 3: Rename the file (preserve history)**

Run:
```bash
git mv docs/solid-gof-overlap.md docs/lens-overlap.md
```

- [ ] **Step 4: Retitle the hub and add clean-architecture rows**

In `docs/lens-overlap.md`, change the top heading and intro from the SOLID↔GoF
framing to a hub framing (keep the existing SOLID↔GoF table and all 23 pattern
rows unchanged), and append a clean-architecture section. Replace the first
paragraph with:

```markdown
# Lens overlap map (hub)

Every refactor lens's reviewer reads this. The lenses see the same code from
different altitudes; this hub keeps them cross-referencing instead of issuing
conflicting recs. One hub rather than pairwise maps, so adding a lens is additive.
```

Then, after the existing SOLID↔GoF table and its **Reconciliation rule**, append:

```markdown
## clean-architecture ↔ the others

`clean-architecture` audits the component/dependency graph (an altitude above
`solid`'s classes and orthogonal to `ddd`'s domain). Shared smells reconcile as
one change; the running lens files it, the other references the rec ID.

| clean-architecture finding | Overlaps | Reconciliation |
|---|---|---|
| dependency-direction violation (core imports framework/DB) | `ddd` (missing port / DIP), `solid` (DIP) | one change; `ddd` frames it as "missing port on aggregate X", CA as "boundary violation: use-case imports the web framework" — whoever runs files it |
| cycle (ADP) | `solid` (DIP inverts an edge) | CA files the cycle; DIP is the fix mechanism, not a second rec |
| composition-root / infra constructed in core | `gof` (Abstract Factory at the boundary), `clean-code` (separate construction from use) | CA files it; GoF/clean-code are the fix idioms |
| Humble Object at a boundary | `gof` (the pattern) | hand off to `gof` |

**Carve with `ddd` (the tightest seam):** `ddd` asks *"is the domain modelled
well?"*; `clean-architecture` asks *"is the dependency structure sound, regardless
of domain richness?"* A codebase can pass one and fail the other.
```

- [ ] **Step 5: Repoint every reference**

Enumerate and replace the string `solid-gof-overlap` with `lens-overlap` across
the repo (excluding narrative specs/plans, which may reference the migration by
name):
```bash
grep -rln "solid-gof-overlap" --include="*.md" --include="*.py" . \
  | grep -v "docs/superpowers/"
```
For each file listed — `tests/test_skill_integrity.py` (both the
`INTEGRITY_SCAN_GLOBS` entry and `OVERLAP_MAP = DOCS_DIR / "solid-gof-overlap.md"`),
`docs/refactor-workflow.md`, `docs/refactor-agents/reviewer.md`,
`skills/solid/SKILL.md`, `skills/solid/agents/reviewer.md`, `skills/gof/SKILL.md`,
`skills/gof/references/python.md`, `skills/gof/agents/reviewer.md`, `README.md` —
replace `solid-gof-overlap` with `lens-overlap` (filenames and prose alike). Then
verify none remain outside `docs/superpowers/`:
```bash
grep -rn "solid-gof-overlap" --include="*.md" --include="*.py" . | grep -v "docs/superpowers/"
```
Expected: no matches.

- [ ] **Step 6: Run tests — hub + integrity green**

Run: `.venv/bin/python -m pytest tests/test_clean_architecture_skill_structure.py tests/test_skill_integrity.py -q`
Expected: PASS — hub exists with CA rows, no stale refs, all 23 patterns still present (`test_overlap_map_covers_all_23_patterns` now reads `lens-overlap.md`), links resolve.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: migrate solid-gof-overlap.md to shared docs/lens-overlap.md hub (+ clean-architecture rows)"
```

---

## Task 2: `skills/clean-architecture/SKILL.md`

**Files:**
- Create: `skills/clean-architecture/SKILL.md`
- Modify: `tests/test_clean_architecture_skill_structure.py`

**Interfaces:**
- Consumes: `read_skill_file`, `parse_frontmatter`.
- Produces: the orchestrator every later CA file is cited by.

- [ ] **Step 1: Append the failing test**

```python
def test_skill_md_declares_tiers_tooling_and_carve():
    fields = parse_frontmatter(read_skill_file("SKILL.md"))
    assert fields.get("name") == "clean-architecture"
    assert fields.get("user-invocable") == "true"
    frontmatter_text = read_skill_file("SKILL.md").split("---")[1]
    assert re.search(r'version:\s*"0\.1\.0"', frontmatter_text)
    body = read_skill_file("SKILL.md")
    lowered = body.lower()
    for marker in ["headline", "secondary", "appendix", "opt-in"]:
        assert marker in lowered, f"SKILL.md missing tier marker: {marker}"
    assert "audit" in lowered and "no build" in lowered, "must state audit-first, no build mode"
    for tool in ["grimp", "import-linter"]:
        assert tool in lowered, f"SKILL.md missing tooling reference: {tool}"
    assert "degrade" in lowered or "fallback" in lowered, "must state graceful fallback"
    assert "lens-overlap.md" in body and "refactor-workflow.md" in body
    assert "ddd" in lowered, "must state the carve with ddd"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_clean_architecture_skill_structure.py::test_skill_md_declares_tiers_tooling_and_carve -q`
Expected: FAIL — file missing.

- [ ] **Step 3: Author `skills/clean-architecture/SKILL.md`**

````markdown
---
name: clean-architecture
description: >-
  Audit an existing codebase's component and dependency structure through Robert
  C. Martin's Clean Architecture lens — the altitude ABOVE the five SOLID
  principles and orthogonal to DDD's domain modelling. Headline checks (run by
  default) are robust and tool-assisted: the Dependency Rule / boundary audit
  (does core code import the framework, ORM, or DB? is the framework a
  replaceable detail?), import cycles (ADP), and stability direction (SDP).
  Secondary checks (opt-in) cover component cohesion (REP/CCP/CRP), Screaming
  Architecture, and the composition root; an opt-in appendix reports the
  abstractness / Main-Sequence metrics (approximate in Python). Audit-first, no
  build mode — building the layered shape is /ddd's job. Emits an import-linter
  contract as a leave-behind CI tripwire. Use for "/clean-architecture",
  dependency rule, boundaries, framework as a detail, import cycles, component
  cohesion/coupling, stable dependencies, screaming architecture, composition
  root.
user-invocable: true
metadata:
  version: "0.1.0"
  source: "Robert C. Martin, Clean Architecture (2017), read pragmatically"
---

# clean-architecture — component & dependency-graph audit

The widest zoom in the ladder: not classes (`solid`), not the domain model
(`ddd`), but the **component graph** — deployable/package units and how they
depend on each other. It **audits** existing code; it does **no build** (building
the layered shape is `ddd`'s job). It runs on the shared engine
([../../docs/refactor-workflow.md](../../docs/refactor-workflow.md)) with its own
rubric.

## The carve (why it doesn't fight the others)

- **vs `ddd`:** `ddd` asks *"is the domain modelled well?"*; this asks *"is the
  dependency structure sound, regardless of domain richness?"* Reconcile shared
  smells via [../../docs/lens-overlap.md](../../docs/lens-overlap.md).
- **vs `solid`:** those are the five class-level principles; this is the graph
  topology and their component-scale cousins. Never restate a `solid` DIP finding
  — cross-reference it.
- **vs `clean-code`:** line-level craft is `clean-code`'s; this never touches it.

## Invocation

`/clean-architecture [path] [--cohesion] [--metrics]`

- Default: the **headline** checks only.
- `--cohesion`: also run the **secondary** checks (packaging, Screaming
  Architecture, composition root). May also be offered interactively ("go
  deeper?").
- `--metrics`: also emit the **appendix** (abstractness / Main Sequence).
- Pre-authorizations count as the human review for what they cover.

## Tiers (see [references/principles.md](references/principles.md))

- **Headline (default) — robust, actionable:** Dependency Rule / boundary audit;
  import cycles (ADP); stability direction (SDP).
- **Secondary (opt-in):** component cohesion (REP/CCP/CRP); Screaming
  Architecture; Main Component / composition root.
- **Appendix (opt-in):** abstractness / Main-Sequence metrics — **approximate in
  Python**; structural-health context, never a finding to refactor toward.

## Tooling posture (tool-assisted, graceful fallback)

Detect a graph tool and use it when present; **degrade to agent-driven import
reading** when not (say which mode ran in the report). See
[references/python.md](references/python.md): `grimp` + `import-linter` (Python),
`dependency-cruiser`/`madge` (TS), via any available runner (`uvx`, `pipx run`,
project-local) — never a hard install.

## Leave-behind artifact

The Dependency-Rule findings compile to an **`import-linter` contract**
(`importlinter.ini`) written into the report dir — a one-time audit becomes a
repeatable CI guardrail. Offered for the user to commit; never committed silently.

## Flow (audit-first; apply opt-in)

Follows the shared workflow, Phases 0–3; apply (4–5) is opt-in and conservative.

1. **Phase 0 — Inventory & baseline.** Scope the tree; detect the test suite and a
   graph tool; create git-excluded `docs/reports/clean-architecture/`.
2. **Phase 1 — Analyzer** ([agents/analyzer.md](agents/analyzer.md), read-only) →
   `findings-draft.md`. Headline checks always; secondary/appendix only if opted
   in.
3. **Phase 2 — Reviewer** ([agents/reviewer.md](agents/reviewer.md)) re-verifies
   every finding, tiers Critical/Major/Minor, cross-references the hub, writes
   `docs/reports/clean-architecture/CLEAN-ARCHITECTURE-REPORT-<YYYY-MM-DD>.md` per
   [references/report-template.md](references/report-template.md), and drafts the
   `import-linter` contract.
4. **Phase 3 — Decision gate.** Present the summary. Most CA fixes are large
   (High-risk architectural moves) and stay advisory; **only mechanical, low-risk
   fixes** (break a cycle by moving a class, introduce a boundary port) are opt-in
   appliable via the shared implementer ([agents/implementer.md](agents/implementer.md)).

## Guardrails

- **Audit-first, no build mode.** Never scaffolds a greenfield layered app.
- **Judgment, not dogma.** Honour the when-NOT-to rules in `references/principles.md`:
  don't demand boundaries a single-deployable app hasn't earned; don't chase
  Main-Sequence distance without real multi-component granularity.
- **Defer, don't duplicate.** Cross-reference `solid`/`gof`/`ddd`/`clean-code` via
  the hub; file each shared smell once.
- **The report is the single source of truth**; apply logs live in it.

## File map

- [references/principles.md](references/principles.md) — the tiered rubric,
  violation signatures, when-NOT-to, tier assignment. Both analysis agents read it.
- [references/python.md](references/python.md) — tool detection, metric how-to,
  the import-linter contract, graceful degrade.
- [references/report-template.md](references/report-template.md) — report format.
- [agents/analyzer.md](agents/analyzer.md), [agents/reviewer.md](agents/reviewer.md),
  [agents/implementer.md](agents/implementer.md) — the three roles.
- [../../docs/refactor-workflow.md](../../docs/refactor-workflow.md) — shared Phase 0–5.
- [../../docs/lens-overlap.md](../../docs/lens-overlap.md) — cross-lens reconciliation.
````

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_clean_architecture_skill_structure.py::test_skill_md_declares_tiers_tooling_and_carve -q`
Expected: PASS.

- [ ] **Step 5: Confirm repo-wide skill guards pass**

Run: `.venv/bin/python -m pytest tests/test_skill_integrity.py tests/test_skill_shell_safety.py -q`
Expected: PASS (frontmatter valid; no `echo "$VAR" | python3`).

- [ ] **Step 6: Commit**

```bash
git add skills/clean-architecture/SKILL.md tests/test_clean_architecture_skill_structure.py
git commit -m "feat(clean-architecture): skill orchestrator (tiered audit, tooling posture, carve)"
```

---

## Task 3: `references/principles.md`

**Files:**
- Create: `skills/clean-architecture/references/principles.md`
- Modify: `tests/test_clean_architecture_skill_structure.py`

**Interfaces:**
- Consumes: `read_skill_file`.
- Produces: the shared rubric both analysis agents judge against.

- [ ] **Step 1: Append the failing test**

```python
def test_principles_cover_the_tiered_rubric():
    text = read_skill_file("references/principles.md")
    required = [
        "Dependency Rule", "ADP", "SDP", "SAP",
        "REP", "CCP", "CRP",
        "Screaming Architecture", "composition root",
        "Instability", "Main Sequence",
        "approximate in Python",   # the metrics caveat
        "When NOT",                # judgment block
    ]
    missing = [concept for concept in required if concept.lower() not in text.lower()]
    assert not missing, f"principles.md missing: {missing}"
    for tier in ["Headline", "Secondary", "Appendix", "Critical", "Major", "Minor"]:
        assert tier in text, f"principles.md missing tier label: {tier}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_clean_architecture_skill_structure.py::test_principles_cover_the_tiered_rubric -q`
Expected: FAIL — file missing.

- [ ] **Step 3: Author `skills/clean-architecture/references/principles.md`**

````markdown
# clean-architecture rubric — the component/dependency-graph altitude

Calibration, not a lesson. This altitude is the **component** — a deployable /
package unit — and how components depend on each other. It sits above `solid`
(classes) and orthogonal to `ddd` (domain). Every finding must argue its
reader / change-safety impact.

## The carve (non-overlap)

- `ddd` asks *"is the domain modelled well?"*; this asks *"is the dependency
  structure sound, regardless of domain richness?"*
- `solid` owns the five class-level principles; this is graph topology + their
  component-scale cousins. Cross-reference `../../docs/lens-overlap.md`; never
  restate a `solid` finding.

## Headline checks (default run) — robust, tool-assisted, actionable

1. **The Dependency Rule / boundaries.** Source dependencies point inward toward
   policy. **Violation:** a domain / use-case / core module imports a web
   framework, ORM, DB driver, or other outer-layer detail — the cardinal finding.
   The framework/DB must be a replaceable **detail** at the edge, reached through
   a port. Mechanically checkable as an `import-linter` forbidden/layers contract.
2. **ADP — no cycles.** The component/import graph must be acyclic. A cycle fuses
   packages into one un-releasable blob; any change forces revalidating the loop.
   Fix by inverting one edge (DIP) or extracting a shared component. Exactly
   detectable on the import graph.
3. **SDP — stability direction.** Depend toward stability. **Instability**
   `I = fan-out / (fan-in + fan-out)` (0 = stable, 1 = unstable). **Violation:** a
   much-depended-on (low-`I`) component importing a volatile (high-`I`) one. Robust
   — computed from import counts only, no "abstractness" needed.

## Secondary checks (opt-in `--cohesion`)

4. **Component cohesion — REP / CCP / CRP.**
   - **REP** — a component should be a coherent, releasable, versioned theme.
     *Smell:* grab-bag `utils`/`common`/`helpers` with unrelated contents.
   - **CCP** (SRP for components) — classes that change together belong together.
     *Evidence:* git co-change of files that live in different packages, or one
     requirement rippling across many.
   - **CRP** (ISP for components) — don't force importers to depend on a fat
     package when each uses only a disjoint slice.
5. **Screaming Architecture.** Top-level layout should reveal use cases
   (`billing/`, `orders/`) not the framework (`controllers/`, `models/`,
   `views/`). One repo-level observation.
6. **Main Component / composition root.** Wiring belongs at the outermost entry
   point. *Smell:* infrastructure constructed **inside** core code (the same smell
   as #1, seen as wiring), or no single composition root at all.

## Appendix (opt-in `--metrics`) — caveated

7. **SAP / the Main Sequence.** **Abstractness** `A = abstract classes / total`.
   Healthy line `A + I = 1`; **distance** `D = |A + I − 1|`; Zone of Pain
   (stable + concrete), Zone of Uselessness (abstract + unstable). **`A` is
   approximate in Python** — duck typing and `Protocol`s defeat "count the
   abstract classes." Present as structural-health context, **never a finding to
   refactor toward**.

## When NOT to flag (judgment, not ceremony)

- **Do NOT** demand boundaries a single-deployable app hasn't earned — partial
  boundaries are legitimate YAGNI.
- **Do NOT** chase Main-Sequence distance on a codebase without real
  multi-component granularity (one deployable with informal packages → noise).
- **Do NOT** flag a cycle *within* one intended release-unit's internal modules —
  the concern is **cross-component** cycles.
- **Do NOT** restate a `solid` DIP finding — cross-reference it via the hub.

## Tier assignment (severity)

- **Critical** — a Dependency-Rule violation welding the core to a framework/DB so
  it can't be tested or swapped; a cycle across core components.
- **Major** — an SDP violation on a central component; infrastructure constructed
  in core; a fat grab-bag component many things depend on.
- **Minor** — Screaming-Architecture naming; small cohesion nits; appendix metrics.
````

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_clean_architecture_skill_structure.py::test_principles_cover_the_tiered_rubric -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/clean-architecture/references/principles.md tests/test_clean_architecture_skill_structure.py
git commit -m "feat(clean-architecture): tiered rubric (dependency rule, ADP/SDP, cohesion, metrics)"
```

---

## Task 4: `references/python.md`

**Files:**
- Create: `skills/clean-architecture/references/python.md`
- Modify: `tests/test_clean_architecture_skill_structure.py`

**Interfaces:**
- Consumes: `read_skill_file`.
- Produces: tool detection + metric how-to + the `importlinter` artifact + degrade path.

- [ ] **Step 1: Append the failing test**

```python
def test_python_reference_covers_tooling_and_degrade():
    text = read_skill_file("references/python.md")
    lowered = text.lower()
    for tool in ["grimp", "import-linter", "importlinter.ini", "dependency-cruiser"]:
        assert tool in lowered, f"python.md missing tool: {tool}"
    assert "fan-in" in lowered and "fan-out" in lowered, "must show how to compute Instability"
    assert "degrade" in lowered or "fallback" in lowered, "must give the no-tool degrade path"
    assert "runtime_checkable" not in text  # sanity: this is CA, not the ddd port ref
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_clean_architecture_skill_structure.py::test_python_reference_covers_tooling_and_degrade -q`
Expected: FAIL — file missing.

- [ ] **Step 3: Author `skills/clean-architecture/references/python.md`**

````markdown
# clean-architecture in Python — tooling & metrics

The headline checks want the real import graph. Use a tool when one is reachable;
**degrade gracefully** when not. Other languages: `dependency-cruiser` / `madge`
(JS/TS) do the equivalent; else fall back to reading imports.

## Detect a graph tool (no hard install)

Try, in order, whatever the environment offers — a project-local install
(`python -c "import grimp"`), then a runner (`uvx import-linter`, `pipx run
import-linter`). Record which path succeeded. If **none** is reachable, switch to
the **degrade path** below and state "agent-driven (no graph tool)" in the report.

## `grimp` — the import graph, cycles, and Instability

```python
import grimp

graph = grimp.build_graph("your_top_package")          # the package under audit
components = graph.find_children("your_top_package")     # the sub-packages = components

for component in sorted(components):
    fan_out = len(graph.find_modules_directly_imported_by(component))  # efferent
    fan_in = len(graph.find_modules_that_directly_import(component))    # afferent
    denominator = fan_in + fan_out
    instability = fan_out / denominator if denominator else 0.0         # SDP metric
    print(component, round(instability, 2))
```
Cycles (ADP): `grimp` exposes them directly —
`graph.find_illegal_dependencies_for_layers(...)` for layered contracts, and cycle
detection over `find_children`. Report each cycle as the chain of components.

## `import-linter` — the Dependency Rule as contracts

Express the Dependency Rule as **contracts** and run them (and leave them behind).
Example `importlinter.ini` the reviewer drafts from the findings:

```ini
[importlinter]
root_package = your_top_package

[importlinter:contract:layers]
name = Dependency Rule: details point inward
type = layers
layers =
    your_top_package.web
    your_top_package.adapters
    your_top_package.application
    your_top_package.domain

[importlinter:contract:framework-out-of-core]
name = Framework is a detail
type = forbidden
source_modules = your_top_package.domain
                 your_top_package.application
forbidden_modules = django
                    sqlalchemy
                    flask
```
Run: `lint-imports --config importlinter.ini` (via the reachable runner). Write the
drafted file to `docs/reports/clean-architecture/importlinter.ini`; **offer** it as
a committed CI tripwire — never commit it silently.

## Abstractness (appendix) — and its Python caveat

`A = abstract classes / total classes` per component. In Python this is
**approximate**: `abc.ABC` subclasses and classes with `@abstractmethod` count,
but `typing.Protocol`s and duck-typed seams do not, so `A` (and therefore
`D = |A + I − 1|`) undercount abstraction. Emit the Main-Sequence table only under
`--metrics`, labelled approximate.

## Degrade path (no graph tool)

Read imports directly: build a rough module→imports map by scanning `import` /
`from ... import` statements, identify the core/detail split from folder names and
framework imports, and reason about cycles and stability qualitatively. State the
limitation in the report; the Dependency-Rule and Screaming-Architecture findings
survive without a tool — only exact cycle enumeration and `I`/`A` numbers are
weaker.
````

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_clean_architecture_skill_structure.py::test_python_reference_covers_tooling_and_degrade -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/clean-architecture/references/python.md tests/test_clean_architecture_skill_structure.py
git commit -m "feat(clean-architecture): Python tooling reference (grimp/import-linter, contract, degrade)"
```

---

## Task 5: `references/report-template.md`

**Files:**
- Create: `skills/clean-architecture/references/report-template.md`
- Modify: `tests/test_clean_architecture_skill_structure.py`

**Interfaces:**
- Consumes: `read_skill_file`.
- Produces: the report shape (IDs `C*/M*/N*`) + the contract + appendix sections.

- [ ] **Step 1: Append the failing test**

```python
def test_report_template_has_structure_contract_and_appendix():
    text = read_skill_file("references/report-template.md")
    for marker in ["[C1]", "[M1]", "[N1]", "Tier", "Status", "pending",
                   "import-linter contract", "Analysis mode", "Structural health"]:
        assert marker in text, f"report-template.md missing: {marker}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_clean_architecture_skill_structure.py::test_report_template_has_structure_contract_and_appendix -q`
Expected: FAIL — file missing.

- [ ] **Step 3: Author `skills/clean-architecture/references/report-template.md`**

````markdown
# clean-architecture report template

The reviewer writes
`docs/reports/clean-architecture/CLEAN-ARCHITECTURE-REPORT-<YYYY-MM-DD>.md` in
exactly this shape. IDs `C1,C2,…` / `M1,…` / `N1,…`, permanent once assigned.
Angle brackets are runtime fill-slots.

```markdown
# Clean-architecture Audit — <project> — <YYYY-MM-DD>

## Summary
- Scope: <path>, <N> components, <languages>
- **Analysis mode:** <graph-tool: grimp+import-linter | agent-driven (no graph tool)>
- Tiers run: Headline<, Secondary, Appendix as opted in>
- Findings: <n> Critical, <n> Major, <n> Minor
- Top wins: <the 2–3 that matter most, one line each>

## Findings

### Critical
#### [C1] <short imperative title, e.g. "Lift the ORM out of the use-case layer">
- **Check:** <Dependency Rule | ADP cycle | SDP | cohesion | screaming | composition root>
- **Location:** `package / path:line` <all sites; for a cycle, the component chain>
- **Evidence:** <the offending imports / the metric. No evidence, no finding.>
- **Impact:** <why it hurts change-safety/testability — justifies the tier>
- **Fix:** <concrete: introduce a port, invert the edge, extract a component,
  move construction to the composition root>
- **Cross-ref:** <lens-overlap rec, e.g. "solid DIP" / "ddd missing port", or none>
- **Tier:** Critical
- **Status:** pending

### Major
#### [M1] ...

### Minor
#### [N1] ...

## import-linter contract (leave-behind)
<the drafted importlinter.ini encoding the Dependency-Rule findings — offered as a
CI tripwire; written to docs/reports/clean-architecture/importlinter.ini>

## Structural health (appendix — only if --metrics)
<per-component I / A / D table, labelled "abstractness approximate in Python";
call out any Zone-of-Pain / Zone-of-Uselessness components — context, not findings>

## Reviewer notes
- Draft findings pruned as false positives: <finding → reason>, or "none"
- Cross-references filed to other lenses: <ids>, or "none"
- Areas not examined: <coverage gaps>
```
````

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_clean_architecture_skill_structure.py::test_report_template_has_structure_contract_and_appendix -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/clean-architecture/references/report-template.md tests/test_clean_architecture_skill_structure.py
git commit -m "feat(clean-architecture): report template (tiers, contract, health appendix)"
```

---

## Task 6: `agents/` — analyzer, reviewer, implementer

**Files:**
- Create: `skills/clean-architecture/agents/analyzer.md`
- Create: `skills/clean-architecture/agents/reviewer.md`
- Create: `skills/clean-architecture/agents/implementer.md`
- Modify: `tests/test_clean_architecture_skill_structure.py`

**Interfaces:**
- Consumes: `read_skill_file`.
- Produces: the three roles. Analyzer writes `findings-draft.md`; reviewer writes the report + contract; implementer applies only opt-in mechanical fixes via the shared TDD job.

- [ ] **Step 1: Append the failing test**

```python
def test_agents_state_their_contracts():
    analyzer = read_skill_file("agents/analyzer.md")
    reviewer = read_skill_file("agents/reviewer.md")
    implementer = read_skill_file("agents/implementer.md")
    assert "read-only" in analyzer.lower()
    assert "findings-draft.md" in analyzer
    assert "principles.md" in analyzer and "python.md" in analyzer
    assert "report-template.md" in reviewer
    assert "lens-overlap.md" in reviewer                     # cross-reference the hub
    assert "importlinter" in reviewer.lower()                # drafts the contract
    assert "mechanical" in implementer.lower() and "refactor-jobs.md" in implementer
    assert "advisory" in implementer.lower() or "opt-in" in implementer.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_clean_architecture_skill_structure.py::test_agents_state_their_contracts -q`
Expected: FAIL — files missing.

- [ ] **Step 3: Author `skills/clean-architecture/agents/analyzer.md`**

```markdown
# Role: clean-architecture analyzer (read-only)

You draft candidate component/dependency findings. You edit no code. An independent
reviewer re-verifies every finding, so carry quotable evidence (the offending
import, the cycle chain, the metric) and flag borderline items honestly.

## Inputs (from the orchestrator)

- Target path, scope notes, and which tiers are enabled (headline always;
  secondary/appendix only if opted in).
- `../references/principles.md` — the rubric. **Read it first.**
- `../references/python.md` — how to detect a graph tool and compute the graph;
  follow the degrade path if no tool is reachable, and record which mode ran.
- Output path: `docs/reports/clean-architecture/findings-draft.md`.

## Process

1. **Build (or approximate) the graph.** Detect `grimp`/`import-linter` per
   `python.md`; else read imports directly. Identify components (top-level
   packages) and the core/detail split (folder names + framework imports).
2. **Headline checks (always):** Dependency-Rule violations (core imports a
   framework/ORM/DB), cycles (ADP), stability-direction (SDP) — with evidence.
3. **Secondary (only if enabled):** cohesion (REP/CCP/CRP, using git co-change for
   CCP), Screaming Architecture (top-level names), composition root (infra built
   in core).
4. **Appendix (only if enabled):** the I/A/D table — mark abstractness approximate.
5. **Check the when-NOT-to list** before filing (don't demand unearned boundaries;
   don't chase metrics without multi-component granularity).

## Output — `findings-draft.md`

One entry per finding: `## [A<n>] title` with **Check**, **Location** (component /
`file:line`; cycle chain), **Evidence**, **Impact**, **Fix**, **Suggested tier**,
**Confidence**, and a possible **Cross-ref** to another lens. End with a
**Coverage** section (what you examined, what you skipped, and the analysis mode).

## Limits

- Prefer the few findings a human will act on. Read-only; change nothing.
```

- [ ] **Step 4: Author `skills/clean-architecture/agents/reviewer.md`**

```markdown
# Role: clean-architecture reviewer (independent verifier, report author)

You are the critic. The analyzer's draft is *candidates*; you produce a report a
human can act on. Every finding you keep, you verified against the real graph /
code. You **edit no code**. You write the report and draft the import-linter
contract.

## Inputs (from the orchestrator)

- `docs/reports/clean-architecture/findings-draft.md` — the draft.
- `../references/principles.md` (read first), `../references/python.md`.
- `../references/report-template.md` — the exact output shape.
- Output: `docs/reports/clean-architecture/CLEAN-ARCHITECTURE-REPORT-<YYYY-MM-DD>.md`
  and the drafted `docs/reports/clean-architecture/importlinter.ini`.

## Process

1. **Verify every draft finding** against the graph/code — re-run the tool where
   one is available; don't trust quoted line numbers. **Keep / Adjust / Prune**
   (record prune reasons; never prune silently). Apply the when-NOT-to rules.
2. **Cross-reference the hub** — check `../../../docs/lens-overlap.md`: a
   dependency-direction smell is one change shared with `solid` DIP / `ddd` missing
   port; file it once and cite the other lens's framing rather than duplicating.
3. **Tier** Critical/Major/Minor (when in doubt, down). Order by impact.
4. **Write the report** using `report-template.md` exactly, including the
   **Analysis mode** line and (only if `--metrics`) the Structural-health appendix.
5. **Draft the import-linter contract** from the Dependency-Rule findings; write it
   to the report dir. It is **offered** as a CI tripwire, never committed silently.

## Quality bar

Ten findings a human acts on beat thirty they skim. Keep the DDD/SOLID framings as
cross-references, not restated recs.
```

- [ ] **Step 5: Author `skills/clean-architecture/agents/implementer.md`**

```markdown
# Role: clean-architecture implementer (opt-in, mechanical fixes only)

Most clean-architecture fixes are large architectural moves and stay **advisory**.
Only **mechanical, low-risk** recs are appliable, and only when the user opts in at
the decision gate: e.g. break a cycle by moving a class, introduce a boundary port,
relocate infra construction to the composition root.

You do **not** edit code directly — you dispatch each approved mechanical rec to
TDD's programmatic refactor job, exactly as the shared implementer role does. Read
[../../../docs/refactor-agents/implementer.md](../../../docs/refactor-agents/implementer.md)
and [../../../skills/tdd/references/refactor-jobs.md](../../../skills/tdd/references/refactor-jobs.md)
and follow that contract: one rec (or dependent chain) at a time, suite green after
each, Status + apply-log updated in the report.

**Never** apply a rec marked High risk (cross-module restructures, layer
re-slicing) without explicit per-rec confirmation. When in doubt, leave it advisory
in the report.
```

- [ ] **Step 6: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_clean_architecture_skill_structure.py::test_agents_state_their_contracts -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add skills/clean-architecture/agents/ tests/test_clean_architecture_skill_structure.py
git commit -m "feat(clean-architecture): analyzer, reviewer, and opt-in implementer roles"
```

---

## Task 7: Trigger + behaviour evals

**Files:**
- Create: `evals/clean-architecture-evals.json`
- Modify: `tests/test_clean_architecture_skill_structure.py`

**Interfaces:**
- Consumes: `REPO_ROOT`, `json`.
- Produces: eval cases mirroring `evals/ddd-evals.json`'s schema.

- [ ] **Step 1: Append the failing test**

```python
def test_ca_evals_cover_tiers_tooling_and_carve():
    evals_path = REPO_ROOT / "evals" / "clean-architecture-evals.json"
    assert evals_path.is_file(), "evals/clean-architecture-evals.json missing"
    document = json.loads(evals_path.read_text())
    assert document["skill_name"] == "clean-architecture"
    cases = document["evals"]
    assert len(cases) >= 4
    for case in cases:
        for field in ["id", "skill", "prompt", "expected_output", "assertions"]:
            assert field in case, f"eval case {case.get('id')} missing {field}"
        assert isinstance(case["assertions"], list) and case["assertions"]
    blob = json.dumps(document).lower()
    assert "dependency rule" in blob
    assert "opt-in" in blob or "--cohesion" in blob or "--metrics" in blob
    assert "import-linter" in blob
    assert "ddd" in blob                      # the carve
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_clean_architecture_skill_structure.py::test_ca_evals_cover_tiers_tooling_and_carve -q`
Expected: FAIL — file missing.

- [ ] **Step 3: Author `evals/clean-architecture-evals.json`**

```json
{
  "skill_name": "clean-architecture",
  "evals": [
    {
      "id": 1,
      "skill": "clean-architecture",
      "prompt": "Audit our service's architecture — I think the business logic is tangled up with Django and the database.",
      "expected_output": "Runs the headline tier: detects a graph tool (or degrades), audits the Dependency Rule (core importing Django/ORM), import cycles, and stability direction; writes a tiered report and drafts an import-linter contract. Report-first.",
      "assertions": [
        "Reads references/principles.md and detects grimp/import-linter (or states it is degrading to agent-driven reading)",
        "Runs only the headline checks by default (dependency direction, cycles, stability)",
        "Flags core/use-case modules importing Django, the ORM, or the DB as Dependency-Rule violations with file:line evidence",
        "Creates git-excluded docs/reports/clean-architecture/ and writes CLEAN-ARCHITECTURE-REPORT-<date>.md via the template",
        "Drafts an import-linter contract (importlinter.ini) and offers it as a CI tripwire without committing it silently",
        "Does not scaffold or build a layered structure (audit-first, no build mode)"
      ]
    },
    {
      "id": 2,
      "skill": "clean-architecture",
      "prompt": "Also check whether our packages are grouped sensibly and whether the layout shows what the app does.",
      "expected_output": "Recognises these as the secondary tier and runs them on opt-in: component cohesion (REP/CCP/CRP, using git co-change for CCP), Screaming Architecture, and the composition root.",
      "assertions": [
        "Treats cohesion and Screaming Architecture as the opt-in secondary tier (via --cohesion or an explicit go-deeper)",
        "Evaluates REP/CCP/CRP, using git co-change as evidence for CCP",
        "Assesses whether the top-level layout reveals use cases vs the framework (Screaming Architecture)",
        "Checks whether infrastructure is constructed in core vs wired at a single composition root"
      ]
    },
    {
      "id": 3,
      "skill": "clean-architecture",
      "prompt": "Can you give me the abstractness / Main-Sequence numbers for each package?",
      "expected_output": "Runs the appendix on opt-in and reports I/A/D, but explicitly caveats that abstractness is approximate in Python and does not tell the user to refactor toward the metric.",
      "assertions": [
        "Treats the Main-Sequence metrics as the opt-in appendix (--metrics)",
        "Reports Instability I from import fan-in/fan-out and the A/D metrics per component",
        "States that abstractness A is approximate in Python (Protocols/duck typing) and presents it as structural-health context, not a finding",
        "Does not recommend refactoring purely to move a component toward the Main Sequence"
      ]
    },
    {
      "id": 4,
      "skill": "clean-architecture",
      "prompt": "How is this different from just running /ddd on the same code?",
      "expected_output": "Explains the carve: /ddd asks whether the domain is modelled well; /clean-architecture asks whether the dependency structure is sound regardless of domain richness, and shared smells are reconciled once via the lens-overlap hub rather than duplicated.",
      "assertions": [
        "States that /ddd evaluates domain modelling (aggregates, ubiquitous language, ports) while /clean-architecture evaluates the component/dependency structure",
        "Notes a codebase can pass one and fail the other",
        "Explains that a shared smell (e.g. a missing port / dependency-direction violation) is filed once and cross-referenced via docs/lens-overlap.md, not duplicated",
        "Does not re-run domain modelling itself"
      ]
    }
  ]
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_clean_architecture_skill_structure.py::test_ca_evals_cover_tiers_tooling_and_carve -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add evals/clean-architecture-evals.json tests/test_clean_architecture_skill_structure.py
git commit -m "test(clean-architecture): trigger + behaviour evals for tiers, tooling, and the carve"
```

---

## Task 8: Register the skill + bump all three version mirrors

**Files:**
- Modify: `.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `tests/test_clean_architecture_skill_structure.py`

**Interfaces:**
- Consumes: `REPO_ROOT`, `json`.
- Produces: the plugin advertises `clean-architecture`; all three version mirrors = `0.13.0`.

Read all three manifest files first; copy the surrounding structure verbatim and
edit in place.

- [ ] **Step 1: Append the failing test**

```python
def test_manifests_advertise_ca_and_versions_are_bumped():
    plugin_manifest = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())
    marketplace_manifest = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text())
    assert "clean-architecture" in plugin_manifest["description"].lower()
    assert "clean-architecture" in plugin_manifest["keywords"]
    marketplace_blob = json.dumps(marketplace_manifest).lower()
    assert "clean-architecture" in marketplace_blob
    assert plugin_manifest["version"] == "0.13.0"
    assert marketplace_manifest["plugins"][0]["version"] == "0.13.0"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_clean_architecture_skill_structure.py::test_manifests_advertise_ca_and_versions_are_bumped -q`
Expected: FAIL — not registered / still 0.12.0.

- [ ] **Step 3: Edit `.claude-plugin/plugin.json`**

Bump `"version"` `0.12.0` → `0.13.0`; append to `description` a clause such as
`", and a Clean Architecture component/dependency audit (/clean-architecture)"`;
add `"clean-architecture"`, `"dependency-rule"`, `"component-principles"` to
`keywords`. Keep valid JSON; change nothing else.

- [ ] **Step 4: Edit `.claude-plugin/marketplace.json` and `pyproject.toml`**

In `marketplace.json`: bump the nested `plugins[0].version` to `0.13.0` and append
the same clause to that plugin's `description`. In `pyproject.toml`: bump
`version` to `0.13.0` (the third mirror). All three must match.

- [ ] **Step 5: Edit `README.md`**

Add a one-line mention of `/clean-architecture` alongside the existing lens
descriptions (near the `/solid` and `/gof` lines and the `lens-overlap.md`
cross-reference already updated in Task 1).

- [ ] **Step 6: Run tests — registration + version mirrors + JSON validity**

Run: `.venv/bin/python -m pytest tests/test_clean_architecture_skill_structure.py::test_manifests_advertise_ca_and_versions_are_bumped tests/test_skill_integrity.py::test_version_mirrors_match -q`
Expected: PASS.

Run: `.venv/bin/python -c "import json,pathlib; [json.loads(pathlib.Path(p).read_text()) for p in ['.claude-plugin/plugin.json','.claude-plugin/marketplace.json']]; print('both valid')"`
Expected: `both valid`.

- [ ] **Step 7: Commit**

```bash
git add .claude-plugin/plugin.json .claude-plugin/marketplace.json pyproject.toml README.md tests/test_clean_architecture_skill_structure.py
git commit -m "feat(clean-architecture): register skill in manifests, bump version to 0.13.0"
```

---

## Task 9: Housekeeping + full-suite green + finish

**Files:**
- Delete: `solid-reports/` (repo-root stale artifact, if present)

- [ ] **Step 1: Remove the stale root report dir**

Plan 1 replaced the `solid-reports/` gitignore entry with `docs/reports/`, so a
leftover root `solid-reports/` (a regenerable, never-committed artifact from a past
self-run) would now show as untracked. Remove it if present:
```bash
rm -rf solid-reports/
git status --porcelain
```
Expected: no untracked `solid-reports/`; tree clean apart from staged work.

- [ ] **Step 2: Run the whole repo test suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — all pre-existing tests plus `test_clean_architecture_skill_structure.py`. If anything unrelated fails, confirm it also failed before this branch; don't "fix" unrelated code.

- [ ] **Step 3: Confirm the skill directory is complete**

Run: `find skills/clean-architecture -type f | sort`
Expected exactly:
```
skills/clean-architecture/SKILL.md
skills/clean-architecture/agents/analyzer.md
skills/clean-architecture/agents/implementer.md
skills/clean-architecture/agents/reviewer.md
skills/clean-architecture/references/principles.md
skills/clean-architecture/references/python.md
skills/clean-architecture/references/report-template.md
```

- [ ] **Step 4: Offer to ship (never auto-run)**

Both plans are now applied on `clean-architecture/skills`. Per
`docs/git-convention.md`, propose a Conventional Commit summary of the whole branch
(clean-code substrate + reports convention + clean-architecture lens + overlap hub)
and ask whether to push + open a PR via `mente-apex:ship`. "Leave it on the branch"
and "discard it" are first-class answers. Do not push without an explicit yes.

- [ ] **Step 5: Offer to capture to the memory brain (never silently)**

Offer to record the durable decisions via `/memory`: the plugin now has a
`clean-architecture` audit lens (tiered: headline default, cohesion/metrics opt-in;
audit-first, no build; carve with `ddd`), and the overlap map is now the shared
`docs/lens-overlap.md` hub.

---

## Self-Review (completed during authoring)

**Spec coverage:**
- clean-architecture as an audit lens on the shared engine, audit-first no build → Task 2 + eval 1. ✓
- Headline tier default (dependency direction, cycles ADP, stability SDP) → Tasks 2, 3 + eval 1. ✓
- Secondary opt-in (REP/CCP/CRP, Screaming, composition root) → Task 3 + eval 2. ✓
- Appendix opt-in (SAP/A/D, Python caveat) → Tasks 3, 4 + eval 3. ✓
- Tooling-first with graceful fallback (grimp/import-linter/dependency-cruiser) → Tasks 2, 4 + eval 1. ✓
- import-linter leave-behind contract → Tasks 4, 5, 6 + eval 1. ✓
- The carve vs ddd; defer via the hub → Tasks 2, 3, 6 + eval 4. ✓
- Overlap hub replacing the pairwise map, all 11 refs repointed incl. the test file → Task 1. ✓
- Reports under docs/reports/clean-architecture/ (from Plan 1) → Tasks 2, 5. ✓
- Manifests + three version mirrors bumped to 0.13.0 → Task 8. ✓
- Housekeeping of the stale root solid-reports/ → Task 9. ✓

**Placeholder scan:** `<...>` in the report template are runtime fill-slots (as in `ddd`). The grimp/import-linter snippets in `python.md` are complete, runnable examples with `your_top_package` as the documented substitution token. No TBD/TODO.

**Type/name consistency:** `read_skill_file` / `parse_frontmatter` / `REPO_ROOT` / `CA_SKILL_DIR` / `LENS_OVERLAP` defined once in Task 1, reused verbatim in Tasks 2–8. Marker strings asserted by tests (`Dependency Rule`, `ADP`, `SDP`, `SAP`, `REP/CCP/CRP`, `Screaming Architecture`, `composition root`, `import-linter`, `importlinter.ini`, `lens-overlap.md`, `0.13.0`, tier labels) appear verbatim in the authored files. All run steps use `.venv/bin/python -m pytest`.
```
