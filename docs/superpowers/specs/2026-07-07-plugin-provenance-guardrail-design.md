# Plugin-provenance guardrail — closing #25 (PS4 residual)

**Date:** 2026-07-07
**Project:** mente-apex-plugin — config-sync engine
**Follows:** C1 (propagator seam) and C2 (MarketplacePropagator)
**Closes:** #25 (PS4 — root-cause umbrella), as a guardrail rather than a new channel.

---

## 1. Problem

C2's `MarketplacePropagator.export` **silently drops** any installed plugin whose `@marketplace` isn't a resolvable, shareable source (`scripts/config_sync_plugins.py:116` — `if marketplace_name not in known: continue`). A plugin whose marketplace is a local-path source, or absent from `known_marketplaces.json`, is quietly excluded from the manifest and never propagates — with no signal to the user. That silent exclusion is the last sharp edge of PS4.

## 2. Decision (guardrail, not a 4th channel)

The #25 umbrella imagined a `LocalPluginPropagator` (content-bundle propagation for locally-authored/offline plugins). We **deliberately do not build it.** Grounding confirmed the case doesn't exist and isn't wanted: all installed plugins are github/git-backed, there are no `@skills-dir` or local plugins, standalone skills already propagate via C1's `ContentBundlePropagator`, and the owner's rule is "everything worth building goes to GitHub." Building a machine-only content-bundle channel would work against that rule.

Instead, we turn the silent drop into an explicit **nudge**: when an installed plugin can't propagate (no shareable marketplace), warn the user and point them at GitHub. The propagator seam stays open/closed for a future 4th channel; we simply choose not to add one.

## 3. Classification rule

A marketplace is **shareable** iff another machine could `claude plugin marketplace add` it — i.e. its source is a real git remote. Concretely:

```python
SHAREABLE_SOURCE_KINDS = {"github", "git"}

def _is_shareable_marketplace(marketplace_meta) -> bool:
    """True iff the marketplace's source is a git/GitHub remote another machine
    can add. Local/path/directory sources, or missing/malformed metadata, are
    not shareable — a plugin behind one won't reach the owner's other machines."""
    if not isinstance(marketplace_meta, dict):
        return False
    source = marketplace_meta.get("source")
    if not isinstance(source, dict):
        return False
    return source.get("source") in SHAREABLE_SOURCE_KINDS
```

An installed plugin is **unshareable** when its `@marketplace` isn't in `known_marketplaces.json`, or its marketplace metadata fails `_is_shareable_marketplace`. Shareable plugins are recorded in the manifest exactly as today; unshareable ones produce a warning and are omitted from the manifest.

Reference source shapes (from `known_marketplaces.json`): shareable → `{"source": "github", "repo": …}` / `{"source": "git", "url": …}`; unshareable → e.g. `{"source": "directory", "path": …}` from `claude plugin marketplace add <local-path>`.

## 4. Data shape — `ExportResult.warnings`

Add a dedicated field to `ExportResult` (`scripts/config_sync_propagators.py:42`):

```python
@dataclass
class ExportResult:
    propagator: str
    written: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    warnings: list = field(default_factory=list)   # user-facing advisories
```

**Why a new field, not `skipped` (SRP):** `skipped` means "not written because unchanged/identical" — a bookkeeping fact. These are user-facing advisories with a call to action. Overloading `skipped` would force the skill to string-match to tell them apart. `warnings` is additive and optional; `SnapshotPropagator`/`ContentBundlePropagator` leave it empty (Liskov-safe — no existing caller breaks). This is the smallest honest extension.

## 5. `MarketplacePropagator.export` changes

Replace the silent `continue` with classification that accumulates warnings, and thread `warnings` through **both** return paths (so a persistently-unshareable plugin nags on every sync, including the unchanged change-gate path):

```python
def export(self, context):
    installed = _read_installed_plugins(context.claude_dir)
    known = _read_known_marketplaces(context.claude_dir)
    marketplaces: dict = {}
    plugins: dict = {}
    warnings: list = []
    for plugin_key, entries in installed.get("plugins", {}).items():
        marketplace_name = plugin_key.split("@", 1)[1] if "@" in plugin_key else ""
        marketplace_meta = known.get(marketplace_name)
        if marketplace_name not in known:
            warnings.append(
                f"{plugin_key}: no known marketplace — won't sync to your other "
                f"machines; publish it to a GitHub marketplace")
            continue
        if not _is_shareable_marketplace(marketplace_meta):
            source_value = marketplace_meta.get("source") if isinstance(marketplace_meta, dict) else None
            source_kind = source_value.get("source") if isinstance(source_value, dict) else None
            warnings.append(
                f"{plugin_key}: marketplace '{marketplace_name}' source is "
                f"'{source_kind}' (not a shareable git/GitHub remote) — won't sync "
                f"to your other machines; publish it to GitHub")
            continue
        entry = entries[0] if isinstance(entries, list) and entries else entries
        version = entry.get("version", "unknown") if isinstance(entry, dict) else "unknown"
        plugin_name = plugin_key.split("@", 1)[0]
        plugins[plugin_key] = {"marketplace": marketplace_name, "name": plugin_name, "version": version}
        marketplaces[marketplace_name] = {"source": known[marketplace_name].get("source")}

    machine_id = propagators._machine_id(context)
    manifest_path = context.repo_dir / "plugins" / f"{machine_id}.json"
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            if existing.get("marketplaces") == marketplaces and existing.get("plugins") == plugins:
                return propagators.ExportResult(
                    self.name, skipped=[f"plugins/{machine_id}.json (unchanged)"], warnings=warnings)
        except (json.JSONDecodeError, OSError):
            pass

    record = {"machine_id": machine_id,
              "exported_at": datetime.now(timezone.utc).isoformat(),
              "marketplaces": marketplaces, "plugins": plugins}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return propagators.ExportResult(
        self.name, written=[f"plugins/{machine_id}.json"], warnings=warnings)
```

## 6. CLI serialization

`cmd_propagate_export` (`scripts/config_sync.py`) serializes each `ExportResult`; add `warnings`:

```python
print(json.dumps({result.propagator: {"written": result.written,
                                       "skipped": result.skipped,
                                       "warnings": result.warnings}
                  for result in results}, indent=2))
```

## 7. Skill surfacing (soft, non-fatal)

`skills/config-sync/SKILL.md` Step 1: after `propagate-export`, parse the JSON and, if `marketplace.warnings` is non-empty, print an advisory to the user — the plugins listed won't reach their other machines, publish them to GitHub. This is informational only; it does **not** gate the sync (the owner asked to be warned, not blocked).

## 8. Scope note — plugins only, not skills

Standalone skills/agents already propagate via C1's `ContentBundlePropagator`; a per-skill "publish to GitHub" nag would fire on every standalone skill (~30 today) and be pure noise. The only genuinely *silent* propagation gap is plugins with an unshareable marketplace, so the guardrail is plugin-scoped by design.

## 9. DIP shape

No new abstraction or concretion. This extends the existing `MarketplacePropagator` (an `Exporter`) whose classification is a pure function over the two registry dicts it already reads via `context.claude_dir`. `_is_shareable_marketplace` is a pure, injected-nothing predicate, unit-testable in isolation. High-level policy (the skill) consumes `warnings` through the CLI JSON — depending on the `ExportResult` data shape, not internals. No module globals added.

## 10. Testing (TDD)

- `test_is_shareable_marketplace` — github→True, git→True, `directory`→False, missing `source`→False, non-dict meta→False.
- `MarketplacePropagator.export`:
  - local-`directory`-source plugin → appears in `warnings`, absent from manifest `plugins`.
  - plugin whose `@marketplace` isn't in `known_marketplaces.json` → warned, absent from manifest.
  - github/git plugin → in manifest `plugins`, no warning.
  - warnings are returned on the **unchanged** change-gate path too (export twice; second still warns).
- CLI: `cmd_propagate_export` JSON includes a `warnings` key under `marketplace`.

All tests run on pyenv 3.14.6 via `.venv/bin/python -m pytest`.

## 11. Global constraints (verbatim)

- **Python:** pyenv **3.14.6** (`.python-version`, `pyproject.toml` `requires-python >= 3.14`); venv built from `$(pyenv root)/versions/3.14.6/bin/python3`; tests via `.venv/bin/python -m pytest`.
- **SOLID/DIP** per §9: pure predicate, no new globals, `ExportResult.warnings` additive and Liskov-safe, seam left open/closed.
- **Descriptive names** — no single-letter/abbreviated variables, including in comprehensions/generators.
- **Commit trailer:** `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- **Version bump:** plugin version 0.8.0 → 0.9.0 (`.claude-plugin/marketplace.json`, `.claude-plugin/plugin.json`, `pyproject.toml`); `config-sync/SKILL.md` frontmatter one minor.

## 12. #25 closure record

The propagator architecture is complete — `SnapshotPropagator` (config) + `ContentBundlePropagator` (skills/agents) + `MarketplacePropagator` (marketplace plugins) — and remains open/closed for a future 4th channel. The local/private-plugin content-bundle channel is **deliberately not built**: no such plugin exists or is wanted, and the owner's rule is that anything worth keeping is published to GitHub. This guardrail enforces that rule by surfacing (rather than silently dropping) any plugin that can't propagate. #25 closes with this change.
