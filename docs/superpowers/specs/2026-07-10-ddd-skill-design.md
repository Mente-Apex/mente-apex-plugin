# Design — `ddd` skill (Domain-Driven Design analysis & guided build)

**Date:** 2026-07-10
**Status:** Approved (brainstorming complete, ready for implementation plan)
**Plugin:** mente-apex

## Purpose

A user-invocable `/ddd` skill that either **designs and builds a new domain**
with DDD from the first line, or **analyzes existing (legacy) code** through a
DDD lens and produces a refactor-toward-DDD plan. It models the core business
problem with entities and value objects first, expands outward to application
services, then to adapters behind ports, with the web/HTTP layer last and only
if needed. Dependencies point strictly inward (hexagonal / ports-and-adapters),
which makes the design an enforcement of the standing dependency-inversion
engineering standard rather than a later refactor.

It is deliberately not a monolith: it owns **architecture, layer ordering, and
dependency direction**, and delegates the actual test-first construction to the
existing `tdd` skill. `solid` and `gof` are advisory. This keeps each skill to
one reason to change.

## Skill identity & shape

- **Name:** `ddd`, user-invocable (`/ddd`), version `0.1.0`, added to the plugin
  manifest alongside `solid` / `tdd` / `gof`.
- **One skill, two modes:**

  | Mode | Trigger | What it does | Touches code? |
  |------|---------|--------------|---------------|
  | **design** | `/ddd design`, or new/empty target | Model the domain (adaptive), gate the model, drive `tdd` to build layer-by-layer innermost-out | Yes (via `tdd`) |
  | **analyze** | `/ddd analyze`, or target has substantial code | Two-stage analyzer→reviewer pass → tiered "refactor toward DDD" report + target-architecture sketch | **No** — report only |

- **Mode detection for bare `/ddd`:** inspect the target path — empty/thin →
  propose `design`; substantial domain code → propose `analyze`; ambiguous →
  ask. The explicit arg always wins.
- **Trigger surface:** `/ddd`, plus phrases like *domain-driven design, bounded
  context, aggregate, ubiquitous language, entity vs value object, anemic domain
  model, hexagonal / ports and adapters, repository / unit of work*.

## DDD depth (knowledge base)

Full strategic + tactical, split by **progressive disclosure** so a simple
single-context app never drowns in ceremony. The orchestrator loads only what
the domain warrants.

- `references/ddd-core.md` (agnostic) — the tactical spine + layering + DIP
  rules: entities vs value objects; aggregates as **consistency boundaries** +
  aggregate roots; domain events; domain services; ports; **repository** (one
  per aggregate root); **unit of work** (transactional consistency across a
  change); the four-layer dependency rule (domain → application → adapters →
  web, dependencies point **inward only**).
- `references/strategic.md` (agnostic, loaded only when a >1-context smell
  appears) — event-storming facilitation script; context mapping
  (upstream/downstream, conformist, anti-corruption layer); subdomain
  classification (core / supporting / generic); anti-corruption layers.
- `references/python.md` — concrete idioms: frozen `@dataclass` value objects;
  `typing.Protocol` for ports (structural, keeps the domain import-clean);
  ABC-vs-Protocol guidance; SQLAlchemy repository + unit-of-work
  implementations; `raise`-based invariant enforcement.
- Other languages → fall back to `ddd-core.md`.

**When-NOT-to discipline** is baked in, mirroring `solid`'s `principles.md`:
don't make a value object where a primitive is fine; don't split one bounded
context into ceremony; don't add a unit of work when a single repository call is
the whole transaction; keep aggregates small.

## `design` mode flow

1. **Precheck.** If the *what* (product requirements) is fuzzy, recommend
   `superpowers:brainstorming` first — `ddd` models a domain, it does not
   discover the product. Then open a working branch `ddd/<slug>` per the plugin
   git-convention, since this mode builds code.
2. **Model (adaptive).** Gauge complexity from the brief. Simple/known →
   **inference-first**: draft glossary + domain events + aggregates &
   invariants + entities/VOs + ports, then review section-by-section.
   Novel/tangled → offer **facilitated event storming**. The user can override
   either way.
3. **Persist the model** to the target project (committed, living):
   - `docs/domain/GLOSSARY.md` — ubiquitous language.
   - `docs/domain/model.md` — aggregates, events, entities/VOs, ports.
   - `docs/domain/context-map.md` — only if more than one bounded context.
4. **🚦 MODELING GATE (hard stop — human sign-off required).** Before a single
   test or line of production code, present the three load-bearing model
   decisions for explicit approval:
   - **Ubiquitous language** — glossary terms and definitions.
   - **Bounded context(s)** — context name(s) and boundaries (+ context map if
     >1).
   - **Aggregates** — each aggregate root, its members, and the **invariant it
     exists to guard**.

   The build does **not** proceed until the user approves. Approve as-is, edit
   terms/boundaries/aggregates, or send back to re-model. Analogous to `solid`'s
   Phase 3 decision gate — the human is the editor of the model before it
   becomes code. A pre-authorization in the same breath ("model looks right,
   build it") counts as passing the gate.

   *Why these three:* they are cheap to change on paper and ruinously expensive
   once code depends on them. Ubiquitous language propagates into every class
   name; bounded-context boundaries decide what is even in scope; an aggregate's
   invariant *is* the consistency rule the whole persistence layer (repository +
   unit of work) is built to protect. Getting them wrong is a rewrite, not a
   refactor.

5. **Build layer-by-layer via `tdd` (programmatic mode), innermost first:**
   - **Domain core** — entities, value objects, aggregates. Pure, no
     infrastructure, no mocks (exactly `tdd`'s existing `ddd_testing.md`
     contract).
   - **Application services** — orchestrate aggregates through **ports**; ports
     are defined here as abstractions *before* any adapter exists.
   - **Adapters** — repository / unit-of-work impls, API clients, message
     publishers — each behind a port defined inward.
   - **Web / HTTP layer last, and only if needed.**
   - After **each** layer: `ddd` asserts **dependency direction** (inward only)
     and **no concretion constructed inside the domain** (strict DIP), then
     *recommends* `/solid` for a deep audit and `/gof` when a specific pattern
     earns its place (factory for aggregate creation, strategy for a domain
     policy, adapter/ACL for a third party). Suggests — never auto-runs.
6. **Finish.** Full suite green, then per git-convention **offer** (never auto)
   commit + PR via `/ship`, and **offer** to capture durable domain decisions to
   the memory brain.

## `analyze` mode flow (report-only)

Mirrors `solid`'s pipeline, minus the apply phase.

1. **Phase 0 — Inventory & baseline.** Scope the tree, detect the test suite,
   create the gitignored `ddd-reports/` dir.
2. **Phase 1 — Analyzer** (subagent, read-only, `agents/analyzer.md`) →
   `ddd-reports/findings-draft.md`. DDD-specific violation signatures: anemic
   domain model (entities that are bags of getters/setters, logic living in
   services); business logic stranded in HTTP controllers or ORM models;
   **missing ports** (domain calling the DB/HTTP directly = DIP violation); fat
   repositories doing domain logic; aggregate boundaries that guard no
   invariant; transaction scripts masquerading as services; leaked ubiquitous
   language (code nouns ≠ business nouns).
3. **Phase 2 — Reviewer** (subagent, `agents/reviewer.md`) re-opens the real
   code for every finding, prunes false positives, tiers survivors
   **Critical/Major/Minor**, cross-references the SOLID lens, and writes
   `ddd-reports/DDD-REFACTOR-<date>.md` using `references/report-template.md` —
   tiered findings **plus a target DDD architecture sketch** (the hexagon this
   code is trying to be).
4. **Reverse-engineer the implicit model.** From the legacy code, reconstruct
   the ubiquitous language, bounded context(s), and aggregates the code is
   *trying* to express, and write them as **proposed** `docs/domain/` artifacts
   (`GLOSSARY.md`, `model.md`, `context-map.md` if >1 context) — the same
   artifacts `design` mode produces, but marked as reverse-engineered proposals.
5. **🚦 MODEL REVIEW GATE (keep or discard).** Present the proposed
   ubiquitous language + bounded context(s) + aggregates — the same three
   load-bearing decisions gated in `design` mode — for human review. On
   approval they are **kept** (and can seed a later `/ddd design` pass on a new
   context); if decided against they are **discarded** (deleted, not committed).
   Nothing here is auto-committed — analyze mode never touches code and never
   silently adds files that outlive the user's decision.
6. **Stop.** Present a compact summary. **No code changes.** Next steps offered:
   run `/ddd design` on a new bounded context, hand specific findings to
   `/tdd`, or run `/solid` for the pure-SOLID cut. End-of-run **offer** to
   capture key findings (and any kept domain decisions) to the brain.

Two subagents (analyzer + reviewer), no implementer — this mode never edits
code. This is the one deliberate deviation from a literal `solid` clone,
justified by the "plan only" decision.

## File map

```
skills/ddd/
  SKILL.md                     # orchestrator: modes, flow, gate, guardrails
  references/
    ddd-core.md                # agnostic tactical + layering + DIP + when-NOT-to
    strategic.md               # event storming, context maps, ACL (on demand)
    python.md                  # VOs, Protocol ports, SA repository/UoW idioms
    report-template.md         # exact analyze-mode report format (IDs, tiers)
  agents/
    analyzer.md                # analyze mode, read-only
    reviewer.md                # analyze mode, verifies + writes report
```

## Interplay contract (explicit, stable)

- **→ `tdd`**: called in *programmatic mode*, handed each layer's acceptance
  criteria + scope + integration points. `tdd` owns red-green-refactor; `ddd`
  owns architecture, layer order, dependency direction. `ddd` does **not**
  commit in this handoff — the outer `ddd` flow owns the branch.
- **→ `solid` / `gof`**: advisory only — recommended at layer boundaries, never
  invoked. `ddd` does its own inline DIP / dependency-direction check.
- **→ `brainstorming`**: recommended upstream when product requirements are
  fuzzy.
- **→ `ship`**: the offered commit + PR exit.
- **`tdd`'s existing `references/ddd_testing.md`** already encodes "test the
  domain through its ports, no mocks" — `ddd` relies on it rather than
  duplicating it. No change to `tdd` required.

## Durable artifacts

- **Committed in target project:** `docs/domain/GLOSSARY.md`, `model.md`,
  `context-map.md` (design mode) — ubiquitous language ships with the code.
- **Proposed `docs/domain/` (analyze mode):** the reverse-engineered glossary /
  model / context-map are written for review at the model gate, then **kept**
  (on approval) or **discarded** (if decided against). Never auto-committed —
  they outlive the run only by explicit user choice.
- **Gitignored report dir:** `ddd-reports/DDD-REFACTOR-<date>.md` and
  `findings-draft.md` (analyze mode) — ephemeral, like `solid-reports/`.
- **Memory brain:** end-of-run **offer** (never silent) to capture durable
  domain decisions — bounded-context names, core invariants, key ubiquitous-
  language terms — via the memory protocol, mirroring `tdd`'s `learning.md`.

## How DIP shaped this design

- **Abstractions that exist:** *ports* (Protocols/ABCs) are the seams — the
  domain and application layers depend only on them, never on concretions.
  Ports are derived from aggregate boundaries, which is why the modeling gate
  approves aggregates *before* any adapter exists to tempt a shortcut.
- **Where dependencies are injected:** adapters (repository, unit of work, API
  clients) are constructed at the composition root (the web/entry layer, built
  last) and injected inward into application services through constructors —
  never instantiated inside the domain. Every dependency is substitutable and
  mockable at the port seam, which is exactly what lets the domain-core tests
  run with no mocks.
- **Skill-internal SRP:** the orchestrator owns architecture; `tdd` owns the
  red-green cycle; analyzer and reviewer are separate read-only roles;
  per-language idioms live in their own reference. Each has one reason to
  change. Extension (a new language adapter, a new violation signature) is by
  adding a file/section, not editing tested orchestration — open/closed.

## Out of scope (YAGNI)

- Legacy **guided apply** — analyze mode is report-only by decision.
- Non-Python concrete idiom adapters — agnostic core covers them; a TypeScript
  adapter can be added later if wanted.
- End-to-end / full-stack test generation — remains `tdd`'s call per layer.
