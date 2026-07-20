# mente-apex

Private Claude Code plugin — Mente Apex business utilities **and** Claude config sync across machines.

## Skills

### Business

| Skill | Command | What it does |
|-------|---------|-------------|
| menteapex-onboarding | `/menteapex-onboarding` | Create HubSpot contact/company/deal + local Customers/ folder + registry entry |
| menteapex-proposal | `/menteapex-proposal` | Generate branded proposal HTML/PDF from client brief |
| menteapex-invoice | `/menteapex-invoice` | Generate branded invoice or service contract HTML/PDF |

### Dev workflow

| Skill | Command | What it does |
|-------|---------|-------------|
| ship | `/ship` | Branch (if on main) → commit (Conventional Commits) → push → open PR, with one confirmation before anything goes public |
| clean-code | `/clean-code` | Clean-code standard for the repo — ranked principles (with the places they should bend) that guide Claude when writing code here, and drive read-only reviews with `file:line` + severity when checking a diff or PR |
| solid | `/solid [path]` | SOLID analysis & guided refactor: analyzer drafts findings → independent reviewer verifies and writes a tiered refactor plan (Critical/Major/Minor) → after human sign-off, an implementer applies recs one at a time with the full test suite run after each change |
| tdd | `/tdd` | Test-driven development: strict red-green-refactor (one test at a time) with a requirements interview up front; feature + legacy-code modes (characterization pins before touching untested code), Python/pytest adapter, refactor handoffs to `/clean-code` and `/solid`. Other skills can invoke it programmatically to get code built test-first. Bugs are out of scope (they belong to a debug skill) |
| gof | `/gof [path]` | Gang of Four pattern analysis & guided refactor: analyzer detects + grades existing patterns (A–F) and proposes where unimplemented patterns genuinely help → independent reviewer verifies, tiers (Critical/Major/Minor) and cross-references `/solid` → after sign-off, approved changes are applied through the TDD refactor engine, suite green after each. Produces a Markdown report + self-contained HTML preview in `gof-reports/` |
| clean-architecture | `/clean-architecture [path]` | Clean Architecture component/dependency audit: analyzer checks the Dependency Rule and component principles (ADP/SDP/SAP, REP/CCP/CRP) → independent reviewer verifies and tiers findings (Critical/Major/Minor) → after sign-off, approved changes are applied through the TDD refactor engine, suite green after each. Audit-first (no build mode); degrades gracefully without `grimp`/`import-linter` |

> **Convention for code-modifying skills** ([docs/git-convention.md](docs/git-convention.md)):
> a `<skill>/<slug>` working branch is opened before the first edit, and at the end the
> skill *offers* — never auto-runs — a commit + PR (typically by handing off to `/ship`).
> `/solid`, `/gof`, and `/clean-architecture` apply their changes through `/tdd`'s programmatic refactor job and cross-reference each other via `docs/lens-overlap.md`.

### Config sync

Keeps your Claude **config files** (CLAUDE.md, rules, skills, agents, the `memory/`
files, settings.json) in sync across machines via a private Git repo, with a structured
section-aware merge when machines diverge (optional LLM merge via
`CONFIG_SYNC_LLM_MERGE=1`). Engine: `scripts/config_sync.py`.

| Skill | Command | What it does |
|-------|---------|-------------|
| config-sync-setup | `/config-sync-setup` | First time, or connecting a new machine to your config-sync repo |
| config-sync | `/config-sync` | Push/pull/merge config across machines (run whenever you switch) |
| config-sync-manage | `/config-sync-manage` | Status, promote session notes into rules, share artifacts, sync history |

> **Two different systems, don't confuse them.** *Config sync* (above) moves your
> `~/.claude` config files between machines. **Mente Apex memory** — the `mem` CLI and
> the `mente-apex-memory` MCP server — is the knowledge brain that captures and recalls
> facts and has its own `mem sync`. Config sync is not the brain.

## Installation

```bash
claude plugin marketplace add menteapex/mente-apex-plugin
claude plugin install mente-apex
```

> **Fresh-machine bootstrap.** Config sync propagates your `~/.claude` *content*, but
> the plugin's own skills and `config_sync.py` engine are **not** part of a snapshot —
> they live in the plugin cache. On a new machine you must run the two install lines
> above **before** `/config-sync-setup`, otherwise there is nothing to run the sync.

First-time config-sync setup (creates the `~/.claude/config-sync-repo` sync repo against
a private Git remote you control):

```
/config-sync-setup
```

> Upgrading from the old `open-memory` naming? The first run of `/config-sync-setup` or
> `/config-sync` auto-migrates your legacy `~/.claude/open-memory-*` paths to
> `config-sync-*` (idempotent — a no-op once migrated).

## What config sync does and doesn't touch

| Item | Synced |
|---|---|
| CLAUDE.md, rules/, skills/, agents/, memory/ | ✓ |
| settings.json | ✓ (env vars and API keys stripped) |
| OAuth tokens / API keys | ✗ Never |
| .claude.json | ✗ Never |

**Note:** Skill/agent **deletions** now propagate — a retired skill on one machine is proposed for removal on the others (consent-gated); snapshot config remains union-only. To remove **config content** (a memory, rule, or CLAUDE.md section) across the network you must delete it on every machine and from the consolidated snapshot. See `/config-sync` for details.

## Requirements

- `HUBSPOT_API_KEY` env var for automated HubSpot record creation (optional — falls back to manual instructions)
- Business skills resolve paths from `$BUSINESS_ROOT` (default `$HOME/Documents/Business`)
  and the brand reference from `$BRAND_REF` (default `$BUSINESS_ROOT/Customers/Tomislav/docs`,
  holding fonts.css, proposal.html, embed_fonts.py). Override either to run on another machine.
- `git` + `python3` (standard library only — no pip installs) for the config-sync skills, plus a private Git repository to hold your config
