# SOLID rubric — shared calibration for analyzer & reviewer

You already know these principles; the one-line definitions below are anchors,
not lessons. What this file actually provides is **calibration**: what counts
as a finding in this skill, what does not, and how to tier it. The analyzer and
reviewer both read this file so they judge against the same yardstick — that
shared yardstick is what makes the verification pass meaningful.

The skill's goal is **human readability of AI-generated code**. Every finding
must argue its *reader impact*: how does this violation slow down or mislead a
human trying to understand or change the code? A violation with no reader
impact is not a finding.

---

## SRP — Single Responsibility Principle

> "A module should have one, and only one, reason to change." — Robert C.
> Martin (equivalently: responsible to one actor).

**Violation signatures in AI-generated code**
- God classes/modules: `*Manager`, `*Handler`, `*Service`, `*Processor`,
  `*Helper`, `utils.*` files that validate + compute + persist + notify +
  format in one place. Generated code loves a single class that "does the
  feature".
- Script-shaped modules: argument parsing, business logic, IO, and output
  formatting interleaved top-to-bottom in one file.
- Functions whose docstring needs the word "and" twice.

**Detection heuristics**
- Rank files by line count and import fan-in; read the top ones first.
- Grep for class names matching `Manager|Handler|Service|Processor|Controller`
  and check their method lists for mixed vocabularies (e.g. `validate_*`,
  `save_*`, `send_*`, `format_*` on one class).
- A class whose methods use disjoint subsets of its fields is two classes.

**Do NOT flag**
- Small cohesive modules (~≤200 lines) with one clear narrative, even if they
  touch two concerns in passing. Splitting readable code is a net loss.
- Entry-point wiring (`main`, composition roots) — assembling everything *is*
  its single responsibility.
- Test files that group scenarios broadly.

---

## OCP — Open/Closed Principle

> "Software entities should be open for extension, but closed for
> modification." — Bertrand Meyer, popularized by Martin.

**Violation signatures in AI-generated code**
- `if/elif` or `switch` chains on a type/kind string — the tell is the *same
  chain duplicated* in two or more places, so adding a variant means finding
  and editing every copy.
- "Add a case here" comments; enums whose every consumer switches on them.

**Detection heuristics**
- Grep for repeated conditionals on the same discriminator
  (`if .*type ==`, `elif .*kind`, `switch (.*type)`); count distinct sites per
  discriminator. Two-plus sites is the finding; one site is usually fine.

**Do NOT flag**
- A *single* dispatch site — as a *structural* finding. One `if/elif` chain in
  one place is often the most readable option, and a strategy-class explosion
  for three variants is worse. An in-place upgrade that reads better (dict /
  table dispatch) may still be worth a Minor rec — see Scale calibration
  below.
- TypeScript discriminated unions with exhaustiveness checking — that is an
  idiomatic, compiler-enforced *solution*, not a violation (see
  `typescript.md`).
- Stable domains: if variants realistically never grow, closed code is honest
  code.

---

## LSP — Liskov Substitution Principle

> "Subtypes must be substitutable for their base types without altering the
> correctness of the program." — Barbara Liskov (1987), Martin's phrasing.

**Violation signatures in AI-generated code**
- Subclass methods that `raise NotImplementedError` / `throw new Error("not
  supported")` for inherited operations.
- Overrides that strengthen preconditions ("this subclass only accepts X"),
  weaken postconditions, return a different shape, or silently return
  None/undefined where the base returns a value.
- `isinstance` / `instanceof` checks sprinkled through callers to special-case
  one subtype — the callers are telling you substitution is broken.

**Detection heuristics**
- Grep `NotImplementedError|not supported|instanceof|isinstance` and inspect
  hits that sit inside subclass overrides or polymorphic call sites.
- Read base-class docstrings/contracts, then diff each override's actual
  behavior against them.

**Do NOT flag**
- `NotImplementedError` in an explicitly abstract method of an abstract base —
  that's the contract being *declared*, not broken.
- Deliberate capability probing at a boundary (one `isinstance` at the edge,
  not scattered through the core).

---

## ISP — Interface Segregation Principle

> "Clients should not be forced to depend on methods they do not use." —
> Robert C. Martin.

**Violation signatures in AI-generated code**
- One fat base class / interface with many abstract methods, where concrete
  subclasses stub half of them (`pass`, `return None`, `NotImplementedError` —
  note the overlap with LSP; file it where the *cause* is: fat interface → ISP,
  broken contract → LSP).
- Interfaces that mirror an entire implementation class method-for-method.
- Clients importing a big object to call one method on it.

**Detection heuristics**
- For each abstract base/interface, count methods and check what fraction each
  implementor actually implements meaningfully and each client actually calls.

**Do NOT flag**
- Interfaces with 2–4 cohesive methods. Splitting those is interface confetti.
- Wide interfaces that every implementor genuinely fulfills and every client
  genuinely uses.

---

## DIP — Dependency Inversion Principle

> "High-level modules should not depend on low-level modules; both should
> depend on abstractions. Abstractions should not depend on details." —
> Robert C. Martin.

**Violation signatures in AI-generated code**
- Business logic constructing its own infrastructure: `SqliteDb()`,
  `requests.Session()`, `SmtpClient()`, `open(path)` inside domain classes —
  the #1 pattern in generated code, and the reason it's untestable without a
  network.
- Module-level singletons (`db = Database()` at import time) that every
  consumer imports directly.
- Hard-coded hosts, paths, and credentials inside logic (also a smell for
  config injection).

**Detection heuristics**
- Grep constructor calls to known infrastructure (db/http/fs/smtp/queue
  clients) *inside* domain/service modules; the fix is constructor/parameter
  injection behind a small abstraction.
- Import graph: domain modules importing concrete adapter modules point the
  wrong way.

**Do NOT flag**
- Stable stdlib or language built-ins (`json`, `datetime`, `Math`) — wrapping
  those is ceremony, not inversion.
- The composition root — *somewhere* has to instantiate concretions; that's
  its job.
- Small scripts/tools — for *abstraction layers*. Don't demand interfaces and
  injected adapters where no test seam is worth buying. Cheap parameterization
  (a hard-coded path or host lifted into a parameter with a default) is still
  worth a Minor rec — see Scale calibration below.

---

## Scale calibration — the don't-flag rules are about structure, not polish

The don't-flag rules above exist to stop one failure mode: **adding
structure** — strategy classes, interface layers, new files — to code that
reads fine without it. They are not vetoes on cheap, in-place improvements.

In a small codebase (a single-file script, or a project a reader can hold in
their head at once), flip the default from *prune* to *keep as Minor* when the
fix is all three of:

- **in-place** — no new files, classes, or interface layers;
- **no bigger** than the code it replaces;
- **clearly better for the reader**, or removes a footgun — e.g. a dict
  dispatch replacing a sprawling `if/elif`, or a hard-coded path lifted into
  a parameter with a default.

Report it as Minor with an honest Risk and let the human decide at the gate —
pruning such a finding decides *for* them. Reserve pruning for findings whose
fix would make a small script structurally heavier than the problem it solves.

---

## Tier rubric (Critical / Major / Minor)

Tier by **reader impact × blast radius**, not by how offended the principle is:

- **Critical** — actively blocks comprehension or safe change *today*: a god
  class at the center of the app; the same type-switch duplicated 3+ places so
  variants get missed; substitution breakage that can produce wrong behavior;
  core logic untestable without live infrastructure.
- **Major** — clear violation with real, recurring friction but contained
  blast radius: fat interface with stubbed implementations; a two-site switch;
  an injected-nowhere dependency in one subsystem.
- **Minor** — emerging or cosmetic-adjacent: a class drifting toward two
  responsibilities; a one-site switch likely to grow; naming that hides intent
  at the design level. Cheap to fix, low urgency.

When in doubt, tier **down** — an inflated Critical erodes the human's trust
in the whole report.

## Risk rubric (Low / Medium / High)

Risk = chance the *fix* breaks something, independent of tier:

- **Low** — internal-only, mechanical, well covered by tests (extract class
  used in one module, introduce a Protocol/interface, inject via constructor
  with a default).
- **Medium** — touches several call sites or partially tested code; mechanical
  but wide.
- **High** — changes public API signatures, moves code across modules/packages,
  touches persistence formats or anything behavior-adjacent, or lands in code
  with no test coverage. High-risk recs are individually confirmed with the
  human before anyone touches them.

## Finding quality bar

Every finding needs: principle, exact location(s) (`file:line`), quoted
evidence, the reader-impact argument, a concrete proposed change, a tier, and
a risk. If you can't quote the evidence, you don't have a finding. Prefer 10
findings a human will act on over 30 they will skim.
