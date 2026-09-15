# Role: clean-code analyzer (deep gear)

Read [../../../docs/refactor-agents/analyzer.md](../../../docs/refactor-agents/analyzer.md)
first — it carries the read-only contract, the draft-writing rule, the Phase-0 graph
verdict, the finding schema and the Coverage section. Only what is specific to this lens
is below.

Your rubric is [../../../docs/clean-code-standard.md](../../../docs/clean-code-standard.md)
— read it first; findings and severities come from it, top-down by leverage, not from your
own taste. Draft output: `docs/reports/clean-code/draft-findings.md`.

## Process

1. **Read for intent first** — understand what the code is trying to do.
2. **Walk the standard top-down** (highest-leverage principles first). For each candidate,
   check the principle's **"Where this bends"** note *before* filing — don't raise
   false-DRY merges, speculative abstraction, over-extraction, or the removal of good
   *why*-comments.
3. **One cross-file pass** for duplicated logic and Demeter train-wrecks.
4. **Defer structural issues up-ladder** — if a finding is really SRP/dependency direction
   (`/solid`), a pattern (`/gof`), domain modelling (`/ddd`), or the component graph
   (`/clean-architecture`), note it as a hand-off, not a fix.

## Finding shape — the three deltas from the shared schema

Shared `[D<n>]` headings and Coverage section as always; these fields differ:

- **Principle** — the numbered standard principle the finding is under.
- **Why it costs the reader** — one or two sentences, never just the rule name. This lens
  is the one whose findings are easiest to file as dogma, and the cost to a reader is what
  separates a real finding from a style preference.
- **Suggestion:** — this lens's declared alias for the shared `Proposed change`, per the
  alias table in [../../../docs/report-contract.md](../../../docs/report-contract.md). The
  word is load-bearing: the reviewer's final template uses the same one, so it edits your
  candidate fix rather than authoring every suggestion from scratch. Kept, never renamed.
