---
name: ddd
description: >-
  Domain-Driven Design for object-oriented codebases, with deep idiom support for
  Python, TypeScript, and Java, in two modes. DESIGN mode
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
  repository / unit of work, specification pattern, entity identity strategy,
  and — opt-in only, never by default — CQRS, event sourcing, sagas / process
  managers.
user-invocable: true
metadata:
  version: "0.2.1"
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
language's idioms (ships `python.md`, `typescript.md`, and `java.md`; list
`references/` for the current set); `references/report-template.md` + `agents/*`
only in `analyze` mode; `references/cqrs.md`, `references/event-sourcing.md`,
`references/sagas.md` **only once a trigger for that discipline has fired** —
either the user opting in or you being about to raise it (design step 3), or the
reviewer filing a finding that names it. Never as background reading, or the
skill starts finding reasons to recommend them.

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

### 3. 🔀 Opt-in triage — CQRS, event sourcing, sagas
Do this **before** the model is persisted and gated: each of these rewrites the
ports and (for event sourcing) the aggregates the gate is about to sign off, so
deciding after the gate means re-opening it.

- **Default is no.** The default build is one model, state-based persistence, and
  domain events. Say nothing about these unless a trigger fires.
- **Triggers.** An explicit request (`/ddd design … with cqrs`, "event-sourced",
  "we need a saga"), or the interview surfacing the specific need each answers:
  sharply divergent read/write shapes (CQRS), hard audit/temporal requirements
  (event sourcing), a multi-aggregate process with compensating steps (sagas).
- **Try the cheap answer first** — these resolve most triggers without any of the
  three, and you do not need the reference to offer them:
  - "we need an audit trail" → an append-only audit table written by a domain-event
    handler, *not* event sourcing.
  - "reads are slow" → measure, then an index or a denormalized view, *not* CQRS.
  - "these two aggregates must stay in step" → re-examine the boundary; if they
    always change together they were one aggregate, *not* a saga.
- **Load the reference to price it, then decide.** Reading `references/cqrs.md`,
  `references/event-sourcing.md`, or `references/sagas.md` is authorized as soon as
  a trigger fires — you cannot state a cost list you have not read. What stays
  forbidden is *adopting* one without the user's explicit yes, and reading them as
  background when no trigger fired.
- **Price it before recommending it.** When *you* raise one, state its cost list
  from the reference **first**, then the benefit, then let the user decide.
  Adopting one silently is a defect, not a shortcut.
- **Build order shifts** only on a yes: CQRS adds query ports + projection
  handlers *after* the write side is complete; event sourcing replaces the
  repository port with an event-store port and requires a written versioning
  strategy before the first test; a saga is an application-layer coordinator over
  dispatch/subscribe ports, built after the aggregates it coordinates.

### 4. Persist the model
Write, into the target project (committed, living):
- `docs/domain/GLOSSARY.md` — ubiquitous language.
- `docs/domain/model.md` — aggregates + invariants, domain events, entities/VOs,
  ports, the identity strategy, and the opt-in decision from step 3 **including a
  "no"**, so the next run doesn't re-litigate it.
- `docs/domain/context-map.md` — only if more than one bounded context.

### 5. 🚦 MODELING GATE (hard stop — human sign-off)
Before a single test or line of production code, present the load-bearing
decisions for explicit approval:
- **Ubiquitous language** — glossary terms and definitions.
- **Bounded context(s)** — name(s) and boundaries (+ context map if >1).
- **Aggregates** — each aggregate root, its members, and the **invariant it
  exists to guard**.
- **Entity identity generation** — application- vs database-generated, per
  "Entity identity" in `ddd-core.md`. Cheap here, and it decides the repository
  port's shape (`add(order)` vs `add(order) -> OrderId`), so it cannot wait for
  the adapter layer.
- **Any opt-in from step 3**, with the cost the user accepted.
Do not proceed until the user approves. They may approve as-is, edit
terms/boundaries/aggregates, or send it back to re-model. A pre-authorization
covering these counts as approval. *Why these:* they are cheap to change on
paper and a rewrite once code depends on them — the language names every class,
the boundaries decide scope, the invariant is the consistency rule the whole
repository + unit-of-work layer is built to protect, and identity generation
reaches the ports. If a later step changes one of them, re-present this gate
rather than editing an approved artifact silently.

### 6. Build layer-by-layer via tdd (programmatic), innermost first
Hand each layer to `tdd` in **programmatic mode** with acceptance criteria,
explicit scope, and integration points. `tdd` writes tests+code; you own the
ordering and the dependency direction. `tdd` does **not** commit — this flow owns
the branch.

**Choose the directory scaffold first**, per "Modules" in `ddd-core.md`:
layer-first (`domain/ application/ adapters/`) for a single bounded context,
concept-first (`billing/{domain,…}`, `catalog/{…}`) once there is more than one —
top-level names come from the ubiquitous language either way. Then, in order:
1. **Domain core** — entities, value objects, aggregates. Pure; no
   infrastructure; no mocks (this is `tdd`'s existing `references/ddd_testing.md`
   contract).
2. **Application services** — orchestrate aggregates through **ports** defined
   here as abstractions, *before* any adapter exists.
3. **Adapters** — repository / unit-of-work impls, API clients, message
   publishers — each behind a port defined inward.
4. **Web / HTTP layer last, and only if needed.**

After **each** layer, verify the DDD boundary yourself (see next section). Aim
`tdd`'s refactor step at "Supple Design" in `ddd-core.md` — intention-revealing
names, side-effect-free queries split from mutating commands, invariants stated
as assertions — that is what the refactor half of red-green-refactor is *for* in
a domain layer. Then *recommend* (never auto-run) `/solid` for a deep audit and
`/gof` when a specific pattern earns its place (factory for aggregate creation,
strategy for a domain policy, adapter/ACL for a third party).

### 7. Per-layer boundary check (inline DIP)
- **Dependency direction is inward only** — domain imports nothing from
  application/adapters/web; application imports domain + ports only; adapters
  depend inward on ports.
- **No concretion constructed inside the domain** — no database clients, HTTP
  sessions, or clocks instantiated in domain/application code; they arrive
  through constructors/parameters and are substitutable at the port seam.
If either fails, fix the boundary before starting the next layer — a broken
boundary compounds.

### 8. Finish
Full suite green, then per the git convention **offer** (never auto) commit + PR
via `mente-apex:ship`. Finally, **offer** (never silently) to capture durable
domain decisions — bounded-context names, core invariants, key ubiquitous-
language terms — wherever the project persists knowledge: the Mente Apex brain via
the `/mente` skill when present, else a short `docs/domain/` note in the repo.
Never assume an external memory system exists.

## Mode: analyze (report-only)

Follows [../../docs/refactor-workflow.md](../../docs/refactor-workflow.md)
Phases 0–2 verbatim — including the structural-graph detection + verdict, the
test-suite single run, the stale-draft pre-clear, and the git-exclude via
`.git/info/exclude` for `docs/reports/ddd/`. Its lens is
`references/ddd-core.md` (+ `references/strategic.md` for >1-context
domains) + `references/report-template.md`, with `references/<language>.md`
loaded for each language Phase 0 detects, per the detect-and-load convention.
**This mode's own run never edits code** — that constrains the run, not the
finding: a finding merged by the code-quality umbrella (or explicitly opted
into by a user) is applicable through the shared engine.

### Phase 1 — Analyzer
Spawn the analyzer (Agent tool, `general-purpose`) per the shared Phase 1,
telling it to read `agents/analyzer.md` — ddd's own analyzer role, not the
shared `docs/refactor-agents/analyzer.md` — plus `references/ddd-core.md`
(and `strategic.md` if multiple contexts appear) and, per the detect-and-load
convention, `references/<language>.md` for each detected language. It writes
`docs/reports/ddd/draft-findings.md` — read-only over the code it audits, not
over its own draft.

### Phase 2 — Reviewer
Spawn the reviewer per the shared Phase 2, with the draft path,
`agents/reviewer.md` (again ddd's own role), `references/ddd-core.md`,
`references/report-template.md`, any detected `references/<language>.md`,
and [../../docs/lens-overlap.md](../../docs/lens-overlap.md). It re-verifies
every finding against the real code, prunes false positives,
tiers survivors Critical/Major/Minor, and cross-references
[../../docs/lens-overlap.md](../../docs/lens-overlap.md) — both the SOLID
overlap and the `clean-architecture` carve (hub, clean-architecture ↔ the
others): ddd asks *"is the domain modelled well?"*, clean-architecture asks
*"is the dependency structure sound, regardless of domain richness?"* — a
codebase can pass one and fail the other, so name the other lens's finding
rather than duplicate it. It writes
`docs/reports/ddd/DDD-REPORT-<YYYY-MM-DD>.md` using the template **exactly**;
once it parses, the orchestrator reaps the draft per the shared Phase 2. It also **reverse-engineers the
implicit model** into proposed `docs/domain/` artifacts (`GLOSSARY.md`,
`model.md`, `context-map.md` if >1 context) — marked as reverse-engineered
proposals and written alongside (never over) any pre-existing `docs/domain/`
files from an earlier `design` or `analyze` run (`agents/reviewer.md`).

### 🚦 MODEL REVIEW GATE (keep or discard)
Present the proposed ubiquitous language + bounded context(s) + aggregates for
human review (the same three decisions gated in `design`). On approval they are
**kept** (and can seed a later `/ddd design`); if decided against they are
**discarded** (delete the proposal files). Nothing here is auto-committed.
**Overwrite risk:** if `docs/domain/` already held real files from an earlier
run, the proposal was written beside them, not over them — say so explicitly
before "keep" replaces the pre-existing files, so a prior run's real
decisions are never silently clobbered. This gate is ddd's own — distinct
from the shared workflow's Phase 3 (the apply-decision gate): ddd's own run
never applies findings, so there is no apply decision to make here, only the
domain-model keep/discard call.

### Stop
Present a compact summary: findings by tier, top 2–3 wins, anything High-impact.
**No code changes in this lens's own run** — findings remain applicable through the
shared engine when merged by the umbrella or opted into directly. Offer next steps: `/ddd design` on
a new context, hand specific findings to `/tdd`, or `/solid` for the pure-SOLID cut.
**Offer** to
capture key findings (and any kept domain decisions) wherever the project keeps
durable knowledge — the memory brain (via `/mente`) when present, else a short repo `docs/domain/` note.

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
- **Out of scope by default (opt-in only):** CQRS, Event Sourcing, Sagas — name
  them, price them, never reach for them silently. Their references
  (`references/cqrs.md`, `references/event-sourcing.md`, `references/sagas.md`)
  stay unloaded until a trigger fires (design step 3, or a reviewer finding that
  names one); a skill that has read them as background starts seeing reasons to
  use them. Once a trigger *has* fired, reading is required — you cannot price
  what you have not read.

## File map

- `references/ddd-core.md` — tactical spine, layering, DIP, when-NOT-to. Always
  read.
- `references/strategic.md` — event storming, subdomain classification, context-
  mapping catalogue. Load only for >1-context domains.
- `references/<language>.md` — the detected language's tactical idioms (value
  objects, ports, repository/UoW). Ships `python.md` (frozen dataclasses,
  `Protocol` ports, SQLAlchemy), `typescript.md` (readonly VOs, branded-type
  ids, `interface` ports, async Prisma repos), and `java.md` (records as value
  objects, Spring-aware ports, the JPA anemic-model trap); list `references/`
  for the current set. New languages drop in here.
- `references/cqrs.md`, `references/event-sourcing.md`, `references/sagas.md` —
  one per opt-in discipline: what it is, when it pays off, its honest cost list,
  the port shape, and a firm when-NOT-to. Loaded **only** once a trigger fires
  (design step 3, or an `analyze` finding that names one), never as background.
- `references/report-template.md` — exact `analyze` report format.
- `agents/analyzer.md`, `agents/reviewer.md` — the two `analyze` subagent roles.
- `../../docs/git-convention.md` — working-branch + offer-never-auto-publish.
