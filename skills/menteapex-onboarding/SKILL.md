---
name: menteapex-onboarding
description: >
  Onboard a new Mente Apex client end-to-end: collect their details, create a
  HubSpot contact + company, create the Customers/<Name>/ folder with the
  standard structure, create the PROJECT.md pointer, and add them to the client
  registry. Use this skill whenever the user says things like "onboard a new
  client", "add a client", "new client setup", "create a client folder", or
  "/onboarding".
user-invocable: true
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion
---

# Client Onboarding

Two steps: (1) HubSpot, (2) local filesystem. Always do both in the same session.

---

## Step 1 — Collect client info

Ask the user for:
- **Client/company name** (used as the folder name — Title Case, no spaces → use underscores if needed)
- **Contact person** (first + last name)
- **Email**
- **Phone** (optional)
- **Engagement type** (e.g. consulting, automation build, custom AI dev)
- **Slug** — suggest one: lowercase, hyphens, descriptive of the work (e.g. `inventory-ai-agent`). Confirm with user.
- **Brief description** of the project (one sentence)

---

## Step 2 — HubSpot

Check for a HubSpot API key:

```bash
echo $HUBSPOT_API_KEY
```

### If API key is present — create via API

**Create or find the company:**

```bash
curl -s -X POST "https://api.hubapi.com/crm/v3/objects/companies" \
  -H "Authorization: Bearer $HUBSPOT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "properties": {
      "name": "<ClientName>",
      "industry": "Other",
      "description": "<brief description>"
    }
  }'
```

Save the returned `id` as `COMPANY_ID`.

**Create the contact and associate with the company:**

```bash
curl -s -X POST "https://api.hubapi.com/crm/v3/objects/contacts" \
  -H "Authorization: Bearer $HUBSPOT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "properties": {
      "firstname": "<FirstName>",
      "lastname": "<LastName>",
      "email": "<email>",
      "phone": "<phone>",
      "company": "<ClientName>"
    },
    "associations": [
      {
        "to": {"id": "<COMPANY_ID>"},
        "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 1}]
      }
    ]
  }'
```

**Create a Deal** (to track the engagement):

```bash
curl -s -X POST "https://api.hubapi.com/crm/v3/objects/deals" \
  -H "Authorization: Bearer $HUBSPOT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "properties": {
      "dealname": "<slug> — <ClientName>",
      "dealstage": "appointmentscheduled",
      "pipeline": "default"
    },
    "associations": [
      {
        "to": {"id": "<COMPANY_ID>"},
        "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 5}]
      }
    ]
  }'
```

Report back: contact ID, company ID, deal ID, and a direct HubSpot URL if available.

### If no API key — manual instructions

Tell the user:

> No HUBSPOT_API_KEY found. Please create the contact manually:
> 1. Go to Contacts → Create contact
> 2. Fill in: name, email, phone, company
> 3. Create a Company record and associate
> 4. Create a Deal named `<slug> — <ClientName>` and set stage to "Appointment Scheduled"
>
> To automate this in future, add your HubSpot private app key:
> `export HUBSPOT_API_KEY=your_key_here` in your shell profile.

---

## Step 3 — Local folder

Create the standard customer folder structure:

```
/Users/ai/Documents/Business/Customers/<ClientName>/
├── PROJECT.md
├── customer_input/
└── docs/
```

**PROJECT.md template:**

```markdown
# <ClientName> — Projects

> Pointer only. Truth lives in the registry + per-engagement file.

| slug | what | repo | memory |
|------|------|------|--------|
| `<slug>` | <brief description> | `~/Projects/<slug>` | `memory/projects/<slug>.md` |

Registry: [`../../memory/projects/clients.md`](../../memory/projects/clients.md)

This folder holds the relationship record — proposals (`docs/`) and client intake (`customer_input/`).
Code and engineering specs live in the repo above, outside the Business folder.
```

---

## Step 4 — Registry + memory

**Add to client registry** (`/Users/ai/Documents/Business/memory/projects/clients.md`):

Add a row to the Registry table:

```
| `<slug>` | <ClientName> | ⚪ scoping / pre-contract | `~/Projects/<slug>` | `Customers/<ClientName>/docs/` | <today's date> |
```

**Create per-engagement memory file** (`/Users/ai/Documents/Business/memory/projects/<slug>.md`):

```markdown
# <slug>

**Customer:** <ClientName>
**Contact:** <FirstName> <LastName> (<email>)
**Started:** <date>
**Status:** ⚪ scoping / pre-contract

## Engagement
<brief description>

## HubSpot
- Contact ID: <id or "see HubSpot">
- Company ID: <id or "see HubSpot">
- Deal ID: <id or "see HubSpot">

## Notes

```

---

## Step 5 — Confirm

Report back a summary:
- HubSpot records created (or manual steps given)
- Folder path created
- Registry updated
- Memory file path

Tell the user: "Ready to start. Next steps: collect a brief → generate proposal."
