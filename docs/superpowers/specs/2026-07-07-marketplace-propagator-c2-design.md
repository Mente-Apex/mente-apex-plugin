# Phase C2 — MarketplacePropagator (desired-state plugin convergence)

**Date:** 2026-07-07
**Project:** mente-apex-plugin — config-sync engine
**Phase:** C2 (follows C1, the Propagator seam)
**Closes:** #22 (PS1), #16 (D8), #26 (SK1); closes #24 (PS3) & #25 (PS4) *for marketplace plugins*, leaving a scoped private-plugin follow-up behind the open seam.

---

## 1. Problem

Plugins still ride the pre-C1 legacy channel:

- **Export** is a 55-line Python heredoc in `skills/config-sync/SKILL.md` that copies each installed plugin's *entire cache* into `shared/plugins/<key>/` and **skips if the directory already exists** → a newer local build never re-exports (freeze, #24). It lives in a skill, is re-parsed as shell every run, and is untestable (#26).
- **Import** is `cmd_apply_shared` in `config_sync.py`: it copies cache files back into `~/.claude/plugins/cache/…`, hand-writes `installed_plugins.json` with `indent=4` (export path uses `indent=2` → machines fight over formatting, #16), and **skips if the plugin key is already installed** → other machines never receive a new version (freeze, #24).
- Nothing ever runs `claude plugin marketplace update` / `install` / `update` → marketplace updates are never pulled (#22).

Root cause (#25): two propagation responsibilities are conflated behind one "copy the live cache" strategy. Marketplace-sourced plugins want **desired-state** propagation (record `{key, marketplace, version}`; converge via marketplace update + install/update). Locally-authored/offline plugins want **content-bundle** propagation.

C1 opened the seam (`config_sync_propagators.py`) and left `default_propagators()` commented *"C2 appends MarketplacePropagator() here."* C2 delivers the marketplace strategy.

## 2. Locked decisions

1. **Single source of truth = `~/.claude/plugins/installed_plugins.json`.** config-sync makes another machine's *installed set* match this one's. The registry is that authoritative desired-installed-state and the file Claude itself reads. Not the filesystem cache, not a hand-maintained list, not the plugin's git repo. A plugin developed but never `claude plugin install`ed is out of scope by design — it syncs via its own remote and becomes visible to config-sync only once installed (which registers it).

2. **Scope = marketplace-only.** The marketplace is resolvable from the plugin **key** (`name@marketplace`), so the marketplace strategy covers every plugin whose `@marketplace` is registered in `known_marketplaces.json` — which is every plugin currently installed. A `LocalPluginPropagator` for genuinely private/offline plugins is **deferred** behind the open seam (YAGNI); no such plugin exists in the current environment.

3. **Apply = plan-then-consent.** The apply half is a pure planner that returns proposed actions as data; the skill shows them and asks via **AskUserQuestion**; only on consent are `claude plugin` mutations executed. Mirrors C1's "bundle conflicts are data, the skill prompts."

4. **Version = converge-to-latest, no pinning.** The recorded version is informational (drives display only). Convergence refreshes marketplaces and installs missing / updates existing to whatever the marketplace currently offers. This matches the `claude plugin` CLI, directly fixes #22, and dissolves multi-machine version conflicts (nothing to reconcile). **Never uninstall** — union-only, no tombstones, consistent with C1.

## 3. Architecture & DIP

Two new abstractions; no high-level code touches a subprocess or a global.

### 3.1 Split C1's `Propagator` into `Exporter` + `Applier` (ISP/LSP)

C1 defined one `Propagator` protocol with both `export` and `apply`. C2 segregates it:

```python
@runtime_checkable
class Exporter(Protocol):
    name: str
    def export(self, context: SyncContext) -> ExportResult: ...

@runtime_checkable
class Applier(Protocol):
    name: str
    def apply(self, context: SyncContext) -> ApplyResult: ...
```

- `SnapshotPropagator` and `ContentBundlePropagator` implement **both**.
- `MarketplacePropagator` implements **`Exporter` only**. Its apply is a separate consent-gated `plan()`/`execute()` pair — *not* a generic `apply()`.

**Why (LSP):** `Applier.apply()`'s postcondition is "idempotently converge **local files** and report what changed." Plugin apply mutates **external install state** (runs `claude plugin install`) and requires user consent — it cannot honor that postcondition, so it must not masquerade as an `Applier`. Segregating the protocols lets the type system express "MarketplacePropagator exports but does not locally-apply" without a weakened-postcondition lie.

### 3.2 `PluginRegistryReader` + `PluginInstaller` ports (ISP-segregated subprocess seam)

```python
@runtime_checkable
class PluginRegistryReader(Protocol):
    def installed_plugins(self) -> dict: ...      # {key: entry} from installed_plugins.json
    def known_marketplaces(self) -> dict: ...     # {name: {"source": {...}}} from known_marketplaces.json

@runtime_checkable
class PluginInstaller(Protocol):
    def add_marketplace(self, name: str, source: dict) -> "ActionOutcome": ...
    def update_marketplace(self, name: str) -> "ActionOutcome": ...
    def install_plugin(self, key: str) -> "ActionOutcome": ...
    def update_plugin(self, key: str) -> "ActionOutcome": ...
```

- The **planner consumes only `PluginRegistryReader`** — pure JSON file reads, **zero subprocess**. The whole plan is computed and tested without mocking a subprocess.
- The **executor consumes only `PluginInstaller`** — the sole component that shells out.
- Real `ClaudePluginHost` implements both (reads the two registry JSON files; shells out to `claude plugin …` for mutations). Tests inject `FakePluginReader` / `FakePluginInstaller`.

`SyncContext(claude_dir, repo_dir)` is injected exactly as in C1; the reader derives the two registry paths from `context.claude_dir`.

## 4. Components & files

| File | Responsibility |
|---|---|
| `scripts/config_sync_propagators.py` (modify) | Replace `Propagator` with `Exporter` + `Applier`; `apply_propagators()` → `[SnapshotPropagator(), ContentBundlePropagator()]` (unchanged mutation sweep). Both concrete classes now nominally satisfy both protocols. |
| `scripts/config_sync_plugins.py` (**new**) | `PluginRegistryReader` / `PluginInstaller` protocols; `ClaudePluginHost`; `MarketplacePropagator(Exporter)`; dataclasses `PlannedAction`, `MarketplacePlan`, `ActionOutcome`, `MarketplaceResult`; `plan_convergence(context, reader) -> MarketplacePlan`; `execute_plan(context, plan, installer) -> MarketplaceResult`; `export_propagators() -> [Snapshot, ContentBundle, Marketplace]`. |
| `scripts/config_sync.py` (modify) | `cmd_propagate_export` uses `export_propagators()`; `cmd_propagate_apply` uses `apply_propagators()`; new `cmd_plugins_plan(repo, host=None)` and `cmd_plugins_apply(repo, host=None)` (default `ClaudePluginHost(context)`, injectable for tests); **delete the plugin half of `cmd_apply_shared`**; register `plugins-plan`, `plugins-apply` in `COMMANDS`. |
| `skills/config-sync/SKILL.md` (modify) | **Delete the 55-line plugin-export heredoc** in Step 1 (now covered by `propagate-export`). Replace the plugin portion of Step 4b with: `plugins-plan` → if non-empty, `AskUserQuestion` consent → `plugins-apply`. `apply-shared` keeps only legacy `shared/skills\|rules\|agents`. |
| `pyproject.toml`, `.claude-plugin/marketplace.json`, `skills/config-sync/SKILL.md` frontmatter (modify) | Version bump 0.7.0 → 0.8.0. |

Dependency direction is one-way: `config_sync_plugins` → `config_sync_propagators` (imports `Exporter`, `SnapshotPropagator`, `ContentBundlePropagator`). No cycle. Plugin/subprocess concerns live in their own module (SRP); `propagators.py` stays about the generic seam.

## 5. Data model — per-machine manifest

Mirrors the `machines/*.json` pattern: **per-machine files unioned at read time** — no shared-file git contention, no consolidate step. Written to `plugins/<machine_id>.json` in the config-sync data repo.

```json
{
  "machine_id": "laptop-ab12cd34",
  "exported_at": "2026-07-07T12:00:00+00:00",
  "marketplaces": {
    "claude-plugins-official": {"source": {"source": "github", "repo": "anthropics/claude-plugins-official"}},
    "mente-apex": {"source": {"source": "github", "repo": "menteapex/mente-apex-plugin"}}
  },
  "plugins": {
    "superpowers@claude-plugins-official": {"marketplace": "claude-plugins-official", "name": "superpowers", "version": "6.1.1"},
    "playwright@claude-plugins-official": {"marketplace": "claude-plugins-official", "name": "playwright", "version": "unknown"}
  }
}
```

**Classification rule:** a plugin is marketplace-sourced iff the `@marketplace` segment of its key is a key in `known_marketplaces.json`. Only those are written; unresolvable ones are silently deferred to the (unbuilt) local channel. `marketplaces` records only the sources actually referenced by included plugins, copied verbatim from `known_marketplaces.json[name]["source"]` (this is what a second machine needs to `claude plugin marketplace add`).

**Change-gate:** the propagator rewrites `plugins/<machine_id>.json` only when the freshly-derived `{marketplaces, plugins}` differs from the existing file's (ignoring `exported_at`). No diff → no write → no churn (#16).

## 6. Data flow

### 6.1 Export (`propagate-export`, now includes MarketplacePropagator)

`cmd_propagate_export` iterates `export_propagators()`. `MarketplacePropagator.export`:
1. Read `installed_plugins.json` + `known_marketplaces.json` **directly** from `context.claude_dir / "plugins"` via shared module-level read helpers (`_read_installed_plugins(claude_dir)`, `_read_known_marketplaces(claude_dir)`) — parity with how `SnapshotPropagator.export` reads config files straight from `context.claude_dir`. These are plain JSON file reads (same tier as the rest of the export sweep), fully testable against a temp `claude_dir`; no concretion is instantiated inside the propagator. `ClaudePluginHost.installed_plugins()` / `known_marketplaces()` wrap the *same* helpers so the reader port and the export path never diverge.
2. For each installed key whose `@marketplace` ∈ known marketplaces: add to `plugins`, and add that marketplace's `source` to `marketplaces`.
3. Change-gated write to `plugins/<machine_id>.json`.
4. Return `ExportResult("marketplace", written=[...] | skipped=[...])`.

The SKILL's plugin heredoc is deleted; `installed_plugins.json` is never copied or hand-written → #16 bloat + indent churn eliminated by construction, #26 export moved into the engine.

### 6.2 Apply (skill-driven consent loop; replaces the plugin part of Step 4b)

1. **`plugins-plan <repo>`** → `plan_convergence(context, reader)` reads *all* `plugins/*.json`, unions `marketplaces` (name→source) and `plugins` (key→meta) across machines, diffs against the live `PluginRegistryReader`, and emits a `MarketplacePlan` of `PlannedAction`s:
   - marketplace desired but not in local `known_marketplaces()` → `add_marketplace(name, source)` (skipped-with-reason if `source` unknown)
   - each desired marketplace → `update_marketplace(name)` (index refresh — core #22 fix)
   - desired plugin key not in local `installed_plugins()` → `install_plugin(key)`
   - desired plugin key present locally → `update_plugin(key)` (converge-to-latest; no-ops if current)
   - installed-but-not-desired → **no action** (union-only; never uninstall)
   Prints the plan as JSON.
2. If the plan is non-empty, the skill renders it and asks **AskUserQuestion** ("Refresh N marketplace(s), install M, update K plugin(s) — proceed?"). Decline → stop, nothing mutated.
3. On consent: **`plugins-apply <repo>`** → re-derives the plan, runs each `PlannedAction` via `PluginInstaller`, collects a `MarketplaceResult` (per-action `ActionOutcome`), re-reads the registry to report resulting versions, prints the result.

### 6.3 `PlannedAction` / result shapes

```python
@dataclass
class PlannedAction:
    verb: str          # "add_marketplace" | "update_marketplace" | "install_plugin" | "update_plugin"
    target: str        # marketplace name or plugin key
    detail: dict = field(default_factory=dict)   # e.g. {"source": {...}} or {"current_version": "6.1.0"}

@dataclass
class MarketplacePlan:
    actions: list = field(default_factory=list)      # list[PlannedAction]
    skipped: list = field(default_factory=list)      # list[str] human reasons (e.g. "marketplace X: source unknown")

@dataclass
class ActionOutcome:
    verb: str
    target: str
    ok: bool
    message: str = ""

@dataclass
class MarketplaceResult:
    outcomes: list = field(default_factory=list)     # list[ActionOutcome]
    skipped: list = field(default_factory=list)
```

## 7. Real `ClaudePluginHost` (the injected concretion)

- `installed_plugins()` / `known_marketplaces()`: read the two JSON files under `context.claude_dir / "plugins"`; return `{}` on missing/corrupt.
- `add_marketplace(name, source)`: `claude plugin marketplace add <spec>` where `<spec>` is `owner/repo` for `source == "github"`, else the `url`.
- `update_marketplace(name)`: `claude plugin marketplace update <name>`.
- `install_plugin(key)`: `claude plugin install <key>`.
- `update_plugin(key)`: `claude plugin update <key>`.
- Each mutation returns an `ActionOutcome(ok=returncode==0, message=stderr-tail)`.

**Verification step (plan Task 0):** confirm the exact `claude plugin` subcommand spellings against `claude plugin --help` before hard-coding them, so a wrong flag isn't baked in. Only mutations shell out; reads are file reads.

## 8. Error handling

- `claude` CLI absent: reads still work; `execute_plan` returns `ActionOutcome(ok=False, message="claude CLI not found")` per action and converges nothing rather than crashing.
- A single action failure is captured per-action and does not abort the rest.
- Marketplace desired, `source` unknown *and* not registered locally → the dependent plugin's install is recorded in `plan.skipped` ("register marketplace X manually"), not silently dropped.
- Corrupt `plugins/*.json` in the repo → skipped with a warning; other machines' files still union.

## 9. Backward compatibility / migration

No repo rewrite. Old machines may still write `shared/plugins/`; the new apply ignores it (inert, exactly like legacy skill keys go inert in C1's `SnapshotPropagator`). New machines stop writing it. `cmd_apply_shared` retains only `shared/skills|rules|agents` handling for older peers.

## 10. Testing (TDD; injected fakes — no real `claude`, no real installs)

- `tests/test_marketplace_propagator.py` — export writes `plugins/<machine_id>.json`; includes only resolvable-marketplace plugins; excludes unresolvable ones; records only referenced marketplace sources; change-gated (no rewrite when unchanged).
- `tests/test_plugin_convergence.py` — `plan_convergence` against `FakePluginReader`: add-marketplace when unregistered, install when absent, update when present, no-op-free union, **never emits an uninstall**, source-unknown → `skipped`. `execute_plan` against `FakePluginInstaller`: records the right calls in order and captures per-action failures.
- `tests/test_plugins_cli.py` — `cmd_plugins_plan` / `cmd_plugins_apply` with an injected fake host print the expected JSON.
- Update C1 tests referencing `default_propagators()` for the `export_propagators()` / `apply_propagators()` split.

All tests run on pyenv **3.14.6** via `.venv/bin/python` (see Global Constraints).

## 11. Global constraints (verbatim)

- **Python:** pyenv **3.14.6**, pinned by `.python-version` and `pyproject.toml` `requires-python = ">=3.14"`. venv built from `$(pyenv root)/versions/3.14.6/bin/python3` (pyenv shims are absent on the non-interactive shell PATH). Run tests via `.venv/bin/python -m pytest`.
- **SOLID/DIP** as stated in §3: depend on `Exporter`, `PluginRegistryReader`, `PluginInstaller` abstractions; inject the concrete `ClaudePluginHost` via CLI wrappers; no module globals in new code; open/closed — `MarketplacePropagator` is *added*, C1 propagators are not edited except for the protocol split.
- **Descriptive names** — no single-letter/abbreviated variables, including in comprehensions/generators.
- **Commit trailer:** `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- **Conflicts/mutations prompt** via AskUserQuestion (never silent).

## 12. Issue closure

| Issue | Status after C2 |
|---|---|
| **#22** PS1 marketplace refresh | Closed — `update_marketplace` in every plan |
| **#16** D8 bloat / indent churn | Closed — manifest not cache; registry never hand-written |
| **#26** SK1 heredoc / asymmetry | Closed — export in engine via propagator; heredoc deleted |
| **#24** PS3 freeze | Closed for marketplace plugins (converge-to-latest, change-gated export); private-plugin residual noted as follow-up |
| **#25** PS4 root cause | Closed for marketplace plugins; scoped private-plugin channel remains behind the open `Applier`/local seam |
