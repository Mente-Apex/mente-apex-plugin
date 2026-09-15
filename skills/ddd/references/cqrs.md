# CQRS — opt-in only

Load this file **only** when CQRS has been explicitly asked for, or when the
modeling interview surfaced sharply divergent read and write needs and you are
about to *recommend* it. Never adopt it silently: the default `ddd` build is one
model, and that is the right answer for most domains.

## What it is

Command Query Responsibility Segregation splits the model in two:

- **Command side** — the DDD aggregate. Accepts commands, enforces invariants,
  emits domain events. Optimized for consistency. Everything in `ddd-core.md`
  applies here unchanged.
- **Query side** — one or more denormalized **read models** (projections), each
  shaped for a specific screen or query. No domain logic, no invariants, no
  behavior. Typically built by handling the command side's domain events.

The two sides may share a database (two sets of tables, or tables plus views) or
diverge to separate stores. That is a deployment decision, not the pattern.

**CQRS and event sourcing are independent.** CQRS does not require ES; ES does not
require CQRS (though ES nearly always wants it — see `event-sourcing.md`). Treating
them as one decision is the most common way teams buy far more complexity than
they meant to.

## When it pays off

- Read and write workloads diverge sharply — 100:1 read ratios, or reads that
  need scaling and caching the write model cannot give.
- Many distinct read shapes over the same aggregates: a dashboard, an export, a
  search index, a mobile summary — each wanting a different projection, none
  wanting the aggregate.
- The write model is genuinely rich (real invariants), and joins to satisfy
  queries are already contorting it — the classic tell is an aggregate carrying
  fields no invariant needs, present only so a screen can render.
- Reporting queries currently reach across aggregate boundaries, which the
  one-aggregate-per-transaction rule cannot express.

## What it costs

State these before the user agrees, not after:

1. **Two models to keep honest.** Every write-side change that a screen depends on
   needs a matching projection change. The model surface roughly doubles.
2. **Eventual consistency becomes user-visible.** A read immediately after a write
   may not reflect it. That is a *product* decision — the UI must tolerate it
   (optimistic update, "processing" state, or a read-your-own-writes path).
3. **Projection rebuild machinery.** Projections drift, break, and need
   rebuilding from scratch; that tooling is real work and is usually written the
   first time under pressure.
4. **Debugging spans two paths.** "The number is wrong" now has two candidate
   causes and no single place to look.

## Shape (design mode)

Build the write side first and completely; the read side is downstream of it.

1. **Write side** — domain core → application services, exactly per `ddd-core.md`.
   Repositories return aggregates. Unchanged.
2. **Query ports** — separate from repositories, and this separation is
   load-bearing:

   | | Repository port | Query port |
   |---|---|---|
   | Returns | a fully-constituted aggregate | a read model / DTO |
   | Used by | application services, to change state | web/API, to render |
   | Enforces | invariants | nothing |

   A repository that returns a read model, or a query port that returns an
   aggregate, has collapsed CQRS back into one confused model. This is ISP: the
   query side never asked for `save`, and the command side never asked for
   `findForDashboard`.
3. **Projection handlers** — subscribe to domain events, build and update read
   models. They live in the application layer, depend on ports, and hold no
   business rules of their own: a projection that *decides* something is a
   misplaced domain rule.
4. **Adapters** — the projection store behind the query port, injected at the
   composition root.
5. **Web last**, reading through query ports and writing through application
   services. Never both in one handler pretending to be a "service".

**DIP:** the read side depends inward on the **event contract** — never the
reverse. The command side must not know a projection exists; if it does, the split
has bought complexity and given nothing.

## Analyze-mode signature

*(For the `analyze` **reviewer** only. The analyzer flags the observation without
pricing it and never loads this file; the reviewer loads it to tier the finding.)*

A codebase reaching for CQRS informally: queries bypassing aggregates (raw SQL or
ORM reads in a controller for a screen, while writes go through the domain),
aggregates carrying display-only fields, or a repository with a growing family of
`findXForY` methods returning DTOs. That is not automatically a defect — it is
often the *right* pragmatic shape. Report it as "this is de-facto CQRS; formalize
the query side or accept it deliberately", not as a violation.

## When NOT to

- **Do NOT** apply CQRS to a CRUD-ish single-context domain. Two models over one
  set of business rules is the canonical over-engineering trap.
- **Do NOT** adopt it because the read side is slow — measure first; an index or a
  denormalized view solves most of these without splitting the model.
- **Do NOT** assume it requires event sourcing, message brokers, or separate
  databases. Synchronous projections in the same transaction are a legitimate
  starting point and remove cost 2 entirely — note this is the one sanctioned
  exception to `ddd-core.md`'s "never dispatch mid-transaction", and it is a trade,
  not a loophole: the projection now shares the write's transaction, so a slow or
  failing projection fails the command.
- **Do NOT** split *some* aggregates and not others without saying so — a half-CQRS
  codebase is harder to reason about than either whole.
