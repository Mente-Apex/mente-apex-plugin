---
name: menteapex-proposal
description: >
  Generate a branded Mente Apex proposal PDF for a client engagement.
  Follows brand-book conventions: navy cover, Cormorant + DM Sans, gold-dot system.
  Use whenever the user says "generate a proposal", "write a proposal", "create a
  proposal for <client>", "proposal from brief", or "/proposal".
user-invocable: true
allowed-tools: Bash, Read, Write, Edit
---

# Proposal Generator

Produces a branded HTML proposal derived from the brand book. The reference build
lives in the brand-reference dir (`$BRAND_REF`, see Paths below) — start from that
CSS skeleton, swap the content.

> **Paths (portable).** Resolve the business folder from `$BUSINESS_ROOT`
> (default `$HOME/Documents/Business`) and the brand reference from `$BRAND_REF`
> (default `$BUSINESS_ROOT/Customers/Tomislav/docs` — the reference-client build).
> Set either env var to relocate on another machine. No absolute `/Users/...` paths.

---

## Step 1 — Gather inputs

You need:
- **Client name and company**
- **Engagement slug** (from client registry or provided by user)
- **Problem statement** — what pain are they trying to solve?
- **Proposed solution** — what will Mente Apex build/deliver?
- **Deliverables** — concrete list of what they receive
- **Timeline** — phases and approximate weeks
- **Investment** — fee(s), payment structure
- **Next step** — what the client must do to proceed

If a brief file exists at `Customers/<ClientName>/customer_input/`, read it first
and extract as much of the above as possible before asking.

---

## Step 2 — Read the reference build

Read these files to load the visual system before writing a single line of HTML:

```
$BRAND_REF/fonts.css
$BRAND_REF/proposal.html
```

Do not deviate from the CSS variable system, grid, or typography defined there.
The visual language is fixed — only the content changes.

---

## Step 3 — Write the proposal HTML

Save to: `Customers/<ClientName>/docs/proposal.html`

Structure (in order):

1. **Cover page** — full-bleed navy, Mente Apex wordmark, client name, date, tagline
2. **Situation** — their problem, restated with clarity and empathy (2–3 paragraphs)
3. **Our approach** — the solution methodology, structured as phases if applicable
4. **Deliverables** — bulleted list, specific and concrete
5. **Timeline** — visual phases table (weeks/milestones)
6. **Investment** — clear fee table, payment milestones, what's included
7. **Next steps** — one clear CTA
8. **About Mente Apex** — 2–3 sentence credential statement (pull from brand book voice)

Copy `fonts.css` from the brand reference (`$BRAND_REF/fonts.css`) into
`$BUSINESS_ROOT/Customers/<ClientName>/docs/fonts.css`.

---

## Step 4 — Generate PDF

The HTML is an intermediate asset. The deliverable is the PDF.

First, embed fonts so the PDF renders correctly without a network connection:

```bash
BUSINESS_ROOT="${BUSINESS_ROOT:-$HOME/Documents/Business}"
BRAND_REF="${BRAND_REF:-$BUSINESS_ROOT/Customers/Tomislav/docs}"
DOCS="$BUSINESS_ROOT/Customers/<ClientName>/docs"

# Copy embed_fonts.py from the brand reference if not present
[ -f "$DOCS/embed_fonts.py" ] || cp "$BRAND_REF/embed_fonts.py" "$DOCS/"

# Embed fonts into a self-contained HTML
python3 "$DOCS/embed_fonts.py" "$DOCS/proposal.html" > "$DOCS/proposal-print.html"
```

Then render to PDF via Chrome headless:

```bash
PDF_NAME="Mente-Apex-Proposal-<ClientName>-$(date +%Y-%m-%d).pdf"
PDF_PATH="$DOCS/$PDF_NAME"

"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless=new \
  --run-all-compositor-stages-before-draw \
  --print-to-pdf="$PDF_PATH" \
  --print-to-pdf-no-header \
  --no-pdf-header-footer \
  "file://$DOCS/proposal-print.html" 2>/dev/null

echo "PDF: $PDF_PATH"
```

If Chrome is not at that path, try:
```bash
which google-chrome-stable || which chromium || ls /Applications/ | grep -i chrome
```
and adjust accordingly.

Verify the PDF exists and has a non-zero size:
```bash
ls -lh "$PDF_PATH"
```

---

## Step 5 — Confirm

Report the full PDF path. That is the deliverable — hand it to the user directly.
Note any sections that still need review before sending to the client.
