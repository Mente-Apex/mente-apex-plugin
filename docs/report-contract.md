# Report contract — the canonical finding schema

**Single responsibility: the schema, and nothing else.** Every lens report template
(`skills/*/references/report-template.md`) and the consolidated template
(`skills/code-quality/references/report-template.md`) implement this shape; this
file defines it once so they can link instead of restate. Workflow mechanics —
what fills the `Status:` line, the Apply-log line format, when `## Outcome` gets
written — live in
[refactor-workflow.md](refactor-workflow.md#status-apply-log--outcome-format-canonical)
("Status, Apply-log & Outcome format"), not here.

## ID scheme

Every finding gets a self-describing, permanent ID: `<lens>/<tier>-<n>`.

- `<lens>` ∈ `clean-arch | ddd | solid | gof | clean-code | test-quality |
  acceptance-quality` — the
  prefix makes the ID globally unique, so the code-quality umbrella (and any
  lens's *Related* line) carries it verbatim, never re-prefixed.
- `<tier>` ∈ `critical | major | minor` — the same three tiers for all seven
  lenses; clean-code, test-quality and acceptance-quality are peers on this scale,
  not down-filed.
- `<n>` is per-lens-per-tier, starting at 1.
- IDs are permanent once assigned — later cycles append, never renumber. The
  tier word records the tier **at first assignment**; if a finding is later
  re-tiered, the section heading it currently sits under is authoritative and
  the ID stays unchanged.

## Anchor rule

Precede every finding heading — in every tier's stub, not only Critical's —
with an explicit anchor: the ID with `/` → `-`, e.g. `<a id="solid-critical-1"></a>`
above `#### [solid/critical-1]`. Markdown's auto-generated heading anchors don't
handle the `/` in the ID, so without this an umbrella *Full detail* link (or any
intra-report reference) can't resolve.

## Filename rule

Each lens writes `docs/reports/<lens>/<LENS>-REPORT-<YYYY-MM-DD>.md`:

| Lens | File |
|---|---|
| clean-architecture | `docs/reports/clean-architecture/CLEAN-ARCHITECTURE-REPORT-<date>.md` |
| ddd | `docs/reports/ddd/DDD-REPORT-<date>.md` |
| solid | `docs/reports/solid/SOLID-REPORT-<date>.md` |
| gof | `docs/reports/gof/GOF-REPORT-<date>.md` |
| clean-code | `docs/reports/clean-code/CLEAN-CODE-REPORT-<date>.md` |
| test-quality | `docs/reports/test-quality/TEST-QUALITY-REPORT-<date>.md` |
| acceptance-quality | `docs/reports/acceptance-quality/ACCEPTANCE-QUALITY-REPORT-<date>.md` |
| code-quality (consolidated) | `docs/reports/code-quality/CODE-QUALITY-REPORT-<date>.md` |

## Canonical per-finding fields

`<a id>` anchor · ID `<lens>/<tier>-<n>` · Title · Lens/Principle line ·
**Location** · **Evidence** · **Reader impact** · **Proposed change** ·
**Risk** (Low | Medium | High) · **Related** · **Status**.

- The **Lens/Principle line** is the "which principle does this break" field —
  its label is lens-specific (`Principle` for solid/clean-code, `Pattern` for
  gof, `Smell` for ddd, `Check` for clean-architecture, `Kind` for
  test-quality), but every lens carries one.
- **Related** surfaces a cross-lens reference where one exists; a lens with
  nothing to cross-reference may omit the line rather than write "none" on
  every finding.
- A lens may carry fields beyond this list (e.g. solid/gof's `Verification`,
  test-quality's `Coverage proof`, gof's graded-inventory-only `Strengths` /
  `Issues`) — the canonical set is the floor the consolidator can rely on, not
  a ceiling on lens-specific detail.

## Canonical report sections

`## Summary` · findings by tier · `## Coverage` (& method) · `## Apply log` ·
`## Outcome` (apply-capable reports only — omit on an audit-only run) — plus
*available*, not mandatory, `## Conflicts` and `## Grouped changes` skeletons,
so a standalone reviewer has a sanctioned format for forks and groups even
though today only the umbrella's consolidated template needs them routinely.

## Alias table (D3)

Standard on **`Reader impact`** and **`Proposed change`** — what the shared
implementer and the consolidator already parse. A lens-flavoured field name is
either renamed to the canonical name outright, or kept as a declared alias
because the lens-flavoured framing carries information the generic name would
flatten. No undeclared synonyms: a field name that isn't the canonical name and
isn't in this table is a defect, not a style choice.

| Field name | Lens | Canonical field | Treatment |
|---|---|---|---|
| `Toward DDD` | ddd | Proposed change | **Alias, kept** — the DDD-flavoured elaboration (which entity/VO/aggregate/port the fix becomes), more specific than the generic name would be. |
| `Problem now` | gof | Reader impact | **Alias, kept** — paired with `Expected benefit` below; together they frame the same reader-impact argument as pain-now / relief-after. |
| `Expected benefit` | gof | Reader impact | **Alias, kept** — see `Problem now`. |
| `Impact` | ddd, clean-architecture, test-quality | Reader impact | **Renamed** — no lens-specific information was carried by the generic word, so all three lenses use the canonical name directly. |
| `Fix` | clean-architecture, test-quality | Proposed change | **Renamed** — same reasoning as `Impact`. |
| `Why it costs the reader` | clean-code | Reader impact | **Alias, kept** — a line-craft-flavoured framing (cost to the *reader specifically*, not change-safety in general) worth keeping distinct from the SOLID/clean-architecture framing of the same canonical field. |
| `Suggestion` | clean-code | Proposed change | **Alias, kept** — matches the clean-code-standard.md rubric's own vocabulary; the deep-gear analyzer's draft entry format also names this field `Suggestion`, so aliasing (not renaming) keeps the draft and the final report consistent. |

## What this file is not

It doesn't restate the `Status:` vocabulary, the Apply-log line format, or the
`## Outcome` content contract — see refactor-workflow.md's canonical section for
those. It doesn't restate the `ran` / `degraded` / `unverified` coverage
vocabulary — see [status-vocabulary.md](status-vocabulary.md) for that. It is
the finding shape and the ID/anchor/filename rules, and nothing else.
