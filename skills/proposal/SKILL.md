---
name: proposal
description: >
  Generate a branded Mente Apex proposal (HTML + PDF) for a client engagement.
  Follows brand-book conventions: navy cover, Cormorant + DM Sans, gold-dot system.
  Use whenever the user says "generate a proposal", "write a proposal", "create a
  proposal for <client>", "proposal from brief", or "/proposal".
user-invocable: true
allowed-tools: Bash, Read, Write, Edit
---

# Proposal Generator

Produces a branded HTML proposal derived from the brand book. The reference build
is `Customers/Tomislav/docs/proposal.html` + `fonts.css` — start from that CSS
skeleton, swap the content.

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
/Users/ai/Documents/Business/Customers/Tomislav/docs/fonts.css
/Users/ai/Documents/Business/Customers/Tomislav/docs/proposal.html
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

Copy `fonts.css` from the Tomislav reference into `Customers/<ClientName>/docs/fonts.css`.

---

## Step 4 — Generate PDF

Run:

```bash
cd /Users/ai/Documents/Business/Customers/<ClientName>/docs/
python embed_fonts.py proposal.html > proposal-embedded.html 2>/dev/null || echo "embed_fonts not available"
```

If `embed_fonts.py` doesn't exist yet, copy it from the Tomislav reference:

```bash
cp /Users/ai/Documents/Business/Customers/Tomislav/docs/embed_fonts.py \
   /Users/ai/Documents/Business/Customers/<ClientName>/docs/
```

Then open in browser for PDF export:

```bash
open /Users/ai/Documents/Business/Customers/<ClientName>/docs/proposal.html
```

Tell the user: "Open the file in Chrome/Safari → File → Print → Save as PDF. Name it
`Mente-Apex-Proposal-<ClientName>-<YYYY-MM-DD>.pdf`."

---

## Step 5 — Confirm

Report: file path of the HTML, PDF instructions, any sections that need user input
before it's client-ready.
