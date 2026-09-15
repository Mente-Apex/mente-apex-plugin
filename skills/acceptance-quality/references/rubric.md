# acceptance-quality rubric

Seven areas, ordered by leverage. Each carries what the smell looks like **and** what is
ordinary practice that must not be filed — this lens grades a suite that real people
agreed on, and a pedantic acceptance review is worse than none.

## The cold-read test — apply it to every finding

Unit suites are largely left to the agent. This layer is the one **a human reads
occasionally, and cold**: no code loaded, step definitions unopened, possibly eighteen
months after agreeing the behaviour, possibly never having seen the system.

So before filing anything, ask the question that decides both whether it is a finding and
what tier it gets:

> Read only the scenario text. Can you say what the system does, and would you notice if
> it did something else?

- **No to the first** → the scenario has failed at its one job. Major at minimum, even
  when it runs perfectly and covers real behaviour.
  *Passing is not the bar here; being read is.*
- **No to the second** → the scenario pins nothing. Critical:
  it is decoration that reports green.
- **Yes to both, but it grates** → Minor, or nothing at all. A wide `Background`, a
  long `Examples` table, one clumsy sentence cost a cold reader nothing, and are not
  worth an argument with the people who wrote them. (A *suite-wide* inconsistency is a
  different matter — see area 6: one slip is noise, a pattern is a finding.)

**Coverage outranks craft.** A beautifully-written suite that does not say what the system
does is the worse failure, and it is the one only this lens can see — a unit suite cannot
know what was agreed.

## 1. Spec-as-spec

The question the whole lens turns on: **can a reader tell what the system does from the
scenarios alone, without opening a step definition?**

- **Imperative script** — `When I click "#submit"`, `And I wait 2 seconds`, `Then I see
  ".alert-success"`. This is a macro recording, not a specification. Critical when the
  whole suite reads this way; Major for one scenario.
- **Missing the Then** — a scenario that ends in an action and asserts nothing observable.
- **Multiple Whens** — two actions in one scenario usually means two scenarios; the
  failure cannot say which action broke.
- **Scenario titles that name a mechanism** (`test login 2`) rather than a behaviour
  (`a locked account cannot sign in`).

**Not a finding:** a genuinely mechanical scenario stated mechanically (a file-upload
size limit, a keyboard shortcut). Some behaviour IS the interaction.

## 2. Implementation leakage

Domain language in, mechanism out. `atdd`'s `spec-guardian` rubric is the reference for
what counts — cite it rather than restating it.

- **Selectors, CSS classes, element ids** in scenario text.
- **Table names, column names, SQL** — the database is not part of the agreed behaviour.
- **HTTP verbs, status codes, endpoint paths** in a scenario about user-visible
  behaviour. (In a scenario about an API's contract, they ARE the behaviour — judge by
  who the stakeholder is.)
- **Internal class or module names.**

**Not a finding:** a domain term that happens to match a table name. The test is whether
a business reader recognises the word, not whether a developer also does.

## 3. Domain coverage

- **An acceptance criterion with no scenario** — the gap that matters most, and the one
  only this lens can see, since a unit suite cannot know what was agreed.
- **A scenario pinning no observable outcome** — it passes whatever the system does.
- **Happy path only**, where the agreed behaviour clearly includes a refusal, a limit or
  an error.

**Not a finding:** every permutation of an input. Acceptance tests are examples, not
exhaustive coverage — that is the unit suite's job, and demanding combinatorial scenarios
here is how acceptance suites become unmaintainable.

## 4. Scenario coupling and ordering

- **Shared mutable state between scenarios** — scenario B passing because scenario A ran
  first. Critical: it makes every other result in the suite unreliable, the same way
  order-dependence does in a unit suite.
- **A `Background` that is really setup for two of nine scenarios** — it runs for all
  nine and hides which ones actually need it.
- **Scenarios that must run in file order**, including "create, then update, then
  delete" chains written as three scenarios.

**Not a finding:** a `Background` genuinely shared by every scenario in the file. That is
what it is for.

## 5. Step-definition health — the CODE must be DRY

The acceptance-layer version of `test-quality`'s stale-test tending, and invisible one
file at a time. This area is about the **definitions behind the steps**, which are code
and obey code's rules.

- **Near-duplicate definitions** — "I am logged in" / "I have logged in" / "the user is
  authenticated" doing the same thing through three definitions that drift apart the
  first time one is fixed.
- **A vocabulary that only ever grows** — every new feature adding definitions, none ever
  merged or retired.
- **Over-parameterised steps** that take five arguments and encode a whole scenario in
  one line.
- **Step definitions with logic** — an `if` in a definition means the step means two
  things.
- **Overlapping regex / expression patterns**, where which definition runs depends on
  registration order.

**Not a finding:** two similar definitions with genuinely different meanings. Merge only
where the behaviour is the same.

## 6. Prose consistency — the SCENARIOS are held to consistency, not to DRY

The definitions behind the steps are code and must be DRY. **The scenario text is prose,
and prose is held to a different standard.** You do not merge two scenarios because they
read alike — you make them say the same thing the same way. De-duplicating prose destroys
the examples this layer exists to give; leaving it inconsistent makes a cold reader stop
and work out whether two sentences mean two things.

That cost is the whole reason this area exists. **An occasional reader cannot tell
deliberate variation from accidental variation**, so every inconsistency reads as a
distinction until they have proved otherwise — and they will not, they will guess.

- **One term per concept, every time.** "the customer" / "the user" / "the account
  holder" for one actor is three concepts as far as a cold reader knows. Same for states
  ("cancelled" / "voided" / "revoked"), for things ("the order" / "the basket" / "the
  cart"), and for actions ("submits" / "places" / "confirms").
- **One tense and voice per step keyword.** `Given` in the past or present-perfect, `When`
  in the present, `Then` stating the observable — whichever the suite chose, it chose for
  all of them. A file mixing "I was logged in" with "I am logged in" is asking the reader
  whether the difference matters.
- **One level of abstraction within a scenario.** "Given a customer with an expired card"
  next to "And the `card_expiry` field is 2019-04-01" makes the reader change altitude
  mid-scenario.
- **One grammar for scenario titles.** All noun phrases, or all sentences, or all
  "<actor> <verb>s <object>" — not "Login fails" beside "The user should not be able to
  sign in when locked".
- **One name per role, across files**, not merely within one. Consistency that stops at
  the file boundary is the version a reader hits hardest, because they arrive by search.

Where the terms disagree with the domain's own language, that is `ddd`'s ubiquitous
language at this altitude: cross-reference it per the hub and file the consistency
finding here.

**Not a finding: variation that carries meaning.** "the customer" and "the guest" are two
actors, and flattening them would be worse than the inconsistency. Judge by whether the
distinction is real — and where it is real but easy to miss, the finding is that the suite
never says so, not that the words differ.

**Not a finding:** British vs American spelling, serial commas, or any other house-style
question — unless the suite is inconsistent *about it*. Consistency is the standard; a
particular choice is not, and this lens does not have opinions about anyone's house style.

## 7. Stale scenarios

- **Pinning behaviour that no longer exists** — the acceptance-layer dead test. Its proof
  is the same as elsewhere: the thing it names is gone, not moved.
- **`@skip` / `@wip` / `@ignore` tags with no reason or ticket** — an obsolete pin that
  reads as coverage.
- **Scenarios commented out** rather than deleted or fixed.

**Not a finding:** a tagged scenario with a stated reason and an owner. That is a
decision, not rot.

## Tiering — weighted by what a cold reader loses

- **Critical** — the suite cannot be trusted or cannot be read: order-dependence, a
  scenario asserting nothing observable, a suite that is entirely a click-script.
- **Major** — a cold reader is misled or left guessing: missing coverage of agreed
  behaviour, selectors and table names in scenario text, step definitions duplicated
  three ways, a scenario whose title names a mechanism, **one concept named three ways
  across the suite** (they cannot tell whether it is one concept).
- **Consistency findings are filed per CONCEPT, not per occurrence.** "the customer /
  the user / the account holder are one actor under three names, 31 scenarios" is one
  finding a human can act on; thirty-one findings is a list nobody reads. The same rule
  the other lenses use for a repeated smell.
- **Minor** — craft that costs the reader nothing: wording, tense, a `Background` that is
  slightly too wide, a scenario that could be an `Examples` row.

When in doubt, down — **except on the cold-read test**, where the bar is the reader's
comprehension and not the reviewer's taste.

Prefer the few findings a human will act on. This review is read by the same people who
agreed the scenarios; thirty wording nits is a review nobody opens twice, and it spends
the credibility needed for the finding that mattered.
