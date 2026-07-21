# Client-facing deliverable families

The picker offers exactly these. Each row: the family, the `Legal/` filename pattern,
the language variants that exist, the render **kind** (`identity` = full-bleed navy
sales cover; `letterhead` = plain M-margin page), and the lifecycle stage it serves.

Resolve `Legal/` from `$BUSINESS_ROOT/Legal` (`$BUSINESS_ROOT` default
`$HOME/Documents/Business`). `<lang>` ∈ `es-ES` · `es-419` · `hr`; EN is the bare file.

| # | Family | Filename pattern | Languages | Kind | Stage |
|---|--------|------------------|-----------|------|-------|
| 1 | Initial offer (one-pager) | `initial-offer-template[-<lang>].md` | EN · es-ES · es-419 · hr | **identity** | C (default) |
| 2 | Proposal (full) | `proposal-template[-<lang>].md` | EN · es-ES · es-419 · hr | **identity** | C (escalation) |
| 3 | Engagement agreement | `engagement-agreement-template[-<lang>].md` | EN · es-ES · es-419 · hr | letterhead | D |
| 4 | IP licence — gift | `licensing-gift.md` | EN only | letterhead | D |
| 5 | IP licence — paying | `licensing-paying.md` | EN only | letterhead | D |
| 6 | IP licence — pro-bono | `licensing-pro-bono.md` | EN only | letterhead | D |
| 7 | DPA (data processing) | `dpa-template[-<lang>].md` | EN · es-ES · es-419 · hr | letterhead | D (if personal data) |
| 8 | Handover doc | `handover-template[-<lang>].md` | EN · es-ES · es-419 · hr | letterhead | D (at onboarding) |
| 9 | Update brief | `update-brief-template[-<lang>].md` | EN · es-ES · es-419 · hr | letterhead | E (per milestone) |
| 10 | Pre-production notice | `preproduction-notice[-<lang>].md` | EN · es-ES · es-419 · hr | letterhead | E/F (publish gate) |

**Naming quirks — don't guess, match these exactly:**
- Most families: `<family>-template[-<lang>].md`.
- `preproduction-notice`: **no** `-template` infix → `preproduction-notice[-<lang>].md`.
- `licensing-{gift,paying,pro-bono}`: **no** `-template`, **EN only**. If the user needs
  Spanish/Croatian here, say so — a variant would have to be authored first.

**License-tier selector (family 4–6), from JOURNEY.md:** arm's-length paying (incl.
discounted — a discount is a price line, not a licence change) → `licensing-paying`;
genuine gift/favour → `licensing-gift`; pro-bono / personal → `licensing-pro-bono`.

**Excluded from the picker (deliberately):**
- `ip-licensing-policy.md`, `trade-in-kind.md` — internal-only, never rendered for a client.
- `site-baseline/` (privacy · aviso legal · cookies) — renders into the **client's own**
  site, not the Mente Apex brand; out of scope for this skill.

**Language fallback:** if a requested `<lang>` variant is missing for a family, fall back
to EN and tell the user, rather than failing.
