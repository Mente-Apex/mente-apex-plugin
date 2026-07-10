# DDD strategic design — load only for multi-context domains

Read this only when the domain has (or is growing) more than one bounded context.
For a single-context app, skip it — strategic ceremony on a small domain is a net
loss.

## Subdomain classification

Sort the problem space before modelling:
- **Core** — the domain that differentiates the business. Spend your best
  modelling effort here.
- **Supporting** — necessary but not differentiating; model it plainly.
- **Generic** — solved elsewhere (auth, payments); buy/adopt, don't lovingly
  model.

## Event storming (facilitation script)

Use for genuinely novel or tangled domains, one step at a time, live with the
user:
1. **Domain events** — "What has happened in this domain?" Collect past-tense
   facts (`OrderPlaced`, `PaymentTaken`). Put them on a timeline.
2. **Commands** — "What triggers each event?" (`PlaceOrder` → `OrderPlaced`).
3. **Actors/policies** — who issues the command, what rule reacts to an event.
4. **Aggregates** — "What enforces the rule / owns the invariant?" Cluster
   commands+events around the thing that guards consistency.
5. **Boundaries** — where the language changes meaning, draw a bounded-context
   line. That edge becomes a context-map relationship (below).

## Bounded context integration — the full context-mapping catalogue

For each pair of contexts, name the relationship and its upstream (U) /
downstream (D) direction:
- **Partnership** — two contexts succeed or fail together; coordinated planning.
- **Shared Kernel** — a small, explicitly shared model subset; changes require
  joint agreement. Powerful and dangerous; keep it tiny.
- **Customer/Supplier** — downstream (D) is a customer whose needs the upstream
  (U) supplier agrees to serve.
- **Conformist** — downstream conforms to the upstream model wholesale (no
  translation). Cheap, but you inherit the upstream's language.
- **Anti-Corruption Layer (ACL)** — downstream builds a translation layer that
  keeps the upstream model out of its own; the ACL is itself an adapter behind a
  port. Use when the upstream model would corrupt yours.
- **Open Host Service** — upstream publishes a defined protocol for many
  downstreams.
- **Published Language** — a well-documented shared interchange format (often the
  contract carried by integration events) used across the boundary.
- **Separate Ways** — the contexts do not integrate at all; sometimes the right
  call.
- **Big Ball of Mud** — the anti-pattern: no boundaries, tangled model. Name it
  when you see it; wall it off behind an ACL rather than extending it.

## Domain vs integration events across a boundary

Internal **domain events** stay inside a context. What crosses a context edge is
an **integration event** expressed in the Published Language and, on the
consuming side, translated by an ACL. Never let a downstream depend on an
upstream's internal domain-event shape.
