# mente-apex

Private Claude Code plugin — Mente Apex business utilities.

## Skills

| Skill | Command | What it does |
|-------|---------|-------------|
| onboarding | `/onboarding` | Create HubSpot contact/company/deal + local Customers/ folder + registry entry |
| proposal | `/proposal` | Generate branded proposal HTML/PDF from client brief |
| invoice | `/invoice` | Generate branded invoice or service contract HTML/PDF |

## Installation

```bash
claude plugin marketplace add bvujicic/mente-apex-plugin
claude plugin install mente-apex
```

## Requirements

- `HUBSPOT_API_KEY` env var for automated HubSpot record creation (optional — falls back to manual instructions)
- Brand reference at `Customers/Tomislav/docs/` (fonts.css, proposal.html, embed_fonts.py)
