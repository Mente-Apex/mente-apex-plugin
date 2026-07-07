# Audit — config_sync.py & plugin design (2026-07-07)

Probe of the `mente-apex` plugin. The skill layer (Markdown) is well-built; the risk is
concentrated in the one executable file, `scripts/config_sync.py`. Findings 1–3 were
**confirmed by running the engine** against a throwaway `$HOME`, not just by reading.

Severity legend: **Critical** = data loss / security · **Major** = correctness ·
**Design** = dogfooding / architecture · **Polish** = consistency / portability.

---

## Critical

### C1 — `/config-sync` wipes local API keys from `settings.json` (CONFIRMED)
- **Where:** `_clean_settings` strips the `env` block + secret keys (`config_sync.py:171-178`);
  `cmd_import` then writes the scrubbed `settings.json` straight back over the live local
  file (`config_sync.py:252-271`, write at `:268`). `/config-sync` Step 4 imports the
  consolidated snapshot on every run (`skills/config-sync/SKILL.md:211`).
- **Why it breaks:** export is *asymmetric* with import — export scrubs secrets, import
  blindly overwrites. Local `env` (ANTHROPIC_API_KEY, custom vars) and `apiKeyHelper` are
  destroyed on every sync.
- **Proof:** round-trip of a settings.json containing `ANTHROPIC_API_KEY` / `MY_FLAG` /
  `apiKeyHelper` returned `{"model":..., "permissions":..., "enabledPlugins":...}` — env
  and apiKeyHelper gone.
- **Fix:** on import, deep-merge the incoming `settings.json` into the existing local one;
  never let a scrubbed snapshot delete keys it deliberately omitted. Re-graft the live
  local `env`/secret keys after applying non-secret fields.

### C2 — Path traversal on import (CONFIRMED)
- **Where:** `cmd_import` builds `dest = CLAUDE_DIR / rel` (`config_sync.py:263`); the guard
  (`:260`) checks known prefixes only, not `../`. Same shape in `cmd_apply_shared`.
- **Why it breaks:** a snapshot key `../../ESCAPED.txt` writes outside `~/.claude`; an
  absolute key `/etc/...` wins outright (`Path / "/abs"` discards the left side).
- **Proof:** importing a key `../../ESCAPED_OUTSIDE_CLAUDE.txt` wrote the file two levels
  above `~/.claude` and reported it as `applied`.
- **Fix:** after resolving, assert `dest.resolve().is_relative_to(CLAUDE_DIR.resolve())`
  and skip anything that isn't. Defense-in-depth (snapshots come from your own repo) but
  one bad/hand-edited snapshot writes arbitrary files as you.

---

## Major

### M3 — Fallback merge fabricates conflicts and drops new content (CONFIRMED)
- **Where:** `_section_union` contradiction test keys on `line.strip().split()[0]`
  (`config_sync.py:494-521`, esp. `:498-503`). Fires whenever `claude` CLI is missing or
  times out (90s) in `_smart_merge_text` (`:413-431`).
- **Why it breaks:** any two Markdown bullets both starting with `-` are treated as
  contradictions. A genuinely-new, non-conflicting bullet gets swallowed into a bogus
  conflict block instead of being merged in.
- **Proof:** merging two normal CLAUDE.md variants flagged `- Prefers light mode` as
  conflicting with `- Prefers dark mode` (spurious) AND lost the new `- Enable telemetry`
  bullet into a fake conflict.
- **Fix:** drop the first-token contradiction heuristic for list content; union unique
  lines. Detect true key/value contradictions only on `key:`-prefixed non-list lines.

### M4 — "Most recent wins" is really "last filename alphabetically wins"
- **Where:** `_deep_merge_json` scalar rule commented "more recent machine's value"
  (`config_sync.py:393-394`); merge order is the shell glob `for snap in machines/*.json`
  (`skills/config-sync/SKILL.md:183`) — alphabetical by machine-id, not timestamp.
- **Why it matters:** conflicting settings.json scalars resolve by filename sort order.
  Snapshots carry a `timestamp` that nothing uses.
- **Fix:** sort the merge queue by snapshot `timestamp` so recency actually decides.

### M5 — Nested `claude -p` inside an active Claude session
- **Where:** `_smart_merge_text` (`:413`) and `cmd_promote` (`:794`) shell out to
  `claude -p`. `/config-sync` runs *inside* Claude Code.
- **Why it matters:** spawns a nested Claude per differing file, sequentially, each with a
  90–120s timeout and token cost, each potentially re-triggering SessionStart hooks. Works
  small, becomes a cost/latency dead-end as config grows.
- **Fix:** cap concurrency/count; prefer a non-LLM structured merge for common cases, LLM
  only for true prose conflicts.

---

## Design & dogfooding

### D6 — `export` mutates local state (violates the plugin's own Clean-Code #6)
- `cmd_export` writes reconciled `settings.json` back to disk (`:214`) and `rmtree`s stale
  plugin cache dirs (`_prune_stale_plugin_cache`, `:159`). A `query`-named command with
  destructive side effects — and `cmd_backup` calls it *precisely because backup should be
  safe before destructive ops* (`:544`). Split reconcile/prune into an explicit command.

### D7 — Zero unit tests for the engine
- Plugin ships `/tdd`, `/solid`, `/clean-code`, but its 900-line `config_sync.py` has no
  tests; `evals/*.json` test skill *prompts*, not the Python. C1/M3/M4 are exactly what a
  round-trip test catches. Sharpest dogfooding gap — the sync engine should be the
  most-tested file and is the least.

### D8 — Shared-plugin sync bloats the repo + formatting churn
- `/config-sync` copies each installed plugin's entire cache into `shared/plugins/` and
  commits it. `apply-shared` writes `installed_plugins.json` with `indent=4` (`:646`) while
  the export path uses `indent=2` — machines fight over formatting, every sync churns.

### D9 — Fixed `/tmp` paths in the sync skill
- `skills/config-sync/SKILL.md:180,189,190` use `/tmp/config-sync-base.json` etc.
  Predictable names in a world-writable dir → collision between concurrent syncs + classic
  symlink pre-plant. Use `mktemp`.

---

## Polish & portability

- **P10 — Version drift:** `.claude-plugin/marketplace.json:11` says `0.5.0`;
  `.claude-plugin/plugin.json:3` says `0.7.0`.
- **P11 — `/ship` hardcodes co-author trailer** `Claude Opus 4.8`
  (`skills/ship/SKILL.md:52,152`); conflicts with the harness default and any other model.
- **P12 — Business skills aren't portable:** absolute paths
  `/Users/ai/Documents/Business/Customers/…` and hardcoded reference client "Tomislav"
  (`menteapex-proposal/SKILL.md:42`, `menteapex-onboarding/SKILL.md:126`). Ironic in a
  plugin whose other half is cross-machine sync.
- **P13 — Public-repo detection overpromises:** `config-sync-setup/SKILL.md:71` warns only
  "if the URL looks public" — a URL can't reveal that reliably. Always warn instead.

## Verified non-issues

- Union-only merge / deletions-not-propagating — documented three times; known trade-off.
- Secret-scan-before-push, backup-before-import, migrate idempotency — behave correctly.

---

## Follow-up — plugin & skill propagation (2026-07-07)

Investigated whether locally-built plugins/skills actually sync, and whether marketplaces
are refreshed first. Two channels exist and local content falls through both.

- Snapshot channel (every sync): CLAUDE.md, memory, rules, skills, agents, settings —
  `.md/.json/.txt` only.
- Shared channel (`shared/plugins`, manual `share`): plugins + explicitly-shared skills —
  all files, but first-time-only.

### PS1 — No marketplace refresh in the sync cycle (CONFIRMED)
- Only `claude plugin` commands in the plugin are the README install lines. The sync cycle
  never runs `claude plugin marketplace update` or `install/update`. It snapshots the
  currently-installed local copy and propagates that. Marketplace updates never pulled.

### PS2 — Locally-built skill assets are dropped (CONFIRMED)
- `_collect_dir` filters to `.md/.json/.txt` (`config_sync.py:103`). A skill with
  `scripts/engine.py` + `fonts.css` + `template.html` exported with **only SKILL.md** in
  the snapshot. Multi-file skills arrive on the other machine as non-working shells.
- Trap: the manual `/config-sync-manage share` path uses `cp -r` (all files), so the
  *automatic* snapshot path breaks multi-file skills while the *manual* path works — the
  opposite of the intuitive expectation.

### PS3 — Local plugin updates never propagate (CONFIRMED by logic)
- Export skips if `shared/plugins/<key>` exists (`config-sync/SKILL.md:99`) → newer local
  build never re-exported.
- `apply-shared` skips if the plugin key is already installed (`config_sync.py:619`) →
  other machines never receive a new version.
- Net: new plugins install exactly once, then freeze. Rebuilds don't reach other machines.

### PS4 — Root cause: two responsibilities conflated behind one strategy
- Marketplace-sourced-unmodified plugins want **manifest / desired-state** propagation
  (record `{key, marketplace, version}`; on apply run marketplace update + install/update).
- Locally-authored / private / offline content wants **content-bundle** propagation
  (all files, hash-gated so updates flow).
- Current code does only "copy the live cache," inline in a SKILL heredoc (untestable).
- Fix (SOLID): one `Propagator` seam — `export(local_state)->artifact` /
  `apply(artifact)->changes`; sync cycle iterates a list of propagators
  (`SnapshotPropagator`, `MarketplacePropagator`, `ContentBundlePropagator`). Open/closed
  for a 4th channel; each propagator unit-testable (ties into D7).

### PS-caveat — the cache lags the source repo
- The "live `~/.claude`" copy of a plugin is the installed cache = source repo at *install
  time*. Uncommitted source edits aren't reflected until reinstall. Reading the Claude
  location (not the repo) is correct for intent, but only reflects installed state.

## Skill-layer findings — the 3 config SKILL.md files (2026-07-07)

Orchestration-layer issues, separate from the engine.

### SK1 — Plugin round-trip split across layers, asymmetrically (flagship)
- Import is an engine command (`cmd_apply_shared`, `config_sync.py:554`); export is a
  55-line Python heredoc in `config-sync/SKILL.md:82-137` (no `export-plugins` in engine).
- Violates the engine's own docstring ("All file manipulation lives here so SKILL.md files
  stay clean"). Export half is untestable and re-parsed as shell every run.
- Fix: add `config_sync.py export-plugins <repo>`, symmetric with `apply-shared`.

### SK2 — `config-sync` allowed-tools omits AskUserQuestion at its critical moment
- Frontmatter `Bash, Read, Write, Edit` (`:11`), no AskUserQuestion — but body drives the
  scan-gate "Continue anyway?" (`:63`) and conflict resolution "Which should win?" (`:303`).
  setup + manage both allowlist it; sync doesn't. Fix: add AskUserQuestion to config-sync.

### SK3 — Secret-scan gate duplicated across skills (DRY)
- Identical warnings+preview+"Continue anyway?" block in `config-sync:55-63` and
  `config-sync-setup:88-96`. Fold into an engine `scan --gate` or shared snippet.

### SK4 — `${CLAUDE_PLUGIN_ROOT}` binds skills to plugin context; manage can break it
- All three resolve `ENGINE="${CLAUDE_PLUGIN_ROOT}/scripts/config_sync.py"`. But manage's
  Share action copies a skill standalone into `~/.claude/skills/`, where the var is unset →
  `ENGINE=/scripts/config_sync.py` broken. Also: plugin skills are snapshot-excluded, so a
  fresh machine needs `claude plugin install mente-apex` before it can sync (bootstrapping).

### SK5 — share-plugin crashes on non-marketplace install path
- `config-sync-manage:308` `next(i for i, part in enumerate(parts) if part == "cache")`
  raises uncaught StopIteration if installPath has no `cache` segment (dev/linked plugin).

### SK6 — Dogfooding: single-letter comprehension/loop vars violate the user's own rule
- Global CLAUDE.md bans single-letter names in comprehensions/generators. `config_sync.py`
  and inline skill Python use `for k, v in ...`, `[_scrub(i, ...) for i in obj]`,
  `{l.strip() for l in lines_a}`, `for i, part in enumerate(parts)`, etc.

### SK7 (minor) — Dead `REMOTE` variable in config-sync Step 0 (`:42`), never used.

Not issues: setup/sync/manage split is sound SRP; manage's status/promote/share bundle is
acceptable for a management surface.

## Suggested order of attack

Fix **C1** first (silent, triggers on the most-run command, eats API keys). Then **C2**,
**M3**. The whole class of engine bug shrinks once **D7** (a real test suite) exists — a
failing round-trip test pinning the settings.json env-preservation contract is the natural
first red test via `/tdd`.
