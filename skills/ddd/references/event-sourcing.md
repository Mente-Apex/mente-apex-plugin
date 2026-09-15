# Event sourcing — opt-in only

Load this file **only** when event sourcing has been explicitly asked for, or when
hard audit/temporal requirements have surfaced and you are about to raise it as an
option. When you raise it, state the cost list below **first**.

**Event sourcing is not required for DDD.** The default `ddd` build persists
current state through a repository and unit of work, and that is correct for the
large majority of domains. ES is a separate discipline that happens to compose
well with domain events — not a more advanced grade of the same thing.

## What it is

The event stream is the source of truth. Instead of storing an aggregate's current
state, you append every domain event it emits; current state is rebuilt by
replaying (folding) those events in order.

```
load(id):   events = store.read(id) → fold(apply, events) → aggregate
handle():   aggregate.place(...)    → records OrderPlaced (no direct mutation)
save(id):   store.append(id, aggregate.newEvents, expectedVersion)
```

Two consequences shape everything else: the aggregate's behavior methods **emit**
events and an `apply(event)` fold performs the state change, and the store's
`append` is where optimistic concurrency lives (`expectedVersion` is the
aggregate's consistency guarantee, replacing row locking).

## What it buys

- A complete, immutable audit log — not reconstructed after the fact, but the
  actual mechanism the system runs on.
- Temporal queries: what did this look like on any past date, and why.
- New read models over historical data that nobody thought to record — replay the
  stream through a new projection.
- Debugging by replay: the exact sequence that produced a bad state is on disk.

## What it costs

Say all of this before the user agrees:

1. **Event versioning and upcasting — required reading before you build.** Events
   are immutable and permanent, so the v1 events you write today must still be
   readable in three years. You will need a versioning strategy (weak schema,
   explicit `v2` types, or an upcaster chain that rewrites old events into the
   current shape on read) *from the first event*, not when the first change lands.
   This is the single most underestimated cost.
2. **Snapshots.** Long streams make replay slow. Snapshot-every-N is standard and
   is an adapter concern behind the same port — but a snapshot serializes the
   aggregate's *state* shape, so it acquires its own versioning problem.
3. **Queries are gone.** You cannot query the event store by attribute; "all
   orders over €500" has no answer without a read model. ES therefore almost
   always pulls CQRS in with it (`cqrs.md`) — budget both.
4. **Deleting data is hard.** An immutable log meets GDPR erasure badly; you need
   crypto-shredding (per-subject keys you can destroy) or a copy-and-rewrite
   procedure, decided up front.
5. **A steeper mental model** for every future contributor, and for you, six
   months later.

## Shape (design mode)

1. **Model events first**, as the write model's actual API — names in the
   ubiquitous language, past tense, carrying everything a replay needs. An event
   that requires reading another aggregate to interpret is a modeling error.
2. **Aggregate** — behavior methods validate the invariant and emit; a private
   `apply(event)` performs the state change; a rehydrating constructor folds a
   stream. Invariants are checked in the behavior method, never in `apply` (which
   must replay history unconditionally, including events that were legal then and
   would not be now).
3. **The repository port becomes an event-store port**:
   `load(id) -> aggregate` (replay) and `append(id, newEvents, expectedVersion)`.
   Snapshotting hides behind it. The domain knows events and the port, nothing else.
4. **Read models** per `cqrs.md`, projected from the same stream.
5. **Adapters** — Postgres append-only table, EventStoreDB, DynamoDB — injected at
   the composition root. The choice must not reach the domain.

**DIP:** the aggregate depends on the event types (domain) and the store port
(abstraction). Serialization format, stream naming, and snapshot policy are
adapter details.

## When NOT to

- **Do NOT** adopt ES for "we might want an audit trail someday". An append-only
  audit *table* written by a domain-event handler gives 80% of the value for ~2%
  of the cost, and is the right answer far more often.
- **Do NOT** event-source the whole system. It is an *aggregate-level* choice —
  source the two aggregates with real temporal requirements and leave the rest
  state-based.
- **Do NOT** start without a written versioning strategy. Building first and
  versioning later is the failure mode that makes teams abandon ES.
- **Do NOT** conflate it with CQRS or with a message broker. ES is a persistence
  decision; the others are separate opt-ins with separate costs.
- **Do NOT** use the event store as an integration bus — domain events are
  internal to the context; crossing a boundary needs an integration event through
  the published-language seam (`strategic.md`).
