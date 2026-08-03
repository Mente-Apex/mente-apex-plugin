---
name: ddd
description: >-
  Domain-Driven Design for object-oriented codebases, with deep idiom support for
  Python and TypeScript, in two modes. DESIGN mode
  models a new domain (adaptive: inference-first, or facilitated event storming
  for tangled domains), gates the ubiquitous language + bounded contexts +
  aggregates for human sign-off, then drives the tdd skill to build it
  layer-by-layer innermost-out — domain core (entities, value objects,
  aggregates) → application services → adapters behind ports → web last — with
  dependencies pointing strictly inward. ANALYZE mode reviews existing/legacy
  code through a DDD lens (anemic domain model, logic stranded in controllers or
  ORM models, missing ports, DIP violations), producing a tiered
  Critical/Major/Minor "refactor toward DDD" report plus a reverse-engineered
  docs/domain proposal — report-only, no code changes. Use for "/ddd",
  domain-driven design, bounded context, aggregate, ubiquitous language, entity
  vs value object, anemic domain model, hexagonal / ports and adapters,
  repository / unit of work.
user-invocable: true
metadata:
  version: "0.1.1"
---

# ddd — Domain-Driven Design modelling, build & analysis

DDD, done as two jobs that share one vocabulary. `design` models a domain and
builds it test-first, innermost layer out, with a hard gate on the decisions
that are ruinous to change later. `analyze` reads existing code through the same
lens and writes a plan — it never edits code. This skill owns **architecture,
layer ordering, and dependency direction**; it delegates the red-green cycle to
`tdd` and treats `solid`/`gof` as advisory.

**Progressive disclosure.** Load only what the domain warrants:
`references/ddd-core.md` always; `references/strategic.md` only when more than
one bounded context is in play; `references/<language>.md` for the detected
language's idioms (ships `python.md`, `typescript.md`; list `references/` for the
current set); `references/report-template.md` + `agents/*` only in `analyze` mode.

## Invocation

`/ddd [design|analyze] [scope]`

- `scope` is a path, a diff, or a range (default: repo root).
- `design` — model and build a new domain (touches code, via `tdd`).
- `analyze` — review existing code, report only (no code changes).
- **Bare `/ddd`**: inspect the target path — empty/thin → propose `design`;
  substantial domain code present → propose `analyze`; ambiguous → ask. The
  explicit arg always wins.

The user may pre-authorize in the same breath ("model looks right, build it") —
that counts as passing the corresponding gate; don't re-ask what was already
answered.

## Mode: design

Read `references/ddd-core.md` first. Load `references/strategic.md` only if the
brief implies more than one bounded context.

### 1. Precheck & branch
If the *product requirements* (the "what") are fuzzy, recommend
`superpowers:brainstorming` first — this skill models a domain, it does not
discover the product. Then, per `../../docs/git-convention.md`, open a working
branch `ddd/<short-slug>` before any file is written (this mode builds code).

### 2. Model (adaptive)
Gauge domain complexity from the brief:
- **Simple/known → inference-first.** Draft the model — ubiquitous-language
  glossary, domain events, aggregates + the invariant each guards, entities vs
  value objects, ports — then walk the user through it section by section. Fall
  back to targeted questions only where the brief is silent.
- **Novel/tangled → offer facilitated event storming** (script in
  `references/strategic.md`): elicit domain events, then commands, then
  aggregates, one step at a time, live.
The user can override the chosen path either way.

### 3. Persist the model
Write, into the target project (committed, living):
- `docs/domain/GLOSSARY.md` — ubiquitous language.
- `docs/domain/model.md` — aggregates + invariants, domain events, entities/VOs,
  ports.
- `docs/domain/context-map.md` — only if more than one bounded context.

### 4. 🚦 MODELING GATE (hard stop — human sign-off)
Before a single test or line of production code, present the three load-bearing
decisions for explicit approval:
- **Ubiquitous language** — glossary terms and definitions.
- **Bounded context(s)** — name(s) and boundaries (+ context map if >1).
- **Aggregates** — each aggregate root, its members, and the **invariant it
  exists to guard**.
Do not proceed until the user approves. They may approve as-is, edit
terms/boundaries/aggregates, or send it back to re-model. A pre-authorization
covering these counts as approval. *Why these three:* they are cheap to change on
paper and a rewrite once code depends on them — the language names every class,
the boundaries decide scope, and the invariant is the consistency rule the whole
repository + unit-of-work layer is built to protect.

### 5. Build layer-by-layer via tdd (programmatic), innermost first
Hand each layer to `tdd` in **programmatic mode** with acceptance criteria,
explicit scope, and integration points. `tdd` writes tests+code; you own the
ordering and the dependency direction. `tdd` does **not** commit — this flow owns
the branch. Order:
1. **Domain core** — entities, value objects, aggregates. Pure; no
   infrastructure; no mocks (this is `tdd`'s existing `references/ddd_testing.md`
   contract).
2. **Application services** — orchestrate aggregates through **ports** defined
   here as abstractions, *before* any adapter exists.
3. **Adapters** — repository / unit-of-work impls, API clients, message
   publishers — each behind a port defined inward.
4. **Web / HTTP layer last, and only if needed.**

After **each** layer, verify the DDD boundary yourself (see next section), then
*recommend* (never auto-run) `/solid` for a deep audit and `/gof` when a specific
pattern earns its place (factory for aggregate creation, strategy for a domain
policy, adapter/ACL for a third party).

### 6. Per-layer boundary check (inline DIP)
- **Dependency direction is inward only** — domain imports nothing from
  application/adapters/web; application imports domain + ports only; adapters
  depend inward on ports.
- **No concretion constructed inside the domain** — no database clients, HTTP
  sessions, or clocks instantiated in domain/application code; they arrive
  through constructors/parameters and are substitutable at the port seam.
If either fails, fix the boundary before starting the next layer — a broken
boundary compounds.

### 7. Finish
Full suite green, then per the git convention **offer** (never auto) commit + PR
via `mente-apex:ship`. Finally, **offer** (never silently) to capture durable
domain decisions — bounded-context names, core invariants, key ubiquitous-
language terms — wherever the project persists knowledge: the Mente Apex brain via
the `/memory` protocol when present, else a short `docs/domain/` note in the repo.
Never assume an external memory system exists.

## Mode: analyze (report-only)

Mirrors `solid`'s pipeline minus the apply phase. **This mode's own run never edits
code** — that constrains the run, not the finding: a finding merged by the code-quality
umbrella (or explicitly opted into by a user) is applicable through the shared engine.

### Phase 0 — Inventory & baseline
Scope the target tree (skip vendored/generated dirs). Detect and record the test
command; note whether the suite is green (context for later refactors — this mode
runs none). Create `docs/reports/ddd/` in the target project and add it to
`.gitignore` if the repo doesn't already ignore it.

### Phase 1 — Analyzer
Spawn the analyzer (Agent tool, `general-purpose`), telling it to read
`agents/analyzer.md` + `references/ddd-core.md` (and `strategic.md` if multiple
contexts appear). It writes `docs/reports/ddd/draft-findings.md` — read-only over the code it audits,
not over its own draft.

### Phase 2 — Reviewer
Spawn the reviewer with the draft path, `agents/reviewer.md`,
`references/ddd-core.md`, and `references/report-template.md`. It re-verifies
every finding against the real code, prunes false positives, tiers survivors
Critical/Major/Minor, cross-references the SOLID lens, and writes
`docs/reports/ddd/DDD-REPORT-<YYYY-MM-DD>.md` using the template **exactly**. It also
**reverse-engineers the implicit model** into proposed `docs/domain/` artifacts
(`GLOSSARY.md`, `model.md`, `context-map.md` if >1 context) — marked as
reverse-engineered proposals.

### Phase 3 — 🚦 MODEL REVIEW GATE (keep or discard)
Present the proposed ubiquitous language + bounded context(s) + aggregates for
human review (the same three decisions gated in `design`). On approval they are
**kept** (and can seed a later `/ddd design`); if decided against they are
**discarded** (delete the files). Nothing here is auto-committed.

### Phase 4 — Stop
Present a compact summary: findings by tier, top 2–3 wins, anything High-impact.
**No code changes in this run** — findings remain applicable through the shared engine
when merged by the umbrella or opted into directly. Offer next steps: `/ddd design` on
a new context, hand specific findings to `/tdd`, or `/solid` for the pure-SOLID cut.
**Offer** to
capture key findings (and any kept domain decisions) wherever the project keeps
durable knowledge — the memory brain when present, else a short repo `docs/domain/` note.

## Interplay contract (stable)

- **→ `tdd`**: programmatic mode; you hand it each layer's acceptance criteria +
  scope + integration points. It owns red-green-refactor; you own architecture,
  layer order, dependency direction. It does not commit in this handoff.
- **→ `solid` / `gof`**: advisory only — recommended at layer boundaries, never
  invoked. You do the inline DIP/dependency-direction check yourself.
- **→ `brainstorming`**: recommended upstream when the product "what" is fuzzy.
- **→ `ship`**: the offered commit+PR exit.
- **`tdd`'s `references/ddd_testing.md`** already encodes "test the domain through
  its ports, no mocks" — rely on it; do not duplicate it.

## Guardrails

- **`analyze`'s own run never edits code.** Its only writes are the report, the draft,
  and the *proposed* `docs/domain/` (kept or discarded by the user) — that constrains
  the run, not the finding: a finding merged by the umbrella (or opted into) is
  applicable through the shared engine.
- **The modeling gate is a hard stop.** No test, no production code, before
  ubiquitous language + bounded contexts + aggregates are approved.
- **Judgment, not ceremony.** Follow the when-NOT-to rules in
  `references/ddd-core.md`: no value object where a primitive is fine, no unit of
  work when a single repository call is the whole transaction, keep aggregates
  small, don't split one context into ceremony.
- **Out of scope by default (opt-in only):** CQRS, Event Sourcing, Sagas —
  name them, price them, never reach for them silently.

## File map

- `references/ddd-core.md` — tactical spine, layering, DIP, when-NOT-to. Always
  read.
- `references/strategic.md` — event storming, subdomain classification, context-
  mapping catalogue. Load only for >1-context domains.
- `references/<language>.md` — the detected language's tactical idioms (value
  objects, ports, repository/UoW). Ships `python.md` (frozen dataclasses,
  `Protocol` ports, SQLAlchemy) and `typescript.md` (readonly VOs, branded-type
  ids, `interface` ports, async Prisma repos); list `references/` for the current
  set. New languages drop in here.
- `references/report-template.md` — exact `analyze` report format.
- `agents/analyzer.md`, `agents/reviewer.md` — the two `analyze` subagent roles.
- `../../docs/git-convention.md` — working-branch + offer-never-auto-publish.
