# Sagas / process managers — opt-in only

Load this file **only** when a genuinely multi-step, multi-aggregate process with
failure and compensation has surfaced, or when one was explicitly asked for. Most
domains never need one; a single aggregate plus its domain events is enough.

## What it is

A **saga** (as the term is used in DDD practice) is a stateful coordinator for a
business process that cannot live inside one aggregate — because
one-aggregate-per-transaction forbids it. It listens for events, holds the
process's own state, and dispatches the next command, driving the process to
completion or to **compensation** when a step fails.

The canonical shape: place order → reserve stock → take payment → arrange
shipping. Each step can fail, and each completed step has an undo (release the
reservation, refund the payment). There is no distributed transaction; there is an
explicit sequence of local transactions plus explicit compensations. That is the
whole idea — eventual consistency across aggregates, made visible and testable.

**Two styles:**

- **Process manager (orchestrated)** — one component holds the process state and
  decides each next step. **This skill's default**: the process is readable in one
  file and testable as a pure state machine.
- **Choreographed saga** — no coordinator; each participant reacts to the previous
  one's event. Less coupling, but the process exists only as an emergent property
  of scattered handlers and nobody can read it end to end. Choose it only for
  short, stable, genuinely independent chains.

## When it pays off

- A process spans two or more aggregates or bounded contexts.
- Steps have real side effects that must be undone on failure (money moved, stock
  reserved, an email sent to a third party).
- The process is long-running — it waits for external systems, human approval, or
  a timeout, and cannot be a single request/response.

## What it costs

- **A state machine nobody asked for**, if introduced early. The process's states
  and transitions are now a modeled artifact requiring their own persistence,
  tests, and migrations.
- **Compensation is not rollback.** It is business logic, and it is often
  asymmetric — you cannot un-send an email; you send an apology. Every step with a
  side effect needs its compensating action designed, not assumed.
- **Timeouts and idempotency become mandatory.** Messages are redelivered; a saga
  that is not idempotent double-charges. Every step needs a deduplication key.
- **Partial failure is now visible in the domain**: "payment taken, shipping
  failed" is a state the business must decide about.

## Shape (design mode)

- The saga is a **first-class domain concept with a name in the ubiquitous
  language** (`OrderFulfilmentProcess`, not `OrderSagaManager`), holding its own
  state and correlation id.
- It **lives in the application layer** — it is orchestration, not a business rule
  of any one aggregate. It must not become a second home for domain logic: it
  decides *sequence*, aggregates decide *legality*.
- It depends only on **ports**: a command-dispatch port and an event-subscription
  port (plus a scheduler port if it has timeouts). The concrete message bus,
  queue, or scheduler is an **adapter injected at the composition root** — a saga
  that imports a broker client has broken the dependency rule.
- Its persistence is a repository over the saga's own state, keyed by correlation
  id — the saga is, in effect, an aggregate of the process.
- **Cross-context sagas consume integration events**, never another context's
  internal domain events, and speak through the published-language / ACL boundary
  (`strategic.md`). A saga reaching directly into another context's model is the
  finding, not the coordination.

**Testing** is the payoff of this shape: feed the saga a sequence of events and
assert the commands and compensations it emits. Pure, no infrastructure, no
mocks — consistent with the domain-testing stance in `tdd`'s
`references/ddd_testing.md`.

## When NOT to

- **Do NOT** introduce a saga for a two-step process where the second step is an
  ordinary event handler that cannot fail meaningfully. That is just a domain
  event handler; call it one.
- **Do NOT** use a saga to work around an aggregate boundary that is simply drawn
  wrong. If two "aggregates" must always change together, they were one aggregate.
  Re-examine the boundary before adding a coordinator.
- **Do NOT** put business rules in the saga. If it decides *whether* something is
  allowed rather than *what happens next*, that rule belongs in an aggregate.
- **Do NOT** choose choreography for a process with more than ~3 steps or any
  compensation — no one will be able to read it.
