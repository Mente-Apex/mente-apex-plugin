# GoF HTML report spec

Standalone visual spec for the self-contained HTML preview written alongside
the Markdown report. This file is the single source of truth for the HTML's
structure and styling — the skill build step reads it, not the other way
around.

The HTML mirrors the MD report's Detected patterns + Recommendations + Not
applicable sections; it is a gitignored artifact written after the MD.

## File

`docs/reports/gof/GOF-ANALYSIS-<YYYY-MM-DD>.html`, written in a single Write
tool call after the Markdown file exists. Fully self-contained — no CDN
scripts, external stylesheets, fonts, or remote images. All CSS lives inline
in a `<style>` block in `<head>`. No JavaScript is required; a small
`<script>` for active nav-link highlighting on scroll is allowed. The file
must open correctly in any modern browser without a local server.

## Layout

- **Sticky top header bar** — project name and generation date.
- **Dark sidebar navigation**, sticky on scroll, listing every section by
  anchor link: Executive Summary, each detected pattern by name, each
  recommendation by ID, Not Applicable.
- **Main content area**, max-width ~900px, comfortable line-height, a
  readable serif or system-ui font for body text and monospace for code.
- `scroll-behavior: smooth` on `html`.

## Grade badges

Colour-coded pill on each detected-pattern heading:

| Grade | Colour | Background | Text |
|---|---|---|---|
| A | green | `#22c55e` | white |
| B | blue | `#3b82f6` | white |
| C | amber | `#f59e0b` | white |
| D | orange | `#ef4444` | white |
| F | red | `#dc2626` | white |

## Category chips

Small outlined pills placed before the pattern name, one colour per
category:

- Creational — muted purple
- Structural — muted teal
- Behavioral — muted indigo

## Executive Summary card

Rendered as a prominent card at the top:

- Maturity level as a progress-bar-style indicator: Nascent → Emerging →
  Moderate → Mature.
- Detected patterns listed with their grade badges.
- Recommendation counts (Critical / Major / Minor) with numbered bullets for
  the top wins.

## Detected-pattern cards

One card per entry in "Detected patterns (graded inventory)":

- Coloured left border matching the grade colour.
- Labelled sub-sections (Location, Evidence, Strengths, Issues,
  Recommendation, Overlap) using small-caps labels in muted text.
- A distinct light-yellow background for the Recommendation block so it
  stands out from the rest of the card.

## Recommendation cards

One card per Critical/Major/Minor rec:

- Coloured left border by tier (Critical red, Major amber, Minor blue — kept
  distinct from the grade-badge palette so tier and grade are never
  confused).
- Labelled sub-sections matching the MD report's fields: Pattern, Location,
  Problem now, Proposed change, Expected benefit, Overlap, Risk,
  Verification, Status.
- A small status pill (`pending` / `applied` / `failed` / `skipped`) in the
  card header.
- Where the recommendation includes a before/after sketch, render it in a
  two-column layout where space allows (stacked on narrow viewports).

## Code / sketch blocks

- Dark background (`#1e1e2e`), light text (`#cdd6f4`).
- A small "BEFORE" / "AFTER" label badge in the top-right corner of each
  block.

## Not applicable grid

A clean two-column grid of small cards, each showing the pattern name and
its one-line reason — mirrors the MD report's "Not applicable" table.

## Content mapping

| HTML section | Source in the MD report |
|---|---|
| Executive Summary card | `## Summary` |
| Detected-pattern cards | `## Detected patterns (graded inventory — informational)` |
| Recommendation cards | `## Recommendations` (Critical / Major / Minor) |
| Not Applicable grid | `## Not applicable` |

Reviewer notes and the Apply log are internal to the MD workflow and are not
rendered in the HTML — the HTML is a read-only preview for humans, not a
place recommendation Status gets edited.
