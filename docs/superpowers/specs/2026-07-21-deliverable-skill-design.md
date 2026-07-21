# Design — `menteapex-deliverable` skill (renames `menteapex-proposal`)

**Issue:** [#64](https://github.com/menteapex/mente-apex-plugin/issues/64) (partial — proposal half; invoice/onboarding parked)
**Date:** 2026-07-21
**Status:** proposed, awaiting review

## Problem

The three lifecycle skills (`menteapex-proposal|invoice|onboarding`, last touched
2026-07-07) predate a dramatic rewrite of the ground-truth docs (`JOURNEY.md`,
`Legal/` templates, brand chain — 2026-07-15→19). They no longer match reality:

- **proposal** produces one generic hand-built "proposal", EN only, inventing its
  own structure instead of sourcing the `Legal/` Markdown templates. This violates
  JOURNEY.md's twice-stated standing rule: *"MD is source, HTML/PDF is derived,
  never hand-edited — change the MD, re-render."*
- The `.build/` "render skeleton" is only CSS tokens + fonts + example HTML —
  **there is no MD→HTML/PDF renderer**; each skill re-describes an ad-hoc, and
  inconsistent, PDF step (proposal uses Chrome-headless; invoice punts to manual
  Print-to-PDF).

## Scope

- **In:** Replace `menteapex-proposal` with a general **`menteapex-deliverable`**
  skill that renders *any* client-facing `Legal/` deliverable, in any of the four
  language variants, from the Markdown source of truth.
- **Parked (unchanged this pass):** `menteapex-invoice`, `menteapex-onboarding`.
  They remain as-is; a later issue overhauls them (onboarding will *orchestrate*
  this skill for the Stage-D pack).

## Behaviour (the skill)

1. **Pick the deliverable** — multiple-choice over the **client-facing** template
   families in `Legal/`:
   initial-offer · proposal · engagement-agreement · licensing (gift / paying /
   pro-bono) · dpa · handover · update-brief · preproduction-notice.
   *Excluded:* internal-only (`ip-licensing-policy`, `trade-in-kind`) and
   `site-baseline/` (renders into the **client's own** site, not MA brand).
2. **Pick the language** — EN (`*.md`) · es-ES · es-419 · hr. Loads the matching
   variant file; falls back to EN with a warning if a variant is missing.
3. **Fill every placeholder.** Templates mark fill-in slots as `[bracketed prose]`
   (e.g. `[Client / business]`, `[date]`, `[€X]`) and carry `<!-- HTML comment -->`
   guidance blocks that are *instructions to strip, not fill*. The skill gathers
   inputs (client's `customer_input/` + registry first, then asks the user) and
   **loops until zero `[…]` slots remain** — completeness is checked mechanically
   by `render.py --check` (see below), so the skill cannot ship a half-filled doc.
4. **Render** on-brand HTML + PDF into `Customers/<X>/docs/` via `render.py`.
5. **Draft the client email.** If the Gmail connector (`mcp__claude_ai_Gmail__*`)
   is available in the session, create a **draft** (recipient from the client
   registry / `PROJECT.md`, or ask). Otherwise output ready-to-paste subject+body
   in the chosen language. Never blocks the deliverable.

## The renderer — `scripts/render.py`

A single reproducible tool every deliverable reuses. Pure, deterministic, and
**zero-dependency** (stdlib only) — the plugin is config-synced across machines and
must not break on a fresh box where `pip install markdown` hasn't run. Because we
*own* the template inputs, the Markdown subset it must handle is bounded (headings,
bold/italic, links, ordered/unordered lists, tables, hr, blockquote, paragraphs) —
not arbitrary CommonMark.

```
render.py <filled.md> --lang <en|es-ES|es-419|hr> --kind <cover|document> --out <dir>
render.py <file.md>   --check          # exit 1 + list if any [placeholder] remains
```

Pipeline:

1. **Consult the live brand output — never copy or run a Brand script.** Resolve
   `$BRAND_ROOT` (default `$BUSINESS_ROOT/Brand`). Read the **live generated**
   artifacts each render — `Brand/tokens/tokens.css` (the output `build_tokens.py`
   produces), `fonts.css`, and the wordmark — straight from the Brand source, never a
   frozen or reimplemented copy. Brand edits (colours, type) thus flow into every
   render automatically the moment they are regenerated. The skill **neither copies
   nor executes** `build_tokens.py`, so it cannot drift from, or be broken by, that
   generator — token *generation* stays single-sourced in the Brand repo.
   **Freshness nudge:** if `brand-book.html` is newer than `tokens/tokens.css`, print
   a warning (`⚠ brand tokens may be stale — run Brand/tokens/build_tokens.py`) and
   proceed with the current `tokens.css`. This catches a forgot-to-regenerate edit
   without the renderer ever owning the generation logic.
2. **Layout from the brand book's grid, not invented "skins".** The book defines one
   system: module **M = 6% of the format's shorter edge** (A4 → 12.6mm); page margins
   = M all sides; covers / identity moments may breathe at 1.5M (or full-bleed);
   column gutter = M/3; type roles are multiples of base **B** (H2 1.85 · Lead 1.15 ·
   Body 1 · Caption .92 · Overline .77), client print B ≈ 10.5–11pt. Colour roles on
   light: text = Navy, secondary = Slate, links = Levante Deep, gold = Deep Gold, and
   **gold appears once per composition**. Letterhead carries only the audience-
   language primary tagline. These formulas are encoded once in `assets/shell.html`.
3. **Strip** `<!-- … -->` guidance comments.
4. **Assert** no `[…]` placeholders survive (the `--check` gate, reused inline);
   markdown links `[text](url)` are *not* placeholders and are excluded.
5. **Convert** the Markdown body → HTML (stdlib subset converter).
6. **Inject** into the brand shell. Two page treatments, both from the grid above:
   an **identity page** (full-bleed navy masthead: wordmark, doc kicker, title, meta)
   for the sales documents (proposal, initial-offer — the book's "identity moment"),
   and plain **M-margin letterhead** pages for the legal/ops documents (agreement,
   licensing, DPA, invoice, handover, update-brief, preproduction). Which family gets
   the identity page is fixed in `references/templates.md`, not guessed per run.
7. **Honour the book's Multi-page Documents law** (deliverables are sequences
   governed by flow, not single compositions). Encoded as print CSS in the shell:
   - **Atomic blocks never break** — tables, pricing/signature clauses, images,
     boxes stay whole: `break-inside: avoid`.
   - **Headings keep with their first two lines** — never stranded at a page foot:
     `break-after: avoid` on h1–h4.
   - **Tall tables** break between rows and **repeat their header**:
     `thead { display: table-header-group }`.
   - **Prose flows across turns** but leaves **two lines minimum each side**:
     `orphans: 2; widows: 2`.
   - **Per-page frame** — the page frame closes at each foot and reopens at the next
     head (a per-page border via `@page`/running element, never one continuous box
     sliced by the edge).
   - **Wordmark opens, footer meta closes** — footer carries meta in the Overline
     role at the margin line (running footer); wordmark only on the opening page.
   - **45–75 character measure** on the body column; rag-right, no justified body,
     no centered body copy; hairline 1px rules divide, not heavy strokes.
8. **Embed fonts** (existing `embed_fonts.py` approach) → self-contained HTML.
9. **Chrome headless** → PDF (`--print-to-pdf`, `@page A4`), the single consistent
   PDF path for all deliverables. Verifies non-zero output.

### Testing (TDD)

`render.py` is deterministic I/O — built test-first (tdd skill) under
`tests/test_deliverable_render.py`: comment-stripping, placeholder detection
(incl. the markdown-link exclusion), markdown→HTML for each construct our templates
use, brand-book-staleness triggers a token rebuild, and `--check` exit codes. The
agent-driven end-to-end skill behaviour is evaluated separately via the
skill-creator eval loop.

## Files

```
skills/menteapex-deliverable/
  SKILL.md                     # rewritten; picker → fill → render → email
  scripts/render.py            # zero-dep renderer; reads live Brand/tokens/tokens.css
  scripts/embed_fonts.py       # vendored; resolves live fonts from Brand source
  assets/shell.html            # brand shell: identity-page + letterhead treatments (M/B grid)
  references/templates.md      # client-facing family list + which family gets the identity page
  references/email.md          # per-family email tone/subject guidance, 4 langs
```

Rename `skills/menteapex-proposal/` → `skills/menteapex-deliverable/`.

**Ripple updates:** `.claude-plugin/marketplace.json` + `plugin.json` (description,
keywords), `README.md`, and `JOURNEY.md` backlog item #2 (proposal → deliverable,
mark done). `menteapex-invoice`/`-onboarding` references stay.

## Non-goals

- No overhaul of invoice/onboarding this pass.
- No arbitrary-Markdown renderer — only the subset our templates use.
- The renderer styles a *branded Markdown document* per the book's grid; it does not
  reproduce every bespoke per-doc layout the old hand-built proposal could. Layout is
  the grid (M margins, B type scale, identity page vs letterhead) — richer treatments
  are shell changes, never hand-edited HTML.

## Open risk

The renderer reads the live `Brand/tokens/tokens.css` (plus `fonts.css`, wordmark).
If the Brand source can't be located on a given machine (e.g. `$BRAND_ROOT` unset and
no default), `render.py` warns and falls back to the last-known tokens vendored beside
the skill rather than aborting — so a render still succeeds, just flagged as
possibly-stale. Keeping the Brand path resolvable is the one operational requirement.
```