# Design — Clean Code + Clean Architecture integration

**Date:** 2026-07-20
**Status:** Approved (brainstorming complete, ready for implementation plan)
**Plugin:** mente-apex

## Purpose

Bring Robert C. Martin's *Clean Code* and *Clean Architecture* into the plugin's
existing quality/architecture ecosystem (`solid`, `gof`, `ddd`, `tdd`, and the
current `clean-code`) **without overlap or contradiction**. Two deliverables:

1. **Rebuild `clean-code`** from a standalone single-file review skill into a
   **hardened, shared craftsmanship substrate** — one canonical standard consumed
   by every code-producing skill, plus a thin standalone review front-end.
2. **Add `clean-architecture`** — a new, deliberately-scoped **audit lens** on the
   existing shared refactor engine, covering only the genuinely net-new residue of
   *Clean Architecture* (the component/dependency-graph altitude) and deferring
   everything else to the lens that already owns it.

The guiding finding from the synthesis: *Clean Code the book already has a home*
(the existing skill captures ~13 of its ideas); and *most of Clean Architecture is
already owned* — its SOLID chapters by `solid`, its layering/Entities/Use-Cases and
the Dependency Rule *as you build* by `ddd`. The only unclaimed territory is the
**component graph** (cohesion/coupling/cycles/stability) and **auditing dependency
direction on existing code**. `clean-architecture` is scoped to exactly that.

## The altitude model (why nothing fights)

Each skill owns one **zoom level** and hands off at the seams via a shared overlap
map. This is the non-overlap contract:

| Zoom | Skill | Band | Book |
|------|-------|------|------|
| in | `tdd` | how changes are made safely (red-green-refactor) | Clean Code ch 9 |
| | `clean-code` | every line: names, functions, comments, errors | Clean Code (all) |
| | `solid` | class & module relationships (5 principles) | Clean Arch Part III |
| | `gof` | recurring object collaborations (+ Humble Object) | GoF |
| | `ddd` | domain model + layering *within a context* | DDD (+ Clean Arch V) |
| out | `clean-architecture` | the component/dependency graph across the system | Clean Arch IV–V |

**The tightest seam — `clean-architecture` vs `ddd`** — is resolved by an explicit
carve: **`ddd` asks "is the domain modeled well?"** (anemic model, aggregates,
ubiquitous language, ports at the domain edge); **`clean-architecture` asks "is the
component/dependency structure sound, regardless of how rich the domain is?"**
(cycles, stability direction, framework kept at the edge, package cohesion). A
codebase can pass one and fail the other. When both run, the overlap hub decides
who files a shared finding (see Part 3).

---

## Part 1 — `clean-code` rebuilt (hybrid substrate)

### Identity & shape

- **Name:** `clean-code`, user-invocable (`/clean-code`), version bump to `0.2.0`.
- **Dual role, made coherent:**
  - **Substrate (ambient, always-on):** a single canonical standard consumed by
    every code-producing skill so all written/refactored code is clean *by
    construction*. This is the important half — a write-time standard should never
    depend on being explicitly invoked.
  - **Standalone review (invoked):** `/clean-code` reviews a diff / file / PR for
    cleanliness with no other lens in play.

### The canonical standard (single source of truth)

- **`docs/clean-code-standard.md` (NEW)** — the hardened principles. Contents:
  - The current 15 leverage-ranked principles from today's `SKILL.md`, each with
    its severity and its **"where this bends"** note (kept verbatim in spirit —
    they are already good).
  - **Three chapters the current skill is missing**, added:
    - **Boundaries** (Clean Code ch 8) — wrap third-party code behind your own
      seam; *learning tests*; keep external APIs from spreading through the code.
      (This is also the code-level bridge into `clean-architecture`'s "framework
      is a detail".)
    - **Emergence / Kent Beck's 4 rules of Simple Design** (ch 12) — runs all
      tests → no duplication → expresses intent → fewest elements, *in that
      priority order*. Doubles as the review's ordering heuristic.
    - **Smells & Heuristics** (ch 17) — the G/N/F/C catalog, distilled into a
      review checklist (not a dogmatic dump).
  - **The meta-rule** (verbatim in spirit): if a rule makes the code *harder* to
    read, the rule is misapplied; readability for the next human wins.
- The standard is **tunable**, like `solid/references/principles.md`: severity
  rubric, and a **when-NOT-to-flag** column per principle so false positives
  (false-DRY merges, speculative abstraction, over-extraction, stripping good
  *why*-comments) stay out.

### Cross-cutting consumers (wired to read the standard)

- `docs/refactor-agents/implementer.md` — the shared implementer role gains: *the
  code produced by any applied recommendation follows `docs/clean-code-standard.md`*
  → every `solid` / `gof` / `clean-architecture` refactor comes out clean.
- `skills/tdd/references/refactor-jobs.md` (the refactor step) and `tdd`'s build
  path — new test-first code and the green→refactor step clean *to* the standard.

No principle text is copied into these consumers — they **link** the one standard,
so it is hardened once and never drifts.

### The thin skill (standalone review)

`skills/clean-code/` becomes thin and plugs into `refactor-workflow.md`
**Phases 0–3** (inventory → analyze → verify → report). It scales effort to scope
with **two gears**:

- **Quick (default for a diff / a few files):** a single read-through against the
  standard, findings inline in chat (today's "Suggested output" format). No
  subagents, no report file — the common case stays lightweight.
- **Deep (for a PR / module / on request):** the full **two-stage
  analyzer→reviewer** verification, writing a report to
  `docs/reports/clean-code/` (see Part 3). This is the "hardening" — trustworthy,
  verified findings when thoroughness matters.

**Apply (Phases 4–5) is opt-in only** — code-level nits are cheap to fix by hand
and riskiest to mass-apply, so review stops at findings unless the user asks to
apply, at which point it reuses the shared TDD-backed implementer.

### File map

```
docs/clean-code-standard.md        # NEW — the single canonical standard (tunable)
skills/clean-code/
  SKILL.md                         # thin: write-time default + two-gear review
  agents/
    analyzer.md                    # deep-gear pointer into shared analyzer role
    reviewer.md                    # deep-gear pointer into shared reviewer role
  references/
    report-template.md             # deep-gear review report format
evals/clean-code-evals.json        # NEW
```

(No `implementer.md` of its own — apply reuses the shared implementer role.)

---

## Part 2 — `clean-architecture` (new deliberate-audit lens)

### Identity & shape

- **Name:** `clean-architecture`, user-invocable (`/clean-architecture`, full name —
  no short alias by decision), version `0.1.0`, registered in the manifests.
- **Audit-first, no build mode.** `clean-architecture` never builds a greenfield
  layered structure — that is `ddd`'s job. Like `solid`/`gof` it *can* apply
  behavior-preserving refactors, but because most CA fixes are large architectural
  moves, apply is conservative: **advisory by default**, with only mechanical
  low-risk fixes (break a cycle, introduce a boundary port) opt-in appliable via the
  shared implementer.
- **Lens on the shared engine:** follows `docs/refactor-workflow.md` and the shared
  `docs/refactor-agents/` roles; supplies its own rubric + report template.

### Tiered scope (headline runs by default; the rest is opt-in)

| Tier | Checks | Default? | Detection |
|------|--------|----------|-----------|
| **Headline** | **dependency-direction / boundary audit** (does core import DB/web/framework? is the framework a replaceable detail?) · **cycles (ADP)** · **stability-direction (SDP)** — a much-depended-on module leaning on a volatile one | **on** | tool-assisted, robust: import graph + contracts |
| **Secondary** | **packaging (REP/CCP/CRP)** — grab-bag packages, things that change together but live apart, fat packages each user only partly needs · **Screaming Architecture** — does the top-level layout reveal the domain or the framework? · **Main Component / composition root** — is infra constructed inside core, or wired at the edge? | opt-in (`--cohesion`, or an interactive "go deeper?") | analyzer judgment + git co-change (CCP) + import-usage (CRP) |
| **Appendix** | **abstractness / Main-Sequence scorecard** (`A`, `D`, zones of Pain/Uselessness) | opt-in (`--metrics`) | tool when present; **explicitly flagged "abstractness is approximate in Python"** |

**Why this split:** cycles (ADP), stability-direction (SDP), and dependency-direction
are *robust* — they are computed from who-imports-whom, which Python handles fine —
and they are where the actionable, high-impact findings live (especially in
AI-generated code, whose #1 architectural sin is exactly a Dependency-Rule
violation). Only the **abstractness** half (SAP / the Main-Sequence chart) is fragile
in Python (duck typing and `Protocol`s defeat "count the abstract classes"), so it is
demoted to an opt-in, caveated appendix — never a finding to refactor toward.

### Tooling posture (tooling-first, graceful fallback)

- Use real graph tools when present, invoked via `uvx` / `npx` (no hard install):
  - **Python:** `grimp` (import graph, exact cycle detection) + `import-linter`
    (Dependency-Rule *contracts*: forbidden imports, layered dependencies).
  - **JS/TS:** `dependency-cruiser` (forbidden rules + cycles); `madge` for cycle
    graphs.
- **Graceful fallback:** when tools are absent, the analyzer reads imports and
  reasons qualitatively (like `solid`/`gof`/`ddd` do today), and the report states
  which mode was used — mirroring Phase 0's existing "detect suite, degrade if
  absent" ethos.

### Leave-behind artifact (the audit becomes a tripwire)

Because the Dependency Rule can be expressed as `import-linter` contracts, the skill
**emits an `importlinter` contract file** (e.g. "the `domain` layer may not import
any web/ORM package") as a committed-on-request artifact — turning a one-time audit
into a repeatable CI guardrail. The metrics cannot give this; the audit can.

### Rubric (`references/principles.md`)

Canonical one-line definitions of each principle (REP/CCP/CRP, ADP/SDP/SAP, the
Dependency Rule, Screaming Architecture, Main Component, Humble Object) as anchors,
plus the parts not baked into any model: the **tier assignment**, **violation
signatures** (AI-code-shaped: `use_cases.py` importing `django.db`; a domain module
constructing its own DB client; an import cycle across packages; a stable core
depending on an experimental module), and the **when-NOT-to-flag** rules (don't
demand boundaries a single-deployable app doesn't need; don't chase Main-Sequence
distance on a codebase without real multi-component granularity; partial boundaries
are legitimate YAGNI — don't flag a missing boundary that isn't yet earned).

### `analyze` flow (audit-first; apply opt-in)

1. **Phase 0 — Inventory & baseline.** Scope the tree, detect the test suite,
   detect graph tooling, create the git-excluded `docs/reports/clean-architecture/`.
2. **Phase 1 — Analyzer** (read-only) → `findings-draft.md`. Runs headline checks;
   runs secondary/appendix only if opted in.
3. **Phase 2 — Reviewer** re-opens the real code for every finding, prunes false
   positives, tiers survivors **Critical/Major/Minor**, cross-references the overlap
   hub, and writes `CLEAN-ARCHITECTURE-REPORT-<date>.md` per the report template.
   Emits the `importlinter` contract draft.
4. **Phase 3 — Decision gate.** Present the summary; most CA fixes are large
   (High-risk architectural moves) and stay advisory, but the mechanical ones (break
   a cycle by moving a class, introduce a port at a boundary) can be applied via the
   shared TDD-backed implementer if the user opts in.

### File map

```
skills/clean-architecture/
  SKILL.md                     # orchestrator: tiers, opt-in flags, tooling, guardrails
  agents/
    analyzer.md                # pointer into shared analyzer role
    reviewer.md                # pointer into shared reviewer role
    implementer.md             # pointer into shared implementer role (opt-in apply)
  references/
    principles.md              # tiered rubric, violation signatures, when-NOT-to
    python.md                  # grimp/import-linter detection + graph how-to
    report-template.md         # report format + importlinter-contract section
evals/clean-architecture-evals.json   # NEW
```

---

## Part 3 — Shared plumbing changes

### Overlap hub (replaces the pairwise map)

Adding a 4th lens would turn the single `solid-gof-overlap.md` into an O(n²)
pairwise-map problem. Instead:

- **Migrate `docs/solid-gof-overlap.md` → `docs/lens-overlap.md`** — one hub every
  reviewer reads. Keep the existing SOLID↔GoF table; add `clean-architecture` rows:

  | CA finding | Overlaps | Reconciliation |
  |---|---|---|
  | dependency-direction violation | `ddd` (missing port / DIP), `solid` (DIP) | whoever runs files it; `ddd` frames as "missing port on aggregate X", CA as "boundary violation: use-case imports Django" — **one** change |
  | cycle (ADP) | `solid` (DIP to invert an edge) | CA files the cycle; DIP is the fix mechanism |
  | composition-root / infra-in-core | `gof` (Abstract Factory at boundary), `clean-code` (separate construction from use) | CA files it; GoF/clean-code are the fix idioms |
  | Humble Object at a boundary | `gof` (the pattern itself) | hand off to `gof` |

- Update `solid` and `gof` SKILLs + reviewer references to point at
  `docs/lens-overlap.md`.

### Reports consolidated under `docs/` (git-excluded)

- **Change `refactor-workflow.md` Phase 0** so every lens creates and writes to
  **`docs/reports/<lens>/`** (holding `findings-draft.md` + the final report),
  **git-excluded by default** via `.git/info/exclude` — preserving today's
  "ephemeral working artifact" behavior; the user can still choose to commit a
  report as a living doc at the end.
- Replaces the scattered top-level `solid-reports/`, `gof-reports/`, `ddd-reports/`.
- Update the hardcoded paths in `solid`, `gof`, `ddd` SKILLs + their
  `report-template.md`s. **`ddd` keeps `docs/domain/`** for its reverse-engineered
  model proposal (that is a deliverable, not a report); only its *refactor report*
  moves to `docs/reports/ddd/`.
- Housekeeping: the plugin's own root `solid-reports/` (from a prior self-run)
  moves/cleans up under the new convention.

### Manifests

- Register `clean-architecture` in `.claude-plugin/plugin.json` (description +
  `clean-architecture` / `dependency-rule` / `component-principles` keywords) and
  `.claude-plugin/marketplace.json` (plugin description), and bump the plugin
  version.

---

## Interplay contract (explicit, stable)

- **`clean-code` → everyone:** the standard is a *substrate* — the shared
  implementer role and `tdd` link it; nothing copies it. `/clean-code` standalone
  review defers structural findings up-ladder (SRP → `solid`, patterns → `gof`).
- **`clean-architecture` → `ddd`:** the carve (structure-soundness vs
  domain-modelling). Shared findings reconciled at the hub; neither auto-runs the
  other.
- **`clean-architecture` → `solid` / `gof`:** advisory at the seams (DIP is the fix
  for a cycle; Abstract Factory / Humble Object are boundary idioms), never invoked.
- **`clean-architecture` → `tdd`:** opt-in apply of mechanical findings goes through
  the shared TDD refactor job, one rec at a time, suite green after each.
- **Both → `ship`:** the offered commit + PR exit per `docs/git-convention.md`.
- **Both → memory brain:** end-of-run **offer** (never silent) to capture durable
  decisions (e.g. an agreed Dependency-Rule contract, a chosen package boundary).

## How SOLID/DIP shaped this design

- **Single responsibility per skill:** `clean-code` owns line-level craft;
  `clean-architecture` owns the component graph; neither absorbs the other's
  altitude, and both defer to `solid`/`gof`/`ddd` at the seams. Each has one reason
  to change.
- **Open/closed:** a new language for `clean-architecture` (a TS graph adapter) or a
  new violation signature is added as a file/section, not by editing tested
  orchestration. The overlap **hub** makes adding a future lens an additive change,
  not an O(n²) edit.
- **DIP / substrate-as-abstraction:** `clean-code`'s standard is the stable
  abstraction that volatile consumers (the implementer role, `tdd`) depend on —
  inverting the old arrangement where cleanliness was trapped behind an invocation.

## Durable artifacts

- **Committed in target project (on request):** the `clean-architecture`
  `importlinter` contract — the audit's leave-behind CI tripwire.
- **Git-excluded report dirs:** `docs/reports/<lens>/` (findings-draft + final
  report) — ephemeral by default.
- **Plugin-repo docs:** `docs/clean-code-standard.md` (new canonical standard) and
  `docs/lens-overlap.md` (migrated hub) are committed plugin source.
- **Memory brain:** offered capture of durable decisions at end of run.

## Suggested build order (for the implementation plan)

This spec spans two skills plus shared plumbing; it decomposes into four stages,
each keeping the existing test/eval suites green so the plumbing edits to `solid`
/ `gof` / `ddd` are guarded:

1. **Foundation (shared plumbing first).** `docs/clean-code-standard.md` (canonical
   standard); migrate `solid-gof-overlap.md` → `docs/lens-overlap.md`; change
   `refactor-workflow.md` Phase 0 to `docs/reports/<lens>/` (git-excluded); update
   the hardcoded report paths + overlap references in `solid` / `gof` / `ddd`. Both
   new skills depend on these.
2. **`clean-code` rebuild.** Thin skill + agents + review report-template; wire the
   consumers (`refactor-agents/implementer.md`, `tdd` refactor-jobs + build) to link
   the standard; evals.
3. **`clean-architecture` lens.** SKILL + agents + `principles.md` + `python.md` +
   report-template + `importlinter` leave-behind; add the CA rows to the hub; evals.
4. **Register + housekeeping.** Manifests (`plugin.json`, `marketplace.json`) +
   version bumps; move the plugin's own root `solid-reports/` under the new
   convention.

## Out of scope (YAGNI)

- **Approach B — umbrella `/architecture` dispatcher** (run all lenses, one
  de-duped report). Parked as an explicit **phase 2**, layered on top of this once
  A proves out.
- **`clean-architecture` greenfield build mode** — permanently out; that is `ddd`.
- **Metrics as a default headline** — the abstractness/Main-Sequence scorecard is
  opt-in appendix only.
- **Deep non-Python `clean-architecture` support** — agnostic fallback covers other
  languages; a TS graph adapter (`dependency-cruiser`) can be deepened later.
- **Auto-apply of large architectural moves** — CA fixes are advisory by default;
  only mechanical, low-risk fixes are opt-in appliable.

## Deferred enhancements (track as issues)

- TypeScript reference for `clean-architecture` (`dependency-cruiser`/`madge`
  detection + idioms), mirroring `solid`'s `typescript.md`.
- Phase-2 umbrella dispatcher (Approach B).
- Trend mode for the metrics appendix (track `D` across runs) — only if the metrics
  prove useful in practice.

## Resolved decisions (from brainstorming)

- Approach **A**, with **B** parked as phase 2.
- `clean-code` = **hybrid substrate** (canonical standard + thin two-gear review).
- `clean-architecture` = **audit-only lens**, tiered, **headline-only by default**;
  secondary + appendix are **opt-in**.
- Tooling: **tooling-first, graceful fallback**; robust checks headline, abstractness
  appendix-only.
- Full name **`/clean-architecture`** (no short alias).
- Reports under **`docs/reports/<lens>/`**, **git-excluded** by default.
