---
name: clean-code
description: >
  Clean-code standard for this repo — the principles from Robert C. Martin's
  Clean Code, ranked by leverage and tempered with the places they should bend.
  Use in two modes. (1) When WRITING or EDITING code here, follow it as the
  default standard for naming, function and class design, error handling, and
  comments. (2) When REVIEWING code, a diff, or a PR — or when the user says
  "review this," "is this clean," "any code smells," "refactor suggestions,"
  "/clean-code," "tidy this up," or asks whether code is well-structured — use it
  to surface issues with file:line locations and a severity, and to suggest
  refactors. This skill encodes judgment, not dogma: it says when a rule applies
  AND when applying it would make the code worse. Do NOT use it to auto-rewrite a
  whole codebase unprompted, to enforce a specific linter/formatter config, or as
  a substitute for the security-review or /ship workflows.
user-invocable: true
allowed-tools: Read, Grep, Glob, Bash, AskUserQuestion
metadata:
  version: "0.1.0"
  source: "Robert C. Martin, Clean Code (2008), read pragmatically"
---

# clean-code

A working standard for keeping this codebase readable and changeable, distilled
from *Clean Code* and deliberately de-dogmatized. The one idea underneath every
rule: **code is written once and read many times — optimize for the next person
who has to understand and change it** (often you, in six months).

Two ways this skill gets used:

- **Writing / editing code in this repo** — treat the principles below as the
  house defaults. You don't need to announce them; just write code that already
  follows them.
- **Reviewing code, a diff, or a PR** (or on an explicit `/clean-code` run) —
  walk the code against these principles and report issues with `file:line` and a
  severity, plus a concrete suggestion. Review is read-only: surface and explain,
  don't silently rewrite (see *Scope*).

The rules are **ranked by leverage** — how much a violation actually costs the
reader. Spend your attention top-down; don't sweat #14 while #2 is broken. And
read the **"Where this bends"** note on each one: misapplying a clean-code rule is
itself a clean-code problem.

---

## The principles, by leverage

### 1. Meaningful names
Names are read constantly, so a bad one taxes every future reader. Use
intention-revealing, pronounceable, searchable names; the name should say why a
thing exists and how it's used. Avoid encodings and mental-mapping
(`i`/`j`/`tmp` outside the tightest scope).
**Where this bends:** conventional short names in a small scope are *fine* —
`i` in a 3-line loop, `e` in a catch, `id`, `db`. Don't force `customerRecordIndex`
where `i` is clearer. Searchability matters most for things referenced far from
their definition.

### 2. Single Responsibility (functions and classes)
A unit should have one reason to change. This is the spine the rest hangs on — a
class or function that owns one clear job is easy to name, test, and move.
**Where this bends:** "responsibility" is about reasons to change, not line count.
A cohesive 120-line class with one job beats five anemic classes that always
change together. Don't split just to hit a number.

### 3. Functions do one thing
A function should do one thing, at one level of abstraction, and reading it
shouldn't require holding two unrelated ideas at once.
**Where this bends — important:** *do not extract tiny functions aggressively.*
Martin's "extract till you drop" advice is the most over-applied in the book.
Shattering a readable 25-line function into eight one-liners spread down the file
often **hurts** readability — the reader now chases indirection to reconstruct one
thought. Extract when it (a) removes real duplication, (b) names a non-obvious
step, or (c) collapses a genuinely separate level of abstraction. Otherwise, a
straight-line function you can read top to bottom is the cleaner option. Prefer
"can I read this in one pass?" over "how few lines per function?"

### 4. Don't Repeat Yourself (DRY)
Duplicated logic means every change has to be made in N places and one will be
missed. Extract a single source of truth for real duplication.
**Where this bends:** beware false DRY. Two pieces of code that look alike but
change for different reasons are *coincidental* duplication — coupling them
creates a worse problem than the repetition. A little duplication is cheaper than
the wrong abstraction. Wait for the third occurrence before abstracting.

### 5. High cohesion, low coupling; depend on abstractions
Keep related data and behavior together; let modules depend on interfaces, not
concrete implementations. This is what keeps a system changeable over time.
**Where this bends:** don't introduce interfaces, factories, or dependency
injection for a single implementation that has no realistic second one. Speculative
abstraction is a cost paid now for a flexibility you may never use. Add the seam
when the second case actually arrives.

### 6. No hidden side effects; Command-Query Separation
A function should do what its name promises and nothing surprising. Prefer
functions that either *do* something (command) or *answer* something (query), not
both — `if (saveAndReturnStatus())` hides a mutation behind a question.
**Where this bends:** pure-everywhere is unrealistic. Logging, caching,
memoization, and obvious in-place mutators (`list.sort()`) are accepted side
effects. The rule targets *surprising* effects, not all effects.

### 7. One level of abstraction / read top-down
Within a function, don't mix high-level policy with low-level mechanics. Code
should read like prose: the overview first, details below it.
**Where this bends:** a sympathetic ordering is the goal, not a rule that every
caller must physically sit above every callee. Don't reshuffle a file purely to
satisfy ordering if it scatters related code.

### 8. Few arguments; no flag arguments
Zero–two arguments is comfortable; three needs a reason; more usually wants a
parameter object. Never pass a boolean that switches what the function does —
that's two functions wearing one name.
**Where this bends:** a well-understood signature with several args (e.g. a
constructor for a value object, a known library call) is fine. Don't wrap three
naturally-related scalars in a struct just to lower the count.

### 9. Error handling with exceptions, not return codes; never return null
Use exceptions over error flags so the happy path stays readable; don't return or
pass `null` (return empty collections, options, or throw). Error handling is one
thing — a function that handles errors should mostly just do that.
**Where this bends:** in languages/ecosystems where result types or error returns
are idiomatic (Go's `err`, Rust's `Result`, option types), follow the language —
forcing exceptions there is the unclean choice. Match the platform's conventions.

### 10. Comments are a last resort, not a failure to be punished
Prefer code that explains itself; a comment that restates the code is noise, and a
stale comment actively lies. Delete commented-out code and redundant headers.
**Where this bends — important:** the book's near-zero-comment stance is too
strong. Comments that explain **why** (intent, trade-offs, the reason for a
non-obvious choice), warn of consequences, cite a spec/bug/RFC, or document a
public API are valuable and should be *added*, not removed. "Self-documenting
code" cannot express *why this approach over the obvious one*. Flag bad comments
(redundant, outdated, commented-out code); don't flag good ones, and don't strip
explanatory comments in the name of cleanliness.

### 11. Law of Demeter — don't talk to strangers
A method should only call methods on itself, its parameters, objects it creates,
and its direct fields. Train wrecks like `a.getB().getC().doThing()` couple you to
a whole object graph.
**Where this bends:** fluent builders and well-known chained APIs
(`stream().filter().map().collect()`, query builders) are designed to chain and
are exempt — the concern is reaching through *domain* objects to grab their
internals, not using a fluent interface.

### 12. Encapsulate conditionals; prefer polymorphism over type-switching
Extract gnarly booleans into well-named predicates (`if (eligibleForRefund(order))`),
and when the same `switch`/`if-else` on a type recurs across the code, push it
behind polymorphism.
**Where this bends:** a single, local switch is perfectly clean — don't build a
class hierarchy to avoid one. Polymorphism earns its keep when the *same* branching
is duplicated in several places.

### 13. Clean tests (F.I.R.S.T.)
Tests must be Fast, Independent, Repeatable, Self-validating, and Timely, with one
concept per test and clear arrange/act/assert. Tests are the safety net that makes
all the refactoring above safe; dirty, flaky tests are worse than none.
**Where this bends:** test code values *obviousness* over DRY — some readable
duplication across tests is fine. And one logical assertion can be several physical
`assert`s; "one concept" matters more than "one assert."

### 14. Consistent formatting
Related code stays vertically close; indentation and spacing are consistent across
the file and the project. Real, but lower-leverage than everything structural above.
**Where this bends:** this should be a tool's job (formatter/linter), not a human
review comment. Don't spend review attention on whitespace a formatter settles —
match the repo's existing config and move on.

### 15. The Boy Scout Rule
Leave the code a little cleaner than you found it; small continuous improvements
prevent rot. This is the meta-habit that keeps the other fourteen alive.
**Where this bends:** keep cleanup *proportional and in-scope.* Don't smuggle a
sweeping refactor into an unrelated bug-fix PR — it bloats the diff and hides the
real change. Note larger cleanups separately rather than doing them inline.

---

## The meta-rule

If you ever find yourself making code **harder** to read in order to satisfy one of
these rules, stop — the rule has been misapplied. Readability for the next human is
the actual standard; the fifteen above are heuristics that usually serve it. When a
heuristic and readability conflict, readability wins, and that's worth a one-line
note explaining why.

---

## Review mode

When reviewing code, a diff, or a PR:

1. **Scope it.** Default to the current diff / the file or paths the user names. For
   a PR or branch, look at the changed lines first; only widen if asked.
2. **Read for intent before rules.** Understand what the code is trying to do, then
   check it against the principles top-down (highest leverage first).
3. **Report each finding** with: `path:line`, the principle, *why it costs the
   reader here* (not just the rule name), a concrete suggestion, and a severity.
4. **Respect the bends.** Before flagging, check the "Where this bends" note. Don't
   raise false-DRY merges, speculative-abstraction "fixes," over-extraction, or
   removal of good *why*-comments. A clean review has few, high-signal items.
5. **Stay read-only.** Explain and suggest; don't rewrite the codebase. Offer to
   apply a specific fix only if the user asks.

### Severity

- **High** — bites correctness or makes the code genuinely hard to change: hidden
  side effects, SRP violations that tangle unrelated change, returned `null` that
  will crash, real duplicated logic that will drift, misleading names/comments.
- **Medium** — clear readability or maintainability drag: too many/flag arguments,
  unencapsulated complex conditionals, mixed abstraction levels, Demeter train
  wrecks, weak test structure.
- **Low** — polish: minor naming, ordering, formatting (prefer the formatter).

### Suggested output

```
Clean-code review — <scope>

High
  path/to/file.py:42  Hidden side effect — load_config() also writes a cache file;
                      callers can't tell from the name. → split the write out, or
                      rename to load_and_cache_config().

Medium
  path/to/file.py:88  Flag argument — render(items, isAdmin) branches into two
                      behaviors. → two functions: render() / renderForAdmin().

Low
  path/to/file.py:12  Name `tmp2` doesn't reveal intent. → `pendingInvoices`.

Looks good
  - Error handling via exceptions, happy path stays clean.
  - Comment at :70 explains *why* the retry backoff is capped — keep it.

Summary: 1 high, 1 medium, 1 low. The high one is worth fixing before merge.
```

If nothing meaningful is wrong, say so plainly — don't manufacture findings to look
thorough.

---

## Scope — what this skill does not do

- It does **not** auto-rewrite or mass-refactor a codebase on its own. Review
  surfaces issues; changes are deliberate and, beyond the immediate edit at hand,
  happen only when the user asks.
- It does **not** enforce a particular linter/formatter/style config — match the
  repo's existing tooling and conventions instead of imposing new ones.
- It does **not** replace `security-review` (use that for vulnerabilities) or
  `/ship` (use that to commit and open a PR). Run a clean-code pass *before* you
  ship; it isn't part of the ship pipeline itself.
