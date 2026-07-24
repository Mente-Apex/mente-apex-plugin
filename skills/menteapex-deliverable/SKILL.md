---
name: menteapex-deliverable
version: 0.21.0
description: >
  Produce any client-facing Mente Apex deliverable — initial offer, proposal,
  engagement agreement, IP licence, DPA, handover, update brief, or pre-production
  notice — as on-brand HTML + PDF from the Legal/ Markdown source of truth, then draft
  the client email. Picks the template, picks the language (EN / es-ES / es-419 / hr),
  fills every placeholder, and renders. Use whenever the user says "generate a
  proposal", "make the offer", "draft the engagement agreement", "render the DPA /
  licence / handover / update brief", "create a deliverable for <client>", or
  "/deliverable".
user-invocable: true
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion
---

# Client Deliverable Generator

Turns a `Legal/` Markdown template (the source of truth) into an on-brand HTML + PDF
deliverable, and drafts the accompanying client email. The visual system is **not
hand-built** — `scripts/render.py` derives it from the live brand book each run. Your
job is to choose the right template, fill it completely, and render.

> **Why a script renders, not you.** JOURNEY.md's standing rule: *MD is source, HTML/PDF
> is derived, never hand-edited — change the MD, re-render.* Do not write HTML by hand.
> Fill Markdown; let `render.py` apply the brand.

> **Paths (portable).** Business folder = `$BUSINESS_ROOT` (default
> `$HOME/Documents/Business`); brand source = `$BRAND_ROOT` (default
> `$BUSINESS_ROOT/Brand`). Templates live in `$BUSINESS_ROOT/Legal`. No absolute
> `/Users/...` paths.

---

## Step 1 — Choose the deliverable

Read `references/templates.md` — it lists the ten client-facing families, their exact
filename patterns, available languages, and render **kind** (`identity` vs `letterhead`).
Ask the user which family (use `AskUserQuestion` with the family list) unless the request
already names it. Apply the **license-tier selector** for families 4–6.

Then confirm the **language** (EN / es-ES / es-419 / hr). Load the matching variant;
if it doesn't exist for that family, fall back to EN and say so.

---

## Step 2 — Locate the client and gather inputs

Identify the client folder `Customers/<Client>/`. Before asking the user anything, read
what's already known so you don't re-ask:

- `Customers/<Client>/customer_input/` — their brief, texts, scope notes.
- The client registry (`~/Brain/docs/clients.md`) and `Customers/<Client>/PROJECT.md` —
  slug, contact, email, engagement details.

Copy the chosen template to a working file in the client's docs dir, e.g.
`Customers/<Client>/docs/<family>-<slug>.md`. **Work on the copy — never edit the
template in `Legal/`.**

---

## Step 3 — Fill every placeholder (do not stop early)

Templates mark fill-in slots as `[bracketed prose]` (e.g. `[Client / business]`,
`[date]`, `[€X]`) and carry `<!-- HTML comment -->` guidance blocks that are
**instructions to you — strip them, never render them**. Fill the copy from the inputs;
ask the user for anything you can't source. Honour each template's guidance comment
(tier, discount reason, consumer-vs-professional clause, etc.) as you fill.

**Weave in customer-specific prose.** Content a client needs that the template has no
`[placeholder]` for — extra scope, a bespoke clause, notes pulled from
`Customers/<Client>/customer_input/` — is added to **the copy**, never the template. You
supply the formatting judgement; a helper does the mechanical placement:

1. **Source the text** from `customer_input/` or the user's message. Raw prose is fine —
   no structure required from them.
2. **Choose the section.** Propose the target heading (its exact heading line) and
   **confirm with the user** before inserting — placement is a decision, never a silent
   guess.
3. **Reformat to the renderer's subset.** `render.py` supports only headings,
   ordered/unordered lists (one level), GFM pipe tables, blockquotes, `**bold**` /
   `*italic*`, links, and `---`. Anything outside it is silently dropped — reformat the
   prose *to this subset*, matching the template's idiom, before inserting.
4. **Insert mechanically** so a hand-edit can't mangle the copy — `insert_block.py`
   places the block at the **end of that heading's section** and refuses (non-zero,
   nothing written) if the anchor is missing or ambiguous:

   ```bash
   printf '%s\n' "<your reformatted markdown block>" | \
     python3 "$CLAUDE_PLUGIN_ROOT/skills/menteapex-deliverable/scripts/insert_block.py" \
       --file "Customers/<Client>/docs/<family>-<slug>.md" --after-heading "## Scope"
   ```

5. **Show the woven block and where it landed, then confirm** before rendering. For the
   legal families (engagement agreement, licence, DPA) this human gate is **mandatory** —
   never insert bespoke legal prose autonomously.

**The completeness gate — this is non-negotiable.** A half-filled deliverable must never
reach the client. Verify mechanically and loop until clean:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/skills/menteapex-deliverable/scripts/render.py" \
  "Customers/<Client>/docs/<family>-<slug>.md" --check
```

`--check` exits non-zero and lists every remaining `[placeholder]`. Keep filling and
re-running until it prints `✓ no placeholders remain`. (Markdown links `[text](url)` are
not placeholders; guidance-comment brackets are ignored because comments are stripped
first.)

---

## Step 4 — Render to HTML + PDF

```bash
python3 "$CLAUDE_PLUGIN_ROOT/skills/menteapex-deliverable/scripts/render.py" \
  "Customers/<Client>/docs/<family>-<slug>.md" \
  --kind <identity|letterhead> --lang <en|es-ES|es-419|hr> \
  --title "<document title>" --out "Customers/<Client>/docs"
```

Use the **kind** from `references/templates.md` (offers/proposals = `identity`; the rest =
`letterhead`). The renderer reads the live `Brand/tokens/tokens.css` each run, so output
tracks the current brand book; if it warns that tokens are stale, pass the nudge to the
user (they may want to run `Brand/tokens/build_tokens.py` first). It embeds fonts and
prints the PDF via headless Chrome. If Chrome isn't found it still writes the HTML and
says so.

Confirm the PDF exists and is non-zero (the renderer reports both paths).

---

## Step 5 — Draft the client email

Read `references/email.md` for the per-family subject + tone (and the tú/usted and
contact-canon rules). Draft a short covering note in the deliverable's language.

- If the Gmail connector (`mcp__claude_ai_Gmail__*`) is available this session, create a
  **draft** (never send) to the client's address (from the registry / `PROJECT.md`, or
  ask), referencing the PDF.
- Otherwise, output the finished **subject + body** for the user to paste.

Never auto-send. Always hand back the PDF path.

---

## Step 6 — Confirm

Report: family + language, the PDF path, whether the email was drafted or is paste-ready,
and anything that still needs the user's review before it goes to the client (e.g. a
figure you inferred, a clause you filled from assumption).
