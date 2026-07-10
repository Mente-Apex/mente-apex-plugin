# GoF pattern lens + a shared TDD refactor engine — design

**Date:** 2026-07-08
**Project:** mente-apex-plugin — dev-workflow skills
**Adds:** a new `gof` skill (Gang of Four design-pattern analysis + guided apply)
**Changes:** `tdd` (new programmatic *refactor job*), `solid` (apply phase routes through TDD), shared `docs/`
**Retires (gated on verification):** the standalone `~/.claude/skills/gof` single-pass analyzer

---

## 1. Problem & goal

The plugin already ships two dev-workflow skills that share almost the same
shape — analyze a codebase, produce a tiered plan, apply it under a test net:

- `solid` — the **principle** lens (SRP/OCP/LSP/ISP/DIP), with a full
  analyzer → reviewer → human gate → guided apply workflow.
- `tdd` — the **test-first implementation** engine, already exposing a
  *programmatic* calling contract and a *legacy* mode (characterization pins
  before touching untested code).

Boris wants a third skill, `gof`, that does for the 23 Gang of Four **patterns**
what `solid` does for the five principles: scan the codebase, detect existing
patterns and grade them, exhaustively propose where an unimplemented pattern
would genuinely help, and — after sign-off — apply approved changes.

Two hard requirements shape the design beyond "clone SOLID":

1. **`gof` and `solid` must interoperate** — they overlap heavily (a duplicated
   type-switch is an *OCP* violation to SOLID and a *Strategy/Factory*
   opportunity to GoF; a domain class constructing its own DB client is *DIP*
   and an *Abstract Factory/Bridge* opportunity). They must cross-reference and
   hand off, never issue conflicting recommendations on the same branch.
2. **Both lenses apply changes through `tdd`** — TDD becomes the single
   implementation engine, so "how a change is safely made" lives in exactly one
   place.

A standalone `gof` skill already exists (`~/.claude/skills/gof`): a single-pass
detect-grade-suggest tool emitting a Markdown + polished HTML report. It has no
reviewer stage, no apply phase, and no interop. Its `references/patterns.md`
(23-pattern catalog with detection signals, an A–F grade rubric, and
"suggest-when" triggers) is strong and is **ported and refined**, not rewritten.

**Non-goals (YAGNI):** merging `solid` and `gof` into one skill; a GoF
opportunity engine that invents problems to justify every pattern; adapters for
languages beyond Python in v1 (the workflow is language-agnostic, deep support
is Python-first as it already is for `solid`/`tdd`).

---

## 2. Architecture — three skills, one engine, shared contracts

```
tdd  ──(programmatic refactor-job contract)──►  the engine: writes / changes code, test-first
        ▲                         ▲
        │ dispatches jobs         │ dispatches jobs
      solid  ◄── docs/solid-gof-overlap.md ──►  gof      (two lenses: rubric + report template)
        └────────── both follow docs/refactor-workflow.md ──────────┘
```

### 2.1 How Dependency Inversion shaped this

- **The engine is an abstraction, injected as a contract.** `solid` and `gof`
  depend only on TDD's *programmatic refactor-job contract* (§3) — a documented
  input/output shape — never on how TDD edits files. The engine can be
  substituted (a caller could stub it in an eval) because the seam is a
  contract, not a concrete call into TDD's internals.
- **The lens is an abstraction with two implementations.** The shared
  orchestration (`docs/refactor-workflow.md`, §4) and the shared agent roles
  (`docs/refactor-agents/`) depend on "a lens" — a `{rubric, report-template}`
  pair passed in — not on SOLID or GoF specifically. Adding a future lens
  (e.g. a security lens) means adding an implementation, editing no
  orchestration. That is Open/Closed for the skill repo itself.
- **Each collaborator is passed in, never hard-wired.** Agents receive their
  rubric path, report-template path, target path, and test command as inputs.
  No agent reaches for a global or instantiates its peer; the orchestrator is
  the composition root that wires lens → agents → engine.
- **Single Responsibility across the docs:** the *workflow* changes for one
  reason (the phase sequence), the *overlap map* for one reason (a new
  pattern↔principle relationship), each *rubric* for one reason (its lens's
  calibration). None of these three reasons to change share a file.

---

## 3. TDD gains a programmatic *refactor job* (the foundation)

TDD already documents two programmatic job kinds implicitly (feature, legacy).
Add an explicit third, **refactor**, for callers that need a *behavior-preserving
structural change under a green safety net*. This is additive — the feature and
legacy contracts are unchanged, so every existing caller keeps working.

### 3.1 Calling contract (stable — callers depend on it)

**Input** (from a lens's implementer-coordinator):

- `targets` — files/symbols the change touches
- `change` — the exact behavior-preserving restructuring (a rec's *Proposed
  change* text: e.g. "extract `PricingStrategy` protocol; move the three
  `if kind ==` branches into `Percent/Fixed/Tiered` strategy classes; inject
  the chosen strategy")
- `test_command` + `baseline_status` (green, or the tolerated pre-existing
  failures)
- `coverage` — whether the targets are currently exercised by the suite
- `new_behavior` — optional: any part of the change that is genuinely new
  behavior rather than structure-preserving

**Execution:**

1. **Safety net.** `coverage == none` → run TDD *legacy* mode: write
   characterization pins asserting what the code *actually does* today, to
   green. Covered → use the existing suite. (When current behavior looks wrong,
   flag it — do not silently "fix" it; that oddity may be load-bearing.)
2. **Apply** the smallest faithful version of `change`. Behavior-preserving;
   match house style; descriptive names, no single-letter variables; no new
   dependencies.
3. **New-behavior carve-out.** Anything in `new_behavior` runs as a normal
   *feature* red-green cycle (a failing test that demands it, then the minimum
   code) rather than as a silent structural edit.
4. **Verify.** Run the full `test_command`. Green (== baseline) → success. Red →
   one focused fix attempt; still red → **revert the entire job** (working tree
   back to the pre-job state) and report failure. Never edit a test's assertion
   to make a refactor pass — a disagreeing test means the change is wrong.

**Output** (stable summary the caller acts on without re-reading anything):
`job_id`, outcome (`applied` | `failed (reverted)`), tests written (pins + any
new feature tests), files touched, diffstat, final suite vs baseline, and
anything noticed-but-not-touched.

### 3.2 Files touched in `tdd`

- `skills/tdd/SKILL.md` — document the refactor job under "Work modes" and the
  programmatic contract; note it composes legacy-mode pinning + refactor-under-
  green, so it is not a new philosophy, only a named entry point. Add a
  reciprocal line to the refactor checklist: when a recurring smell is
  *pattern-shaped* (missing/duplicated/forced pattern), suggest a `/gof` audit
  — mirroring the existing `/solid` suggestion.
- `skills/tdd/references/refactor-jobs.md` (new) — the mechanics + a worked
  example of a refactor job driven by a SOLID/GoF rec.
- Bump `metadata.version` (1.2.0 → 1.3.0 — additive feature).

---

## 4. Shared orchestration & agents (`docs/`)

The analyzer → reviewer → gate → apply → loop workflow is identical for both
lenses. It is **extracted once** so it has a single home.

### 4.1 `docs/refactor-workflow.md` (new)

Generalizes SOLID's current SKILL.md body to "the lens." Phases:

- **Phase 0 — Inventory & baseline.** Scope the tree (skip vendored/generated);
  detect and **run** the test suite once (record baseline); create
  `<lens>-reports/` in the target project and git-exclude it.
- **Phase 1 — Analyzer.** Read-only draft findings via the lens's rubric →
  `<lens>-reports/findings-draft.md`.
- **Phase 2 — Reviewer.** Independently verify every finding against the real
  code, prune/adjust/tier, hunt cross-file misses, **cross-reference the other
  lens** via `docs/solid-gof-overlap.md`, and write the final report using the
  lens's report-template exactly (IDs / Risk / Status are load-bearing).
- **Phase 3 — Decision gate (human).** Summarize; `AskUserQuestion` for which
  recs to apply (by tier or ID). "None — just the doc" is a first-class
  outcome. No-suite handling (stop-at-doc / characterization-first / light
  verification) is chosen here and passed to the engine as the `coverage`
  policy.
- **Phase 4 — Apply via TDD.** Working branch first (per
  `docs/git-convention.md`). Split approved recs by Risk (High → individual
  human confirm). One rec (or same-file chain) at a time, **each dispatched as
  a TDD refactor job**; sequential is the contract, disjoint chains may run in
  parallel worktrees as an optimization (re-run the full suite on the merged
  tree).
- **Phase 5 — Review & loop.** Verify the suite yourself; spot-check diffs for
  "regressions of the cure"; loop (analyzer scoped to changed files → reviewer
  → gate), **hard cap 3 cycles**; summarize; **offer** commit + PR (hand to
  `/ship`), never auto-publish.
- **Guardrails** (shared): behavior-preserving always; the report is the single
  source of truth; judgment not dogma; fan-in at the orchestrator; every agent
  terminates by writing its artifact even when empty.

### 4.2 `docs/refactor-agents/{analyzer,reviewer,implementer}.md` (new)

Lens-agnostic role instructions, parameterized by the lens paths the
orchestrator passes in:

- **analyzer** — map the tree, hunt with the rubric's detection signatures,
  read suspects, one cross-file pass; emit evidence-backed draft findings.
- **reviewer** — verify each finding against current code, prune/adjust/tier +
  assign Risk, own the cross-file sweep and the cross-lens cross-reference,
  author the final report from the lens's template.
- **implementer** → **TDD-coordinator.** No longer edits code. Takes one rec
  (or chain), builds the refactor-job input from the rec's *Proposed change* +
  the Phase 0/3 test facts, **dispatches a TDD refactor job**, and records the
  returned outcome into the report's Status line + Apply log. This is where
  "both lenses apply through TDD" physically lives.

Each `skills/<lens>/agents/*.md` becomes a 2–3 line pointer: "read
`docs/refactor-agents/<role>.md`; your rubric is `references/<rubric>.md`; your
report template is `references/report-template.md`."

### 4.3 `docs/solid-gof-overlap.md` (new)

The pattern↔principle map both reviewers read. Rows (illustrative, to be
completed during build):

| GoF pattern | Typically serves | Handoff note |
|---|---|---|
| Strategy / Factory Method / Abstract Factory | OCP (dispatch), DIP (creation) | a duplicated type-switch: SOLID files it OCP, GoF as Strategy — one rec, not two |
| Bridge / Abstract Factory | DIP | combinatorial subclass explosion + concrete construction |
| Adapter | DIP, ISP | incompatible third-party/legacy interface |
| Decorator / Proxy / Chain of Responsibility | OCP | extension without modifying tested logic |
| Composite | LSP | uniform leaf/composite treatment |
| Observer / Command | SRP, OCP | decoupling producers from consumers |
| Template Method | OCP | fixed skeleton, varying steps |
| Facade | SRP, ISP | client orchestrating 3+ subsystem classes |

Three behaviors it enables:
1. **Cross-reference** — every finding names its overlapping principle/pattern.
2. **Hand off** — a rec better expressed in the other lens is marked and the
   other skill recommended.
3. **Dedup on a shared branch** — when both lenses run, the second reads the
   first's `*-reports/` and references existing rec IDs instead of emitting a
   conflicting duplicate.

### 4.4 `docs/git-convention.md` (edit)

Update the applicability line from "(today: `solid` and `tdd`)" to include
`gof`.

---

## 5. The `gof` skill

```
skills/gof/
  SKILL.md                    # thin: frontmatter + intro + "follows docs/refactor-workflow.md" + GoF lens notes + HTML-report note
  agents/                     # 3 pointer stubs → docs/refactor-agents/*
  references/
    patterns.md               # 23-pattern rubric (ported from standalone, verified/refined) — GoF's principles.md
    report-template.md        # tiered report (recs w/ IDs·Risk·Status) + graded detected-pattern inventory + N/A table
    html-report.md            # self-contained polished HTML preview spec (ported from standalone Step 4d)
    python.md                 # per-pattern Python idioms + test-runner detection (mirrors solid/python.md)
```

- **Frontmatter:** `name: gof`, `user-invocable: true`, a description covering
  the standalone's trigger phrases ("what patterns are in my code?", "should I
  use a factory/observer/strategy here?", creational/structural/behavioral,
  etc.), `metadata.version: "0.1.0"`.
- **Analyzer sub-passes** (both feed draft findings): **detect** existing
  patterns and grade **A–F**; **opportunity** scan for genuine, located
  applications of unimplemented patterns (no generic suggestions; N/A with a
  one-line reason is a valid, trust-building outcome).
- **Reviewer:** verify each; tier *actionable* items **Critical/Major/Minor** by
  reader-impact × blast-radius (same rubric SOLID uses, so Phase 4 is
  identical); confirm grades on detected patterns; cross-reference SOLID; write
  the MD report, then the **HTML preview** (grade badges, category chips, cards
  — kept as a differentiator; a gitignored artifact).
- **Report shape:** apply-eligible **recommendations** (opportunities + any
  low-grade detected pattern worth refactoring) carry `IDs/Risk/Status` so the
  shared apply phase consumes them unchanged; a **graded inventory** section and
  **N/A** table are informational context.

`patterns.md` is **reviewed and corrected** during build (§8 step 3): each of
the 23 entries checked for a crisp intent, accurate detection signals, an honest
A–F rubric, and a real "suggest-when" trigger; fixed where thin.

---

## 6. `solid` rework (into the shared model)

- Slim `skills/solid/SKILL.md` to: intro + "follows `docs/refactor-workflow.md`;
  lens = `references/principles.md` + `references/report-template.md` +
  `references/{python,typescript}.md`." Keep those reference files as-is
  (they are the SOLID lens).
- Replace `skills/solid/agents/*` with pointer stubs to
  `docs/refactor-agents/*` (the implementer stub now names the SOLID lens).
- **Apply phase routes through TDD:** SOLID's former "characterization-tests-
  first / light-verification" modes map onto the refactor job's `coverage`
  policy. The **observable workflow — phases, gate, report format
  (IDs/Risk/Status) — is unchanged**; only the apply *mechanism* moves behind
  the engine.
- Add the SOLID→GoF cross-reference/handoff (reviewer reads the overlap map).
- Bump `skills/solid/SKILL.md` `metadata.version` (0.3.0 → 0.4.0).

**Risk & mitigation:** this edits shipped SOLID. The report template and phase
contract are preserved verbatim, so nothing downstream breaks; the existing
`evals/` plus a dry-run on a sample repo (§8 step 7) guard the change; the whole
effort lands on one branch reviewable as a unit.

---

## 7. Manifest, README, versioning, retiring the standalone

- **Discovery:** `plugin.json` has no explicit skills array — skills are
  auto-discovered from `skills/`, so `gof/` is picked up automatically. Still
  update `plugin.json` **description** + **keywords** (add `gof`,
  `design-patterns`, `gang-of-four`) and the `marketplace.json` plugin
  description.
- **README.md:** add a `gof` row to the *Dev workflow* skills table, and a line
  noting `solid`/`gof` apply through `tdd` and cross-reference each other.
- **Version:** bump plugin `0.9.4 → 0.10.0` (new skill + engine rework — minor).
- **Retire the standalone** (`~/.claude/skills/gof`) **as the closing step,
  gated on verification:** once plugin `gof` is verified, remove the standalone
  skill and re-bundle config-sync so two `gof` skills never linger. Not started
  until §8 step 7 passes.

---

## 8. Build order (dependency-ordered; each layer independently testable)

1. **TDD refactor-job contract** — `refactor-jobs.md` + SKILL.md edits + version
   bump. Foundation both lenses import.
2. **Shared `docs/`** — `refactor-workflow.md`, `refactor-agents/*`,
   `solid-gof-overlap.md`, `git-convention.md` edit.
3. **Refine `patterns.md`** and author the rest of `skills/gof/references/`
   (report-template, html-report, python).
4. **`gof` SKILL.md + agent stubs** — wire lens to the shared workflow.
5. **`solid` rework** — slim SKILL.md, agent stubs, TDD-routed apply, interop.
6. **Manifest + README + versions.**
7. **Verify** — run existing `evals/`; dry-run `gof` and reworked `solid` on a
   sample Python repo (detect → report → gate → one apply via a TDD refactor
   job → suite green). Only on green: **retire the standalone** + re-bundle
   config-sync.

**Testing posture:** helper scripts (if any) and eval fixtures are built
**test-first** (the plugin dogfoods its own TDD skill). Skill instruction files
are validated via the `evals/` harness and the step-7 dry-run; the design keeps
each artifact small enough to review in one pass.

---

## 9. Open questions carried into planning

- Exact final row set for `docs/solid-gof-overlap.md` (all 23 patterns mapped,
  not just the eight illustrative rows above).
- Whether `gof`'s graded **detected-pattern inventory** should ever produce
  apply-eligible recs, or stay purely informational with only *opportunities*
  and *low-grade* patterns becoming recs (leaning: low-grade detected patterns
  are eligible; clean ones are inventory-only).
- HTML preview parity: keep the standalone's full visual spec, or trim to a
  lighter card layout for maintainability (leaning: keep, it is a
  differentiator and matches the deliverable-quality bar).
