# mente-apex

Private Claude Code plugin — Mente Apex business utilities **and** cross-agent memory sync (the brain).

## Skills

### Business

| Skill | Command | What it does |
|-------|---------|-------------|
| onboarding | `/onboarding` | Create HubSpot contact/company/deal + local Customers/ folder + registry entry |
| proposal | `/proposal` | Generate branded proposal HTML/PDF from client brief |
| invoice | `/invoice` | Generate branded invoice or service contract HTML/PDF |

### Memory sync (the brain)

Keeps your Claude memory (CLAUDE.md, rules, skills, agents, memory/) in sync across
machines via a private Git repo, with smart LLM-powered merge when machines diverge.
Merged in from the former `open-memory` plugin — same engine (`scripts/brain.py`), now
shipped here.

| Skill | Command | What it does |
|-------|---------|-------------|
| memory-setup | `/memory-setup` | First time, or connecting a new machine to your brain repo |
| memory-sync | `/memory-sync` | Push/pull/merge memory across machines (run whenever you switch) |
| memory-manage | `/memory-manage` | Status, promote session notes into rules, share artifacts, sync history |

## Installation

```bash
claude plugin marketplace add menteapex/mente-apex-plugin
claude plugin install mente-apex
```

First-time memory setup (creates the `~/.claude/open-memory-repo` sync repo against a
private Git remote you control):

```
/memory-setup
```

## What memory sync does and doesn't touch

| Item | Synced |
|---|---|
| CLAUDE.md, rules/, skills/, agents/, memory/ | ✓ |
| settings.json | ✓ (env vars and API keys stripped) |
| OAuth tokens / API keys | ✗ Never |
| .claude.json | ✗ Never |

## Requirements

- `HUBSPOT_API_KEY` env var for automated HubSpot record creation (optional — falls back to manual instructions)
- Brand reference at `Customers/Tomislav/docs/` (fonts.css, proposal.html, embed_fonts.py)
- `git` + `python3` (standard library only — no pip installs) for the memory skills, plus a private Git repository to hold your brain
