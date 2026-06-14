---
name: menteapex-invoice
description: >
  Generate a branded Mente Apex invoice or contract (HTML + PDF) for a client.
  Follows brand-book conventions. Use whenever the user says "create an invoice",
  "generate an invoice", "draft a contract", "service agreement", "invoice for
  <client>", or "/invoice".
user-invocable: true
allowed-tools: Bash, Read, Write, Edit
---

# Invoice & Contract Generator

Produces branded documents derived from the brand book CSS system.
Two modes: **Invoice** (billing) and **Contract** (service agreement).

---

## Step 1 — Determine document type

Ask: invoice or contract (or both)?

**Invoice inputs:**
- Client name, company, billing address
- Invoice number (format: `MA-YYYY-NNN`, e.g. `MA-2026-001`)
- Invoice date and due date (default: net 30)
- Line items: description, quantity, unit price
- VAT / tax treatment (see note below)
- Payment instructions (bank transfer details or payment link)

**Contract inputs:**
- Client name and legal entity name
- Engagement description (what Mente Apex will deliver)
- Start date and estimated duration
- Fee and payment schedule
- Governing law (default: España / Spanish law)
- Special terms (IP ownership, confidentiality, etc.)

**VAT note:** For Spanish clients, apply IVA (21%) unless they provide a valid
NIF with reverse-charge exemption. For EU business clients outside Spain, apply
reverse charge (0% IVA, client self-assesses). For non-EU clients, no IVA.
When in doubt, ask the user.

---

## Step 2 — Read the reference build

Load the visual system:

```
/Users/ai/Documents/Business/Customers/Tomislav/docs/fonts.css
/Users/ai/Documents/Business/Customers/Tomislav/docs/proposal.html
```

Use the same CSS variables, grid, and typography. Invoices and contracts use a
simpler layout (no full-bleed cover, no phases table) but must match the same
typeface, color system (navy headers, Deep Gold accents), and hairline-rule style.

---

## Step 3 — Write the document

Save to: `Customers/<ClientName>/docs/<type>-<MA-number>-<YYYY-MM-DD>.html`

**Invoice structure:**
1. Header — Mente Apex name/address on left, "FACTURA / INVOICE" + number on right
2. Client block — billing name, address, NIF/VAT if applicable
3. Dates — invoice date, due date
4. Line items table — description | qty | unit | total (with gold-line header row)
5. Subtotal, IVA/VAT row, **Total** (bold, navy background)
6. Payment instructions
7. Footer — NIF, bank details, legal notice

**Contract structure:**
1. Cover — client name, "ACUERDO DE SERVICIOS / SERVICE AGREEMENT", date
2. Parties — Mente Apex and client legal names, addresses
3. Scope of work — deliverables, what's explicitly excluded
4. Fees and payment schedule
5. Timeline
6. IP and confidentiality
7. Termination
8. Governing law
9. Signatures block

---

## Step 4 — Generate PDF

Copy fonts.css from reference if not already present:

```bash
cp /Users/ai/Documents/Business/Customers/Tomislav/docs/fonts.css \
   /Users/ai/Documents/Business/Customers/<ClientName>/docs/ 2>/dev/null || true
```

Open for PDF export:

```bash
open /Users/ai/Documents/Business/Customers/<ClientName>/docs/<filename>.html
```

Tell the user: "Print → Save as PDF in Chrome/Safari. File name already set."

---

## Step 5 — Confirm

Report: file path, document type, total amount (invoice) or key terms (contract).
Flag anything that needs user review before sending to client.
