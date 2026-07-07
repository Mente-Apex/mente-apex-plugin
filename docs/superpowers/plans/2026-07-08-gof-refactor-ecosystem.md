# GoF pattern lens + shared TDD refactor engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `gof` design-pattern skill and make it + the existing `solid` skill apply their approved changes through a new programmatic TDD *refactor job*, with the two lenses cross-referencing via a shared overlap map.

**Architecture:** Two analysis lenses (`solid` = principles, `gof` = patterns) depend on two injected abstractions — the *engine* (TDD's programmatic refactor-job contract) and the *lens* (a `{rubric, report-template}` pair). Shared orchestration lives once in `docs/refactor-workflow.md` and `docs/refactor-agents/*`; both skills are thin wirings that pass their own lens in. Structural pytest guards protect the shared-docs pointers and the version mirrors.

**Tech Stack:** Markdown skill/instruction files; Python 3.14 + pytest for structural guards (stdlib only — `json`, `re`, `tomllib`, `pathlib`); JSON manifests + eval files.

## Global Constraints

- **Branch:** all work on `feat/gof-refactor-ecosystem` (already created off current `main`). Never commit to `main`.
- **Python:** `requires-python >= 3.14`; **stdlib only** — no pip installs in any test or script.
- **Skills are Markdown**; the only executable code added is pytest guards under `tests/`.
- **Version mirrors** must always match across `.claude-plugin/plugin.json`, `pyproject.toml`, and `.claude-plugin/marketplace.json` (test enforces this).
- **Report field names are load-bearing:** recommendation IDs (`C*/M*/N*`), `Risk:`, and `Status:` are parsed by the apply phase — keep verbatim across `solid` and `gof` report templates.
- **Behavior-preserving apply:** the refactor engine reverts any job whose change turns the suite red; it never edits a test's assertion to pass a refactor.
- **Naming:** descriptive names only — no single-letter or abbreviated variables, including in comprehensions.
- **Commits:** Conventional Commits; end each commit body with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- **Test command:** `cd <repo> && python3 -m pytest -q` (config: `pyproject.toml` `testpaths=["tests"]`).
- **Reference source (read-only):** the standalone skill at `~/.claude/skills/gof/` — port `references/patterns.md` and the HTML spec from it; do not modify it until Task 13.

---

## File Structure

**Create:**
- `tests/test_skill_integrity.py` — all structural guards (grows across Tasks 1, 5, 6, 8, 9, 11)
- `skills/tdd/references/refactor-jobs.md` — the refactor-job contract + worked example
- `docs/refactor-workflow.md` — shared Phase 0–5 orchestration
- `docs/refactor-agents/analyzer.md`, `reviewer.md`, `implementer.md` — shared lens-agnostic roles
- `docs/solid-gof-overlap.md` — 23-pattern ↔ principle map
- `skills/gof/SKILL.md`
- `skills/gof/agents/analyzer.md`, `reviewer.md`, `implementer.md` — pointer stubs
- `skills/gof/references/patterns.md`, `report-template.md`, `html-report.md`, `python.md`
- `evals/gof-evals.json`

**Modify:**
- `skills/tdd/SKILL.md` (add refactor job; version 1.2.0 → 1.3.0)
- `docs/git-convention.md` (applicability line)
- `skills/solid/SKILL.md` (route apply through TDD; point to shared docs; version 0.3.0 → 0.4.0)
- `skills/solid/agents/analyzer.md`, `reviewer.md`, `implementer.md` (→ pointer stubs)
- `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `pyproject.toml` (version 0.10.0 + descriptions/keywords)
- `README.md` (gof row + ecosystem note)

**Out of repo (Task 13, gated):** remove `~/.claude/skills/gof/`; re-bundle config-sync.

---

## Stage A — Structural test net

### Task 1: Skill/doc integrity guards

**Files:**
- Create: `tests/test_skill_integrity.py`

**Interfaces:**
- Produces: module-level constant `GOF_PATTERNS` (list[str], the 23 names) and helpers `_parse_frontmatter(text)`, `_relative_link_targets(text)`, reused by later tasks in this same file.

- [ ] **Step 1: Write the guard module (green-on-write net over existing files)**

```python
# tests/test_skill_integrity.py
"""Static structural guards for the plugin's skills, shared docs, and manifests.

No engine import: these are pure file checks. They protect the shared-docs
architecture (a skill pointing at docs/refactor-workflow.md must not dangle)
and keep the three version mirrors in lockstep.
"""
import json
import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
DOCS_DIR = REPO_ROOT / "docs"
PLUGIN_JSON = REPO_ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE_JSON = REPO_ROOT / ".claude-plugin" / "marketplace.json"
PYPROJECT = REPO_ROOT / "pyproject.toml"

REQUIRED_FRONTMATTER_KEYS = ("name", "description")

GOF_PATTERNS = [
    "Abstract Factory", "Builder", "Factory Method", "Prototype", "Singleton",
    "Adapter", "Bridge", "Composite", "Decorator", "Facade", "Flyweight", "Proxy",
    "Chain of Responsibility", "Command", "Interpreter", "Iterator", "Mediator",
    "Memento", "Observer", "State", "Strategy", "Template Method", "Visitor",
]

# The cross-references this guard protects: the refactor ecosystem's skills and
# shared docs. Files created by later tasks simply don't match yet. Narrative
# docs under docs/superpowers/ (plans, specs) are deliberately NOT scanned —
# they carry intentional forward-references and fenced example links; and
# unrelated skills may point at the user's deployment (e.g. the memory brain).
INTEGRITY_SCAN_GLOBS = (
    "skills/gof/**/*.md",
    "skills/solid/**/*.md",
    "skills/tdd/**/*.md",
    "docs/refactor-workflow.md",
    "docs/refactor-agents/*.md",
    "docs/solid-gof-overlap.md",
    "docs/git-convention.md",
)

MARKDOWN_LINK = re.compile(r"\]\(([^)]+)\)")


def _parse_frontmatter(markdown_text):
    """Return the raw YAML frontmatter between the first two '---' fences, or None."""
    if not markdown_text.startswith("---"):
        return None
    fence_end = markdown_text.find("\n---", 3)
    if fence_end == -1:
        return None
    return markdown_text[3:fence_end]


def _integrity_scan_files():
    """Existing Markdown files whose links this guard resolves (dedup, sorted)."""
    matched = set()
    for glob_pattern in INTEGRITY_SCAN_GLOBS:
        for markdown_file in REPO_ROOT.glob(glob_pattern):
            if markdown_file.is_file():
                matched.add(markdown_file)
    return sorted(matched)


def _strip_fenced_code_blocks(markdown_text):
    """Drop ``` fenced blocks so example links inside them aren't treated as live pointers."""
    kept_lines = []
    inside_fence = False
    for line in markdown_text.splitlines():
        if line.lstrip().startswith("```"):
            inside_fence = not inside_fence
            continue
        if not inside_fence:
            kept_lines.append(line)
    return "\n".join(kept_lines)


def _relative_link_targets(markdown_text):
    """Yield each relative markdown-link target (fenced blocks stripped, anchors removed, URLs skipped)."""
    for raw_target in MARKDOWN_LINK.findall(_strip_fenced_code_blocks(markdown_text)):
        target = raw_target.split("#", 1)[0].strip()
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        yield target


def test_every_skill_has_required_frontmatter():
    offenders = []
    for skill_file in sorted(SKILLS_DIR.rglob("SKILL.md")):
        frontmatter = _parse_frontmatter(skill_file.read_text())
        if frontmatter is None:
            offenders.append(f"{skill_file.relative_to(REPO_ROOT)}: no frontmatter")
            continue
        for required_key in REQUIRED_FRONTMATTER_KEYS:
            if not re.search(rf"^{required_key}:", frontmatter, re.MULTILINE):
                offenders.append(f"{skill_file.relative_to(REPO_ROOT)}: missing '{required_key}'")
    assert not offenders, "Frontmatter problems:\n" + "\n".join(offenders)


def test_relative_markdown_links_resolve():
    offenders = []
    for markdown_file in _integrity_scan_files():
        for target in _relative_link_targets(markdown_file.read_text()):
            resolved = (markdown_file.parent / target).resolve()
            if not resolved.exists():
                offenders.append(f"{markdown_file.relative_to(REPO_ROOT)} -> {target}")
    assert not offenders, "Dangling relative markdown links:\n" + "\n".join(offenders)


def test_version_mirrors_match():
    plugin_version = json.loads(PLUGIN_JSON.read_text())["version"]
    pyproject_version = tomllib.loads(PYPROJECT.read_text())["project"]["version"]
    marketplace_version = json.loads(MARKETPLACE_JSON.read_text())["plugins"][0]["version"]
    assert plugin_version == pyproject_version == marketplace_version, (
        f"version drift — plugin.json={plugin_version} "
        f"pyproject={pyproject_version} marketplace={marketplace_version}"
    )
```

- [ ] **Step 2: Run — verify green over existing state**

Run: `python3 -m pytest tests/test_skill_integrity.py -q`
Expected: 3 passed. (This net is green now; later tasks make specific assertions go red when they add a dangling pointer or bump one version mirror out of step.)

- [ ] **Step 3: Commit**

```bash
git add tests/test_skill_integrity.py
git commit -m "test(skills): structural guards — frontmatter, link resolution, version mirrors

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Stage B — TDD refactor engine (foundation both lenses call)

### Task 2: TDD gains a programmatic refactor job

**Files:**
- Create: `skills/tdd/references/refactor-jobs.md`
- Modify: `skills/tdd/SKILL.md` (Work modes + programmatic contract + reciprocal `/gof` line + `metadata.version`)

**Interfaces:**
- Produces: the **refactor-job calling contract** consumed by `docs/refactor-agents/implementer.md` (Task 4). Exact input keys: `targets`, `change`, `test_command`, `baseline_status`, `coverage` (`covered` | `none`), `new_behavior` (optional). Exact output keys: `job_id`, `outcome` (`applied` | `failed (reverted)`), `tests_written`, `files_touched`, `diffstat`, `suite_status`, `noticed_not_touched`.

- [ ] **Step 1: Create `skills/tdd/references/refactor-jobs.md`**

Write the file with these sections and this exact contract (prose may be expanded, keys/outcomes must match verbatim):

```markdown
# Programmatic refactor jobs

A **refactor job** is TDD's third programmatic entry (alongside feature and
legacy work): a *behavior-preserving structural change under a green safety
net*. It exists so other skills — `solid`, `gof` — apply their approved
recommendations through one engine instead of each re-implementing "apply,
run suite, revert on red." It is additive: feature and legacy contracts are
unchanged.

## Calling contract (stable — callers depend on it)

Input (from a lens's implementer-coordinator):
- `targets` — files/symbols the change touches
- `change` — the exact behavior-preserving restructuring (a rec's Proposed change)
- `test_command` + `baseline_status` — green, or the tolerated pre-existing failures
- `coverage` — `covered` if the suite exercises the targets, else `none`
- `new_behavior` — optional: any genuinely-new behavior the change introduces

Execution:
1. Safety net. `coverage == none` → run legacy mode: write characterization
   pins asserting what the code does today, to green. `covered` → use the
   existing suite. If current behavior looks wrong, flag it — never silently
   "fix" it; the oddity may be load-bearing.
2. Apply the smallest faithful version of `change`. Behavior-preserving; house
   style; descriptive names; no new dependencies.
3. New-behavior carve-out. Anything in `new_behavior` runs as a normal feature
   red-green cycle (a failing test that demands it, then minimum code).
4. Verify. Run the full `test_command`. Green (== baseline) → success. Red →
   one focused fix attempt; still red → revert the ENTIRE job (tree back to the
   pre-job state) and report failure. Never edit a test assertion to pass a
   refactor — a disagreeing test means the change is wrong.

Output (the caller acts on this without re-reading anything):
`job_id`, `outcome` (`applied` | `failed (reverted)`), `tests_written`
(pins + any new feature tests), `files_touched`, `diffstat`, `suite_status`
(vs baseline), `noticed_not_touched`.

## Worked example

A SOLID rec "extract PricingStrategy protocol; move the three `if kind ==`
branches into Percent/Fixed/Tiered strategy classes; inject the chosen
strategy" arrives as: targets=[pricing.py], change=<that text>,
coverage=covered, baseline_status=green, new_behavior=none.
→ existing suite is the net → apply the extraction → suite green → outcome
`applied`, tests_written=[] (behavior unchanged), files_touched=[pricing.py,
strategies.py].
```

- [ ] **Step 2: Edit `skills/tdd/SKILL.md` — add the refactor job to Work modes**

Under the "## Work modes" list (after the `Legacy` bullet), add a third bullet:

```markdown
- **Refactor** (programmatic) — a lens skill (`solid`, `gof`) asks you to apply a
  behavior-preserving structural change under a green safety net. Read
  `references/refactor-jobs.md` for the calling contract. In short: pin untested
  targets first (legacy mode), apply the smallest faithful change, keep the full
  suite green, revert the whole job on red. Any genuinely-new behavior the change
  introduces runs as a normal feature cycle.
```

- [ ] **Step 3: Edit `skills/tdd/SKILL.md` — reciprocal `/gof` suggestion**

In "#### 3. REFACTOR", find the line that suggests a `/solid` audit for recurring architecture smells and extend it so a *pattern-shaped* smell points to `/gof`:

Existing:
```
  touches, type switches spreading between files — don't derail the cycle to fix them.
  Note the pattern and suggest a `/solid` audit as separate work.
```
Replace the second sentence with:
```
  Note the pattern and suggest a `/solid` audit as separate work. When the smell is
  specifically pattern-shaped — a missing, duplicated, or forced design pattern (a
  hand-rolled dispatch that wants Strategy, copy-pasted algorithm skeletons that want
  Template Method) — suggest a `/gof` audit instead.
```

- [ ] **Step 4: Edit `skills/tdd/SKILL.md` — bump version**

Change frontmatter `metadata.version` from `"1.2.0"` to `"1.3.0"`.

- [ ] **Step 5: Run integrity guards**

Run: `python3 -m pytest tests/test_skill_integrity.py -q`
Expected: 3 passed (frontmatter still valid; no new links added yet; versions untouched).

- [ ] **Step 6: Commit**

```bash
git add skills/tdd/references/refactor-jobs.md skills/tdd/SKILL.md
git commit -m "feat(tdd): programmatic refactor-job contract as the shared apply engine

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Stage C — Shared orchestration & agents

### Task 3: Shared refactor workflow

**Files:**
- Create: `docs/refactor-workflow.md`

**Interfaces:**
- Consumes: nothing yet (self-contained doc).
- Produces: the Phase 0–5 workflow that `skills/gof/SKILL.md` (Task 8) and `skills/solid/SKILL.md` (Task 10) both link and follow, parameterized by "the lens" = `{rubric, report-template}`.

- [ ] **Step 1: Create `docs/refactor-workflow.md`**

Generalize the body of the current `skills/solid/SKILL.md` (read it as the source of truth for exact wording) to "the lens." Required sections and content:

- Intro: "Shared orchestration for the plugin's refactor lenses (`solid`, `gof`). Each lens supplies a **rubric** (`references/<rubric>.md`) and a **report template** (`references/report-template.md`); this file supplies the workflow. The engine is TDD's refactor job ([skills/tdd/references/refactor-jobs.md](../skills/tdd/references/refactor-jobs.md))."
- **The cast** table: Orchestrator (main agent), Analyzer (`docs/refactor-agents/analyzer.md`), Reviewer (`docs/refactor-agents/reviewer.md`), Implementer/TDD-coordinator (`docs/refactor-agents/implementer.md`). Note the "play the roles yourself sequentially if you cannot spawn subagents" fallback (copy SOLID's wording).
- **Phase 0 — Inventory & baseline:** scope (skip vendored/generated); detect + run the test suite once, record baseline; create `<lens>-reports/` in the target project and git-exclude it via `.git/info/exclude`.
- **Phase 1 — Analyzer:** dispatch with target path, scope notes, the lens's rubric path; output `<lens>-reports/findings-draft.md`.
- **Phase 2 — Reviewer:** verify every finding against real code; prune/adjust/tier + assign Risk; cross-file sweep; **cross-reference the other lens** via [docs/solid-gof-overlap.md](solid-gof-overlap.md); write the final report from the lens's `report-template.md` exactly.
- **Phase 3 — Decision gate (human):** summarize; `AskUserQuestion` for which recs (tier or ID); "none — just the doc" is first-class; no-suite handling chooses the `coverage` policy (stop-at-doc / characterization-first / light-verification) passed to the engine.
- **Phase 4 — Apply via TDD:** working branch first (link [docs/git-convention.md](git-convention.md)); split by Risk (High → individual human confirm); one rec or same-file chain at a time; **each rec dispatched as a TDD refactor job**; sequential is the contract; disjoint chains may run in parallel worktrees (re-run full suite on the merged tree).
- **Phase 5 — Review & loop:** verify the suite yourself; spot-check diffs for "regressions of the cure"; loop scoped to changed files, **hard cap 3 cycles**; summarize; **offer** commit + PR (hand to `/ship`), never auto-publish.
- **Guardrails:** behavior-preserving always; the report is the single source of truth; judgment not dogma; fan-in at the orchestrator; every agent terminates by writing its artifact even when empty.

Use markdown links (`[text](path)`) for every cross-file reference so the integrity guard covers them.

- [ ] **Step 2: Run integrity guards**

Run: `python3 -m pytest tests/test_skill_integrity.py -q`
Expected: 3 passed. In particular `test_relative_markdown_links_resolve` covers the new links — note `solid-gof-overlap.md` does not exist yet, so **do not link it until Task 5**, OR if you link it now expect that one test RED until Task 5. Recommended: leave the overlap-map link as plain text in this step and convert it to a markdown link in Task 5. If green: proceed.

- [ ] **Step 3: Commit**

```bash
git add docs/refactor-workflow.md
git commit -m "docs(refactor): shared analyzer→reviewer→gate→apply-via-tdd workflow

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 4: Shared agent roles (lens-agnostic)

**Files:**
- Create: `docs/refactor-agents/analyzer.md`, `docs/refactor-agents/reviewer.md`, `docs/refactor-agents/implementer.md`

**Interfaces:**
- Consumes: the refactor-job contract from Task 2 (`implementer.md` calls it).
- Produces: three role docs referenced by both skills' `agents/*.md` stubs (Tasks 8, 10).

- [ ] **Step 1: Create `docs/refactor-agents/analyzer.md`**

Adapt `skills/solid/agents/analyzer.md` (read it) to be lens-agnostic: replace "SOLID findings" with "findings for this lens"; inputs name a generic `rubric path` and `report output path`; keep the "every finding must carry quotable evidence", "map before reading", "hunt with the signatures", "read the suspects", "one cross-file pass", the draft entry format, Coverage section, and the ~25-finding cap.

- [ ] **Step 2: Create `docs/refactor-agents/reviewer.md`**

Adapt `skills/solid/agents/reviewer.md` to be lens-agnostic. Keep: verify every draft finding against current code; keep/adjust/prune with recorded reasons; the cross-file sweep that terminates by writing; tier + Risk with the lens rubric; write the report from the lens's template. **Add** one step: "Cross-reference the other lens via [docs/solid-gof-overlap.md](../solid-gof-overlap.md): for each rec, note the overlapping principle/pattern; if a rec is better expressed in the other lens, mark it and recommend that skill; if the other lens has already produced a report in its `*-reports/`, reference its existing rec IDs instead of emitting a duplicate."

- [ ] **Step 3: Create `docs/refactor-agents/implementer.md` (the TDD-coordinator)**

This is the load-bearing change. Adapt `skills/solid/agents/implementer.md`, but replace the "apply the change yourself" mechanic with **dispatching a TDD refactor job**:

```markdown
# Role: refactor implementer (TDD-coordinator)

You apply one approved recommendation — or one dependent chain — by dispatching
it to TDD's programmatic refactor job. You do NOT edit code directly; TDD is the
engine. Your job is to translate the rec into a refactor-job call and record the
outcome.

## Inputs (from the orchestrator)
- Report path + your rec ID (or ordered chain IDs)
- Test command + baseline status
- `coverage` policy from the human gate (covered / characterization-first / light)

## Per-recommendation loop
1. Read the rec and every file it cites.
2. Build the refactor-job input (see
   [skills/tdd/references/refactor-jobs.md](../../skills/tdd/references/refactor-jobs.md)):
   `targets` = the rec's cited files; `change` = the rec's Proposed change verbatim;
   `test_command` + `baseline_status` = as given; `coverage` = per the gate;
   `new_behavior` = any part the rec marks as new behavior (usually none).
3. Dispatch the TDD refactor job.
4. Record the returned `outcome` into the rec's Status line and append the Apply-log
   line (timestamp, ID, suite result, diffstat) — using the report's exact fields.
   `applied` → Status `applied`; `failed (reverted)` → Status `failed (reverted)`.
5. In a chain, a mid-chain revert invalidates dependents — mark them
   `skipped` with a note pointing at the failed rec.

## Hard rules
- Only your rec (or chain). Update only Status lines + the Apply log in the report.
- Unrelated problems go in your final summary, not into any change.

## Yield back
Per rec ID: applied/failed/skipped + one line; final suite status vs baseline;
total diffstat; anything noticed but not touched.
```

- [ ] **Step 4: Run integrity guards**

Run: `python3 -m pytest tests/test_skill_integrity.py -q`
Expected: 3 passed (the new links — refactor-jobs.md exists from Task 2; overlap map is referenced from reviewer.md, so if `solid-gof-overlap.md` is not yet created, this RED is expected — create the overlap map now in Task 5 before considering Stage C done, or temporarily use plain text and convert in Task 5). Prefer to proceed straight into Task 5 and run the guard once after it.

- [ ] **Step 5: Commit**

```bash
git add docs/refactor-agents/
git commit -m "docs(refactor): lens-agnostic analyzer/reviewer/implementer roles (TDD-coordinated apply)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 5: Overlap map + coverage guard + git-convention edit

**Files:**
- Modify: `tests/test_skill_integrity.py` (add coverage test)
- Create: `docs/solid-gof-overlap.md`
- Modify: `docs/git-convention.md`

- [ ] **Step 1: Add the coverage guard (RED first)**

Append to `tests/test_skill_integrity.py`:

```python
OVERLAP_MAP = DOCS_DIR / "solid-gof-overlap.md"


def test_overlap_map_covers_all_23_patterns():
    text = OVERLAP_MAP.read_text()
    missing = [pattern for pattern in GOF_PATTERNS if pattern not in text]
    assert not missing, f"overlap map missing patterns: {missing}"
```

- [ ] **Step 2: Run — verify it fails**

Run: `python3 -m pytest tests/test_skill_integrity.py::test_overlap_map_covers_all_23_patterns -q`
Expected: FAIL (`FileNotFoundError` — `solid-gof-overlap.md` does not exist yet).

- [ ] **Step 3: Create `docs/solid-gof-overlap.md` (all 23 rows)**

```markdown
# SOLID ↔ GoF overlap map

Both reviewers read this. The two lenses see the same code from different angles;
this map keeps them cross-referencing instead of issuing conflicting recs.

Uses:
1. **Cross-reference** — every finding names its overlapping principle/pattern.
2. **Hand off** — a rec better expressed in the other lens is marked and the other
   skill recommended.
3. **Dedup on a shared branch** — when both lenses run, the second reads the first's
   `*-reports/` and references existing rec IDs instead of duplicating.

| GoF pattern | Category | Serves (SOLID) | Typical shared smell / handoff note |
|---|---|---|---|
| Abstract Factory | Creational | DIP, OCP | domain constructs concrete infra → SOLID DIP; GoF Abstract Factory for product families |
| Builder | Creational | SRP | telescoping/god constructor → separate construction from representation |
| Factory Method | Creational | OCP, DIP | `if/elif` picking a class to instantiate → subclass-chosen product |
| Prototype | Creational | — (performance) | expensive init + cloning; usually no direct principle overlap |
| Singleton | Creational | ⚠ tension with DIP | a module-level singleton is a DIP smell to SOLID; prefer injection — reconcile before suggesting |
| Adapter | Structural | DIP, ISP | incompatible third-party/legacy interface used across call sites |
| Bridge | Structural | DIP, OCP | combinatorial subclass explosion → split into two hierarchies |
| Composite | Structural | LSP, OCP | `isinstance` checks in recursive tree traversal → uniform treatment |
| Decorator | Structural | OCP, SRP | cross-cutting concern (logging/caching/auth) copy-pasted across classes |
| Facade | Structural | SRP, ISP | client orchestrating 3+ subsystem classes in the same sequence |
| Flyweight | Structural | — (performance) | many identical objects consuming memory; not a readability principle |
| Proxy | Structural | SRP, OCP | lazy-load/access-control logic mixed into the subject |
| Chain of Responsibility | Behavioral | OCP, SRP | `if/elif` handler chain whose order/set changes at runtime |
| Command | Behavioral | SRP, OCP | undo/redo/queue; UI action coupled to business logic |
| Interpreter | Behavioral | OCP, SRP | small grammar/expression evaluator crammed into one function |
| Iterator | Behavioral | ISP, LSP | traversal exposes a collection's internal structure |
| Mediator | Behavioral | SRP, DIP | many-to-many tangled dependencies between components |
| Memento | Behavioral | SRP | undo needs a state snapshot without breaking encapsulation |
| Observer | Behavioral | DIP, OCP, SRP | subject calls concrete observers directly → depend on observer interface |
| State | Behavioral | OCP, SRP, LSP | `if/elif` on a state variable with per-state behavior |
| Strategy | Behavioral | OCP, DIP | `if algo == "x"` selecting among interchangeable algorithms (the canonical overlap) |
| Template Method | Behavioral | OCP, DIP | copy-pasted algorithm skeletons differing only in steps |
| Visitor | Behavioral | OCP, SRP | `isinstance` dispatch to add operations across a stable hierarchy |

**Reconciliation rule:** when a smell maps to both a SOLID principle and a GoF
pattern (e.g. a duplicated type-switch = OCP + Strategy), it is **one** change, not
two. Whichever lens is running files the rec; the other lens references that rec ID.
For ⚠ entries (Singleton), the lenses can disagree — surface the tension to the human
rather than auto-recommending.
```

- [ ] **Step 4: Convert the overlap-map references in Tasks 3 & 4 to markdown links**

Ensure `docs/refactor-workflow.md` (Phase 2) and `docs/refactor-agents/reviewer.md` link `solid-gof-overlap.md` via markdown-link syntax (they now resolve).

- [ ] **Step 5: Edit `docs/git-convention.md` applicability line**

Change `(today: `solid` and `tdd`; ...)` to `(today: `solid`, `tdd`, and `gof`; ...)`.

- [ ] **Step 6: Run integrity guards (all green now)**

Run: `python3 -m pytest tests/test_skill_integrity.py -q`
Expected: 4 passed (frontmatter, links resolve, version mirrors, overlap-map coverage).

- [ ] **Step 7: Commit**

```bash
git add tests/test_skill_integrity.py docs/solid-gof-overlap.md docs/git-convention.md docs/refactor-workflow.md docs/refactor-agents/reviewer.md
git commit -m "docs(refactor): 23-pattern SOLID↔GoF overlap map + coverage guard

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Stage D — GoF references (the lens)

### Task 6: Port and refine `patterns.md` with a completeness guard

**Files:**
- Modify: `tests/test_skill_integrity.py` (add completeness test)
- Create: `skills/gof/references/patterns.md`

- [ ] **Step 1: Add the completeness guard (RED first)**

Append to `tests/test_skill_integrity.py`:

```python
PATTERNS_MD = SKILLS_DIR / "gof" / "references" / "patterns.md"
REQUIRED_PATTERN_SUBSECTIONS = (
    "**Intent**", "**Detect by**", "**Grade A**",
    "**Grade C/D issues**", "**Suggest when**", "**Don't suggest when**",
)


def _pattern_blocks(text):
    """Map each '### <pattern>' heading to the text of its block (up to the next heading)."""
    blocks = {}
    current_name = None
    current_lines = []
    for line in text.splitlines():
        heading = re.match(r"^###\s+(.*\S)\s*$", line)
        if heading:
            if current_name is not None:
                blocks[current_name] = "\n".join(current_lines)
            current_name = heading.group(1)
            current_lines = []
        elif re.match(r"^##\s", line):  # a category header closes the current block
            if current_name is not None:
                blocks[current_name] = "\n".join(current_lines)
                current_name = None
                current_lines = []
        elif current_name is not None:
            current_lines.append(line)
    if current_name is not None:
        blocks[current_name] = "\n".join(current_lines)
    return blocks


def test_patterns_md_has_all_23_with_required_subsections():
    blocks = _pattern_blocks(PATTERNS_MD.read_text())
    missing_patterns = [pattern for pattern in GOF_PATTERNS if pattern not in blocks]
    assert not missing_patterns, f"patterns.md missing: {missing_patterns}"
    incomplete = []
    for pattern in GOF_PATTERNS:
        for subsection in REQUIRED_PATTERN_SUBSECTIONS:
            if subsection not in blocks[pattern]:
                incomplete.append(f"{pattern}: missing {subsection}")
    assert not incomplete, "patterns.md incomplete:\n" + "\n".join(incomplete)


def test_patterns_md_defines_shared_rubrics():
    text = PATTERNS_MD.read_text()
    for required_block in ("## Grade rubric", "## Tier rubric", "## Risk rubric"):
        assert required_block in text, f"patterns.md missing '{required_block}'"
```

- [ ] **Step 2: Run — verify it fails**

Run: `python3 -m pytest tests/test_skill_integrity.py -k patterns -q`
Expected: FAIL (`FileNotFoundError` — `skills/gof/references/patterns.md` absent).

- [ ] **Step 3: Create `skills/gof/references/patterns.md` by porting + refining**

Copy every one of the 23 pattern entries **verbatim** from `~/.claude/skills/gof/references/patterns.md` (Intent / Detect by / Grade A / Grade C/D issues / Suggest when are already good). Then apply these exact refinements:

1. **Header + intro:** replace the first line and the "Used by the gof-patterns skill" note with: "Shared rubric for the `gof` skill's analyzer and reviewer. The skill's goal is real reader value: every *opportunity* must argue a concrete benefit at a specific location, and 'no opportunity' (N/A) is a valid, trust-building outcome."
2. **Add a `**Don't suggest when**` line to each of the 23 patterns** — the anti-over-engineering guard (the reason GoF advice fails is proposing patterns where a simpler form reads better). Name the cheaper alternative and the small-scale case. Examples (author all 23 in this spirit):
   - Strategy: "Don't suggest when there is a single algorithm, or only 2–3 stable branches a dict dispatch handles more readably; a strategy-class explosion for three cases is worse."
   - Singleton: "Don't suggest — prefer a module-level object or dependency injection; a Singleton usually *adds* a DIP/testability problem. Only note it for a genuinely global resource, and cross-check the overlap map's ⚠ tension."
   - Builder: "Don't suggest for ≤4 params or a simple dataclass; a keyword constructor reads better."
   - Visitor: "Don't suggest for a hierarchy that changes often (adding an element type forces every visitor to change) or when a simple method on each element suffices."
   - Facade: "Don't suggest when the subsystem is already one or two classes, or when the 'facade' would just be a pass-through."
   - Observer: "Don't suggest for a single, static listener — a direct call is clearer than a subscription list."
   - (Author the analogous guard for the remaining 17.)
3. **Append three shared-rubric blocks** at the end so the analyzer and reviewer share calibration with `solid` and the apply phase consumes identical fields:

```markdown
## Grade rubric (detected patterns)
Always use the full label, not just the letter.
- **A — Clean implementation** — idiomatic Python; follows GoF intent; no obvious flaws
- **B — Mostly correct** — minor deviations (missing abstraction, slight coupling)
- **C — Structural issues** — recognizable but partially broken or awkward
- **D — Significantly misimplemented** — intended as the pattern but mostly wrong
- **F — Fundamentally incorrect** — wrong in a way that could cause harm
A mediocre singleton is a C, not a B. Grade honestly.

## Tier rubric (actionable recommendations: opportunities + low-grade patterns)
Tier by reader impact × blast radius, matching the `solid` lens so the shared
apply phase is identical.
- **Critical** — a missing/forced pattern actively blocks comprehension or safe
  change today (a duplicated hand-rolled dispatch in 3+ places; a god facade).
- **Major** — clear, recurring friction, contained blast radius (a two-site
  dispatch that wants Strategy; a D-grade pattern in one subsystem).
- **Minor** — emerging or cosmetic-adjacent; cheap, low urgency.
When in doubt, tier down.

## Risk rubric (Low / Medium / High)
Risk = chance the *change* breaks something, independent of tier. Gates the apply
phase: High-risk recs get individual human confirmation.
- **Low** — internal, mechanical, well covered (introduce a Protocol, inject a
  strategy with a default).
- **Medium** — several call sites or partially tested code.
- **High** — public API signatures, cross-module moves, persistence-adjacent, or
  untested code. Rated up when in doubt.
```

- [ ] **Step 4: Run — verify green**

Run: `python3 -m pytest tests/test_skill_integrity.py -k patterns -q`
Expected: 2 passed (`...has_all_23...`, `...defines_shared_rubrics`).

- [ ] **Step 5: Commit**

```bash
git add tests/test_skill_integrity.py skills/gof/references/patterns.md
git commit -m "feat(gof): port+refine 23-pattern rubric with don't-suggest guards and tier/risk rubrics

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 7: GoF report template, HTML spec, Python idioms

**Files:**
- Create: `skills/gof/references/report-template.md`, `skills/gof/references/html-report.md`, `skills/gof/references/python.md`

- [ ] **Step 1: Create `skills/gof/references/report-template.md`**

Mirror `skills/solid/references/report-template.md` structure exactly (the apply phase parses IDs/Risk/Status), adapted for the pattern lens. Required shape:

```markdown
# GoF report template

The reviewer writes `gof-reports/GOF-ANALYSIS-<YYYY-MM-DD>.md` in exactly this
shape. IDs (`C*/M*/N*`), `Risk`, and `Status` are load-bearing (parsed by the
apply phase). IDs are permanent once assigned.

# GoF Analysis — <project> — <YYYY-MM-DD>

## Summary
- Scope: <path>, <N> source files
- Test suite: <command> — <green / N failing / none>
- Detected patterns: <name [grade], ...> · Maturity: <Nascent/Emerging/Moderate/Mature>
- Recommendations: <n> Critical, <n> Major, <n> Minor
- Top wins: <2–3 recs a human should care about, one line each>

## Detected patterns (graded inventory — informational)
### [Category] · <Pattern> — Grade: <letter — full label>
- Location / Evidence / Strengths / Issues / Recommendation (as in the standalone)
- **Overlap:** <SOLID principle / "none">

## Recommendations
### Critical
#### [C1] <imperative title, e.g. "Introduce Strategy for the pricing dispatch">
- **Pattern:** <one of the 23>
- **Location:** `file:line` <all sites>
- **Problem now:** <the concrete pain: duplicated/forced/missing structure>
- **Proposed change:** <behavior-preserving steps; name new classes/protocols>
- **Expected benefit:** <what becomes easier/safer>
- **Overlap:** <SOLID principle + any existing solid-reports rec ID, or "none">
- **Risk:** <Low|Medium|High> — <what could break>
- **Verification:** <which tests cover this; what to check after>
- **Status:** pending
### Major
#### [M1] ...
### Minor
#### [N1] ...

## Not applicable
| Pattern | Reason |
|---|---|
| <pattern> | <one line> |

## Reviewer notes
- Pruned suggestions + reasons; added findings; areas not examined; cross-lens references.

## Apply log
<!-- <UTC ts> [C1] applied — suite green (42 passed) — diffstat: 2 files, +80/-30 -->
```

- [ ] **Step 2: Create `skills/gof/references/html-report.md`**

Port the standalone skill's Step 4d HTML spec (read `~/.claude/skills/gof/SKILL.md` lines ~275–332) into a standalone reference: self-contained (no CDN), sticky sidebar nav, grade badges (A green / B blue / C amber / D orange / F red), category chips, per-pattern cards, before/after sketch styling, N/A grid. Add one line: "The HTML mirrors the MD report's Detected patterns + Recommendations + Not applicable sections; it is a gitignored artifact written after the MD."

- [ ] **Step 3: Create `skills/gof/references/python.md`**

Mirror `skills/solid/references/python.md` shape: per-pattern Python idioms (module-level singleton vs `__new__`; `functools`/class decorators; `__iter__`/generators; `abc.ABC`+`@abstractmethod` for Abstract Factory) and the test-runner detection table (copy the detection table from `skills/solid/references/python.md` verbatim — pytest/unittest discovery).

- [ ] **Step 4: Run integrity guards**

Run: `python3 -m pytest tests/test_skill_integrity.py -q`
Expected: 6 passed (no new frontmatter/links broken; these are reference files, not SKILL.md).

- [ ] **Step 5: Commit**

```bash
git add skills/gof/references/report-template.md skills/gof/references/html-report.md skills/gof/references/python.md
git commit -m "feat(gof): report template (IDs/Risk/Status), HTML preview spec, Python idioms

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Stage E — The GoF skill

### Task 8: `gof` SKILL.md + agent stubs

**Files:**
- Create: `skills/gof/SKILL.md`, `skills/gof/agents/analyzer.md`, `skills/gof/agents/reviewer.md`, `skills/gof/agents/implementer.md`

- [ ] **Step 1: Create `skills/gof/SKILL.md`**

Frontmatter (exact):

```yaml
---
name: gof
description: >
  Gang of Four design-pattern analysis and guided refactor for Python codebases.
  Two-stage analysis: an analyzer detects existing patterns (graded A–F) and
  proposes where unimplemented patterns genuinely help; an independent reviewer
  verifies every finding, tiers the actionable ones (Critical/Major/Minor), and
  cross-references the SOLID lens. After human sign-off, approved changes are
  applied through the TDD refactor engine, one at a time, suite green after each.
  Use for "/gof", "what patterns are in my code?", "should I use a
  factory/observer/strategy here?", "is this a good Singleton?", pattern
  detection, or any mention of creational / structural / behavioral patterns.
user-invocable: true
metadata:
  version: "0.1.0"
---
```

Body (thin wiring — required content):
- One-paragraph intro: what the skill does (detect+grade, propose, apply via TDD).
- "**This skill follows [docs/refactor-workflow.md](../../docs/refactor-workflow.md).** Its lens is `references/patterns.md` (rubric) + `references/report-template.md`. Reports go to `gof-reports/`. The HTML preview follows `references/html-report.md`. Python idioms + test detection: `references/python.md`."
- "**Invocation:** `/gof [path]`" + pre-authorization note (copy SOLID's).
- **Lens-specific analyzer note:** the analyzer runs two sub-passes — **detect** (grade existing patterns A–F) and **opportunity** (locate genuine applications; obey each pattern's `Don't suggest when`; N/A is valid). Both feed the draft.
- **Report note:** apply-eligible = the recommendations (opportunities + low-grade detected patterns); the graded inventory + N/A table are context. After the MD, the reviewer writes the HTML preview.
- **Interop note:** cross-reference SOLID per [docs/solid-gof-overlap.md](../../docs/solid-gof-overlap.md); reconcile the ⚠ Singleton tension with the human.
- File map (list the references + shared docs, all as markdown links).

- [ ] **Step 2: Create the three agent stubs**

`skills/gof/agents/analyzer.md`:
```markdown
# GoF analyzer

Read [../../../docs/refactor-agents/analyzer.md](../../../docs/refactor-agents/analyzer.md).
Your rubric is [../references/patterns.md](../references/patterns.md). Run two
sub-passes: detect existing patterns (grade A–F) and locate genuine opportunities
(obey each pattern's "Don't suggest when"). Draft output: `gof-reports/findings-draft.md`.
```

`skills/gof/agents/reviewer.md`:
```markdown
# GoF reviewer

Read [../../../docs/refactor-agents/reviewer.md](../../../docs/refactor-agents/reviewer.md).
Your rubric is [../references/patterns.md](../references/patterns.md); your report
template is [../references/report-template.md](../references/report-template.md).
Cross-reference the SOLID lens via
[../../../docs/solid-gof-overlap.md](../../../docs/solid-gof-overlap.md). After the
MD report, write the HTML preview per [../references/html-report.md](../references/html-report.md).
Final report: `gof-reports/GOF-ANALYSIS-<YYYY-MM-DD>.md`.
```

`skills/gof/agents/implementer.md`:
```markdown
# GoF implementer (TDD-coordinator)

Read [../../../docs/refactor-agents/implementer.md](../../../docs/refactor-agents/implementer.md).
Your report template is [../references/report-template.md](../references/report-template.md).
Apply each approved rec by dispatching a TDD refactor job; record outcomes into the
report's Status lines + Apply log.
```

- [ ] **Step 3: Run integrity guards**

Run: `python3 -m pytest tests/test_skill_integrity.py -q`
Expected: 6 passed. Confirms `gof` frontmatter is valid AND every stub link (into `docs/refactor-agents/*`, `references/*`, `solid-gof-overlap.md`) resolves — verify the `../` depth is right (`skills/gof/agents/` → repo root is `../../../`).

- [ ] **Step 4: Commit**

```bash
git add skills/gof/SKILL.md skills/gof/agents/
git commit -m "feat(gof): skill wiring + agent stubs following the shared refactor workflow

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 9: GoF behavioral evals

**Files:**
- Modify: `tests/test_skill_integrity.py` (add eval-schema test)
- Create: `evals/gof-evals.json`

- [ ] **Step 1: Add the eval-schema guard (RED first)**

Append to `tests/test_skill_integrity.py`:

```python
GOF_EVALS = REPO_ROOT / "evals" / "gof-evals.json"
EVAL_CASE_KEYS = {"id", "skill", "prompt", "expected_output", "assertions"}


def test_gof_evals_valid_schema():
    data = json.loads(GOF_EVALS.read_text())
    assert data["skill_name"] == "gof"
    assert isinstance(data["evals"], list) and data["evals"], "no eval cases"
    for eval_case in data["evals"]:
        assert EVAL_CASE_KEYS <= eval_case.keys(), f"case {eval_case.get('id')} missing keys"
        assert isinstance(eval_case["assertions"], list) and eval_case["assertions"]
```

- [ ] **Step 2: Run — verify it fails**

Run: `python3 -m pytest tests/test_skill_integrity.py::test_gof_evals_valid_schema -q`
Expected: FAIL (`FileNotFoundError`).

- [ ] **Step 3: Create `evals/gof-evals.json`**

Follow `evals/tdd-evals.json` shape. At least four cases covering: (id 1) trigger + detect-and-grade on a repo with a Singleton; (id 2) an opportunity proposal for an `if/elif` dispatch → Strategy, asserting it references the overlap map's OCP link; (id 3) the "Don't suggest" restraint — a 3-param class must NOT get a Builder suggestion; (id 4) apply-phase routing — an approved rec is applied via a TDD refactor job with the suite green after. Example case:

```json
{
  "skill_name": "gof",
  "evals": [
    {
      "id": 1,
      "skill": "gof",
      "prompt": "/gof — what design patterns are in this code and how good are they?",
      "expected_output": "Runs Phase 0 inventory + test baseline, dispatches analyzer (detect+grade) then reviewer, writes gof-reports/GOF-ANALYSIS-<date>.md plus the HTML preview, and summarizes detected patterns with A–F grades and top opportunities.",
      "assertions": [
        "Creates gof-reports/ and git-excludes it via .git/info/exclude",
        "Detects existing patterns and grades each with the full label (e.g. 'B — Mostly correct')",
        "Writes the final report using references/report-template.md (IDs/Risk/Status present)",
        "Writes a self-contained HTML preview per references/html-report.md",
        "Does not apply any change without the human decision gate"
      ]
    }
  ]
}
```
Author cases 2–4 in the same shape with the assertions described above.

- [ ] **Step 4: Run — verify green**

Run: `python3 -m pytest tests/test_skill_integrity.py::test_gof_evals_valid_schema -q`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_skill_integrity.py evals/gof-evals.json
git commit -m "test(gof): behavioral evals for detect/grade, opportunity, restraint, apply-via-tdd

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Stage F — SOLID rework onto the shared model

### Task 10: Route SOLID's apply through TDD; point to shared docs

**Files:**
- Modify: `skills/solid/SKILL.md`
- Modify (→ stubs): `skills/solid/agents/analyzer.md`, `skills/solid/agents/reviewer.md`, `skills/solid/agents/implementer.md`

**Interfaces:**
- Consumes: `docs/refactor-workflow.md` (Task 3), `docs/refactor-agents/*` (Task 4), the refactor-job contract (Task 2).

- [ ] **Step 1: Slim `skills/solid/SKILL.md`**

Replace the Phase 0–5 body (now living in `docs/refactor-workflow.md`) with: a short intro + "**This skill follows [../../docs/refactor-workflow.md](../../docs/refactor-workflow.md).** Its lens is `references/principles.md` (rubric) + `references/report-template.md`, with `references/python.md` / `references/typescript.md` for language specifics. Reports go to `solid-reports/`." Keep the Invocation, Guardrails, and "Evolving this skill" sections (these are lens-specific). **Add** an interop note: cross-reference the GoF lens via [../../docs/solid-gof-overlap.md](../../docs/solid-gof-overlap.md). In the (now-shortened) apply description, state that approved recs are applied **through the TDD refactor job** — SOLID's former "characterization-tests-first / light-verification" choices become the refactor job's `coverage` policy set at the gate.

- [ ] **Step 2: Convert `skills/solid/agents/*` to stubs**

Replace each with a pointer (mirror Task 8's stubs), naming the SOLID lens:
```markdown
# SOLID analyzer
Read [../../../docs/refactor-agents/analyzer.md](../../../docs/refactor-agents/analyzer.md).
Your rubric is [../references/principles.md](../references/principles.md). Draft output:
`solid-reports/findings-draft.md`.
```
(analogously for reviewer.md — add report template + overlap-map links — and implementer.md — TDD-coordinator).

- [ ] **Step 3: Bump SOLID version**

`skills/solid/SKILL.md` frontmatter `metadata.version` `"0.3.0"` → `"0.4.0"`.

- [ ] **Step 4: Run the full suite**

Run: `python3 -m pytest -q`
Expected: all pass — the pre-existing config-sync tests are untouched; integrity guards confirm SOLID's frontmatter valid and its new markdown links resolve (`../../docs/...`, `../references/...`).

- [ ] **Step 5: Commit**

```bash
git add skills/solid/SKILL.md skills/solid/agents/
git commit -m "refactor(solid): apply through the TDD refactor engine; adopt shared workflow + GoF interop

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Stage G — Manifest, README, version

### Task 11: Register gof, bump to 0.10.0, document

**Files:**
- Modify: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `pyproject.toml`, `README.md`

- [ ] **Step 1: Bump the three version mirrors to `0.10.0`**

- `.claude-plugin/plugin.json`: `"version": "0.10.0"`.
- `pyproject.toml`: `version = "0.10.0"  # mirrors .claude-plugin/plugin.json (canonical source of truth)`.
- `.claude-plugin/marketplace.json`: `plugins[0].version` → `"0.10.0"`.

- [ ] **Step 2: Update descriptions + keywords**

- `plugin.json` `description`: append "…a GoF design-pattern analysis & guided-refactor workflow (creational/structural/behavioral), …" and add keywords `"gof"`, `"design-patterns"`, `"gang-of-four"`.
- `marketplace.json` `plugins[0].description`: add a `/gof` clause alongside `/solid`.

- [ ] **Step 3: Update `README.md`**

Add a row to the *Dev workflow* skills table (after the `tdd` row):
```markdown
| gof | `/gof [path]` | Gang of Four pattern analysis & guided refactor: analyzer detects + grades existing patterns (A–F) and proposes where unimplemented patterns genuinely help → independent reviewer verifies, tiers (Critical/Major/Minor) and cross-references `/solid` → after sign-off, approved changes are applied through the TDD refactor engine, suite green after each. Produces a Markdown report + self-contained HTML preview in `gof-reports/` |
```
And add one line under the convention note: "`/solid` and `/gof` apply their changes through `/tdd`'s programmatic refactor job and cross-reference each other via `docs/solid-gof-overlap.md`."

- [ ] **Step 4: Run the full suite**

Run: `python3 -m pytest -q`
Expected: all pass — `test_version_mirrors_match` is green only when all three mirrors read `0.10.0` (if any step was missed, it fails and names the drift).

- [ ] **Step 5: Commit**

```bash
git add .claude-plugin/plugin.json .claude-plugin/marketplace.json pyproject.toml README.md
git commit -m "chore(gof): register skill, document ecosystem, bump 0.9.4 → 0.10.0

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Stage H — Verify & retire the standalone

### Task 12: Full verification + dry-run

- [ ] **Step 1: Full suite green**

Run: `python3 -m pytest -q`
Expected: all pass (config-sync suite + all `tests/test_skill_integrity.py` guards).

- [ ] **Step 2: Dry-run `gof` on a throwaway sample**

Create `/private/tmp/claude-511/-Users-ai/94249d85-5b70-4650-a357-dbfeff1121b1/scratchpad/gof-sample/pricing.py` with a deliberate `if kind == "percent"/"fixed"/"tiered"` dispatch and a naive `Config` module-level singleton, and a trivial `tests/test_pricing.py` that passes. Invoke `/gof` on that dir. Acceptance checklist:
  - `gof-reports/GOF-ANALYSIS-<date>.md` written with a **Strategy** opportunity (Major/Critical) whose **Overlap** cites OCP, and a Singleton entry flagged with the ⚠ tension.
  - HTML preview generated, opens in a browser, grade badges render.
  - The decision gate asks before applying; approving the Strategy rec dispatches a **TDD refactor job**; `test_pricing.py` still green afterward; the rec Status flips to `applied` with an Apply-log line.
  - A 3-parameter class in the sample gets **no** Builder suggestion (restraint).

- [ ] **Step 3: Dry-run reworked `/solid`** on the same sample: confirm it still produces `solid-reports/…`, applies one rec via a TDD refactor job, and cross-references the GoF Strategy rec by ID rather than duplicating it.

- [ ] **Step 4: Commit any doc corrections** surfaced by the dry-run (no code changes expected).

```bash
git add -A && git commit -m "docs(gof): corrections from dry-run acceptance

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 13 (GATED — only after Task 12 passes): Retire the standalone skill

> This touches the user's live config **outside** the repo. Do it only after Task 12 is green and the user confirms. It is not a repo commit.

- [ ] **Step 1: Confirm with the user**, then remove the standalone skill:

```bash
rm -rf ~/.claude/skills/gof
```

- [ ] **Step 2: Re-bundle config-sync** if the standalone was bundled: check `~/.claude/config-sync-repo/bundles/skills/gof` and, per the `config-sync` skill, re-export so the removal propagates (invoke `/config-sync`; do not hand-edit bundles).

- [ ] **Step 3:** Verify only the plugin `gof` remains: `ls ~/.claude/skills/ | grep -w gof` returns nothing; `/gof` now resolves to `mente-apex:gof`.

---

## Finishing

Per `docs/git-convention.md`: **offer, never auto-run** the PR. After Task 12 (and 13 if approved), propose a Conventional Commit summary of the branch and ask whether to open a PR (hand to `/ship`). "Leave it on the branch" and "discard it" are first-class answers.

---

## Self-Review

**Spec coverage** (spec §→task): §3 TDD refactor job → T2; §4.1 workflow → T3; §4.2 agents → T4; §4.3 overlap map → T5; §4.4 git-convention → T5; §5 gof skill (patterns/report/html/python/SKILL/agents) → T6,T7,T8; §5 evals → T9; §6 SOLID rework → T10; §7 manifest/README/version → T11; §7 retire standalone → T13; §8 verify → T12. §2.1 DIP framing is realized structurally (engine + lens abstractions injected via workflow/agent params) — no dedicated task needed. §9 open questions: detected-pattern-inventory-vs-recs is resolved in T7/T8 (low-grade detected patterns are apply-eligible; clean ones inventory-only); HTML parity resolved in T7 (kept); full 23-row overlap map delivered in T5.

**Placeholder scan:** test code is complete and runnable; prose-doc tasks give exact frontmatter/contract/stub text + named source-to-port + enumerated transformations, with structural guards (`test_patterns_md_*`, overlap coverage, eval schema, link resolution, version mirrors) mechanically enforcing completeness. The one judgment-bearing authoring item — 23 per-pattern "Don't suggest when" lines — is guarded by `test_patterns_md_has_all_23_with_required_subsections` and seeded with six worked examples + an explicit rule.

**Type/name consistency:** refactor-job input/output keys are identical in T2 (contract), T4 (implementer consumes them), and T9 (eval asserts them). Report field names (`C*/M*/N*`, `Risk:`, `Status:`) are identical across `solid` and `gof` templates (T7) and consumed by the shared implementer (T4). `GOF_PATTERNS` is defined once in T1 and reused by T5/T6 tests. Version `0.10.0` is applied to all three mirrors in T11 and enforced by `test_version_mirrors_match`.
