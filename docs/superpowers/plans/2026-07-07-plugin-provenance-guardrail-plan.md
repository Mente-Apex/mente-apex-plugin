# Plugin-Provenance Guardrail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `MarketplacePropagator.export`'s silent drop of unshareable plugins into an explicit, user-facing "publish to GitHub" warning, closing #25 as a guardrail rather than a new propagation channel.

**Architecture:** Add a pure `_is_shareable_marketplace` predicate and a `warnings` list to `ExportResult`; `MarketplacePropagator.export` accumulates a warning for each installed plugin whose marketplace isn't a shareable git/GitHub remote (instead of silently skipping it) and threads warnings through both return paths. The CLI serializes `warnings`; the `/config-sync` skill surfaces them as a soft, non-gating advisory.

**Tech Stack:** Python 3.14 stdlib only (`json`, `dataclasses`, `pathlib`); pytest.

## Global Constraints

- **Python:** pyenv **3.14.6**. **Run every test via `.venv/bin/python -m pytest`**, never bare `pytest`/`python3`.
- **SOLID/DIP:** `_is_shareable_marketplace` is a pure predicate (no injected collaborators, no globals). `ExportResult.warnings` is additive and Liskov-safe — `SnapshotPropagator`/`ContentBundlePropagator` leave it empty; no existing caller breaks. The seam stays open/closed (no 4th channel added).
- **Descriptive names** — no single-letter/abbreviated variables, including in comprehensions/generators (e.g. `for warning in warnings`).
- **Plugin-scoped:** warnings are for plugins only. Do NOT warn about skills/agents (they propagate via C1's `ContentBundlePropagator`).
- **Commit trailer (every commit):** `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- **Branch:** `audit/plugin-provenance-guardrail` (already created). Do not commit to `main`.
- **Reference files:** spec `docs/superpowers/specs/2026-07-07-plugin-provenance-guardrail-design.md`; `scripts/config_sync_plugins.py` (`MarketplacePropagator.export` at line 109); `scripts/config_sync_propagators.py` (`ExportResult` at line 42); `scripts/config_sync.py` (`cmd_propagate_export` at line 1024); tests `tests/test_marketplace_propagator.py`, `tests/test_propagate_cli.py`; fixture `claude_home` in `tests/conftest.py`.

**Marketplace source shapes** (`known_marketplaces.json`): shareable → `{"source": "github", "repo": …}` or `{"source": "git", "url": …}`; unshareable → e.g. `{"source": "directory", "path": …}`.

---

### Task 1: The warning mechanism (`warnings` field, predicate, export, CLI)

**Files:**
- Modify: `scripts/config_sync_propagators.py:42-45` (`ExportResult` — add `warnings`)
- Modify: `scripts/config_sync_plugins.py` (add `SHAREABLE_SOURCE_KINDS` + `_is_shareable_marketplace`; rewrite `MarketplacePropagator.export` at 109-142)
- Modify: `scripts/config_sync.py:1024-1029` (`cmd_propagate_export` — serialize `warnings`)
- Test: `tests/test_marketplace_propagator.py` (extend), `tests/test_propagate_cli.py` (extend)

**Interfaces:**
- Consumes: `_read_installed_plugins`, `_read_known_marketplaces`, `propagators._machine_id`, `propagators.ExportResult`, `propagators.SyncContext` (all existing).
- Produces:
  - `ExportResult.warnings: list` (new field, default empty).
  - `SHAREABLE_SOURCE_KINDS = {"github", "git"}` and `_is_shareable_marketplace(marketplace_meta) -> bool` in `config_sync_plugins.py`.
  - `MarketplacePropagator.export` now returns `ExportResult` with `warnings` populated for unshareable plugins, on both the written and unchanged paths.
  - `cmd_propagate_export` JSON now includes a `warnings` key per propagator.

- [ ] **Step 1: Write the failing predicate test**

Add to `tests/test_marketplace_propagator.py`:

```python
def test_is_shareable_marketplace_classifies_sources():
    assert plugins_module._is_shareable_marketplace({"source": {"source": "github", "repo": "a/b"}}) is True
    assert plugins_module._is_shareable_marketplace({"source": {"source": "git", "url": "https://h/r.git"}}) is True
    assert plugins_module._is_shareable_marketplace({"source": {"source": "directory", "path": "/x"}}) is False
    assert plugins_module._is_shareable_marketplace({"source": None}) is False
    assert plugins_module._is_shareable_marketplace({}) is False
    assert plugins_module._is_shareable_marketplace(None) is False
```

(The module is already imported as `plugins_module` at the top of this test file.)

- [ ] **Step 2: Run the predicate test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_marketplace_propagator.py::test_is_shareable_marketplace_classifies_sources -v`
Expected: FAIL — `AttributeError: module 'config_sync_plugins' has no attribute '_is_shareable_marketplace'`.

- [ ] **Step 3: Add the constant and predicate**

In `scripts/config_sync_plugins.py`, add near the top-level helpers (after the `_read_known_marketplaces` function, before `PluginRegistryReader`):

```python
SHAREABLE_SOURCE_KINDS = {"github", "git"}


def _is_shareable_marketplace(marketplace_meta) -> bool:
    """True iff the marketplace's source is a git/GitHub remote another machine
    can `claude plugin marketplace add`. Local/path/directory sources, or
    missing/malformed metadata, are not shareable — a plugin behind one won't
    reach the owner's other machines."""
    if not isinstance(marketplace_meta, dict):
        return False
    source = marketplace_meta.get("source")
    if not isinstance(source, dict):
        return False
    return source.get("source") in SHAREABLE_SOURCE_KINDS
```

- [ ] **Step 4: Run the predicate test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_marketplace_propagator.py::test_is_shareable_marketplace_classifies_sources -v`
Expected: PASS.

- [ ] **Step 5: Write the failing export-warning tests**

Add to `tests/test_marketplace_propagator.py` (the file already has `_setup(claude_dir, installed, marketplaces, machine_id="m1")` from earlier tasks — reuse it):

```python
def test_export_warns_on_local_source_plugin(tmp_path):
    claude_dir = tmp_path / ".claude"
    _setup(
        claude_dir,
        installed={"local-thing@mylocal": [{"version": "0.1"}]},
        marketplaces={"mylocal": {"source": {"source": "directory", "path": "/somewhere"}}},
    )
    context = propagators.SyncContext(claude_dir=claude_dir, repo_dir=tmp_path / "repo")

    result = plugins_module.MarketplacePropagator().export(context)

    manifest = json.loads((context.repo_dir / "plugins" / "m1.json").read_text())
    assert "local-thing@mylocal" not in manifest["plugins"]          # not propagated
    assert any("local-thing@mylocal" in warning for warning in result.warnings)   # warned instead
    assert any("publish it to GitHub" in warning for warning in result.warnings)


def test_export_warns_on_unknown_marketplace(tmp_path):
    claude_dir = tmp_path / ".claude"
    _setup(claude_dir, installed={"orphan@ghost": [{"version": "1"}]}, marketplaces={})
    context = propagators.SyncContext(claude_dir=claude_dir, repo_dir=tmp_path / "repo")

    result = plugins_module.MarketplacePropagator().export(context)

    assert any("orphan@ghost" in warning for warning in result.warnings)


def test_export_does_not_warn_on_shareable_plugin(tmp_path):
    claude_dir = tmp_path / ".claude"
    _setup(
        claude_dir,
        installed={"superpowers@official": [{"version": "6.1.1"}]},
        marketplaces={"official": {"source": {"source": "github", "repo": "a/b"}}},
    )
    context = propagators.SyncContext(claude_dir=claude_dir, repo_dir=tmp_path / "repo")

    result = plugins_module.MarketplacePropagator().export(context)

    manifest = json.loads((context.repo_dir / "plugins" / "m1.json").read_text())
    assert "superpowers@official" in manifest["plugins"]
    assert result.warnings == []


def test_export_warnings_persist_when_unchanged(tmp_path):
    claude_dir = tmp_path / ".claude"
    _setup(
        claude_dir,
        installed={"local-thing@mylocal": [{"version": "0.1"}]},
        marketplaces={"mylocal": {"source": {"source": "directory", "path": "/x"}}},
    )
    context = propagators.SyncContext(claude_dir=claude_dir, repo_dir=tmp_path / "repo")
    marketplace_propagator = plugins_module.MarketplacePropagator()

    marketplace_propagator.export(context)
    second = marketplace_propagator.export(context)
    assert any("unchanged" in entry for entry in second.skipped)                 # change-gate hit
    assert any("local-thing@mylocal" in warning for warning in second.warnings)  # still warned
```

- [ ] **Step 6: Run the export-warning tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_marketplace_propagator.py -k "warns or warnings" -v`
Expected: FAIL — `TypeError` (ExportResult has no `warnings`) or `AttributeError: 'ExportResult' object has no attribute 'warnings'`.

- [ ] **Step 7: Add the `warnings` field to `ExportResult`**

In `scripts/config_sync_propagators.py`, change the `ExportResult` dataclass (lines 42-45):

```python
@dataclass
class ExportResult:
    propagator: str
    written: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
```

- [ ] **Step 8: Rewrite `MarketplacePropagator.export` to warn instead of silently dropping**

In `scripts/config_sync_plugins.py`, replace the entire `export` method (lines 109-142) with:

```python
    def export(self, context: propagators.SyncContext) -> propagators.ExportResult:
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

        record = {
            "machine_id": machine_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "marketplaces": marketplaces,
            "plugins": plugins,
        }
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        return propagators.ExportResult(
            self.name, written=[f"plugins/{machine_id}.json"], warnings=warnings)
```

- [ ] **Step 9: Run the export-warning tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_marketplace_propagator.py -v`
Expected: PASS (existing tests + the 4 new warning tests).

- [ ] **Step 10: Write the failing CLI serialization test**

Add to `tests/test_propagate_cli.py` (the file uses the `claude_home` fixture and imports `config_sync`):

```python
def test_propagate_export_json_includes_warnings_key(claude_home, tmp_path, capsys):
    plugins_dir = claude_home / "plugins"
    plugins_dir.mkdir(parents=True)
    (plugins_dir / "installed_plugins.json").write_text(config_sync.json.dumps({
        "version": 2, "plugins": {"local-thing@mylocal": [{"version": "0.1"}]}}))
    (plugins_dir / "known_marketplaces.json").write_text(config_sync.json.dumps({
        "mylocal": {"source": {"source": "directory", "path": "/x"}}}))
    (claude_home / "config-sync-machine-id").write_text("cli-warn")
    repo = tmp_path / "repo"
    repo.mkdir()

    config_sync.cmd_propagate_export(str(repo))
    payload = config_sync.json.loads(capsys.readouterr().out)

    assert "warnings" in payload["marketplace"]
    assert any("local-thing@mylocal" in warning for warning in payload["marketplace"]["warnings"])
```

- [ ] **Step 11: Run the CLI test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_propagate_cli.py::test_propagate_export_json_includes_warnings_key -v`
Expected: FAIL — `KeyError: 'warnings'` (the serialized dict lacks the key).

- [ ] **Step 12: Add `warnings` to the CLI serialization**

In `scripts/config_sync.py`, change `cmd_propagate_export` (lines 1028-1029) to include `warnings`:

```python
    print(json.dumps({result.propagator: {"written": result.written,
                                           "skipped": result.skipped,
                                           "warnings": result.warnings}
                      for result in results}, indent=2))
```

- [ ] **Step 13: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — all existing tests plus the new predicate, export-warning, and CLI tests.

- [ ] **Step 14: Commit**

```bash
git add scripts/config_sync_propagators.py scripts/config_sync_plugins.py scripts/config_sync.py tests/test_marketplace_propagator.py tests/test_propagate_cli.py
git commit -m "feat(config-sync): warn on unshareable plugins instead of dropping them silently

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Surface the warnings in the sync skill + version bumps

**Files:**
- Modify: `skills/config-sync/SKILL.md` (Step 1 — surface `marketplace.warnings`; frontmatter version)
- Modify: `.claude-plugin/marketplace.json`, `.claude-plugin/plugin.json`, `pyproject.toml` (version bump)
- Test: none (skill prose + version metadata; not unit-tested)

**Interfaces:**
- Consumes: the `warnings` key emitted by `cmd_propagate_export` (Task 1).

- [ ] **Step 1: Surface warnings after `propagate-export` in Step 1**

In `skills/config-sync/SKILL.md`, find the Step 1 line that runs the export (it reads exactly):

```bash
python3 "$ENGINE" propagate-export "$REPO"
```

Replace that single line with a capture-and-surface block:

```bash
EXPORT_OUT=$(python3 "$ENGINE" propagate-export "$REPO")
echo "$EXPORT_OUT"

# Surface plugin-provenance warnings: plugins that can't reach your other machines
# because their marketplace isn't a shareable git/GitHub remote.
echo "$EXPORT_OUT" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for warning in data.get('marketplace', {}).get('warnings', []):
    print('⚠ ' + warning)
"
```

Then add this prose immediately after that code block:

> If any `⚠` lines appeared, tell the user those plugins won't sync to their other
> machines and suggest publishing each to a GitHub marketplace. This is advisory
> only — **do not** stop the sync; continue to the next step.

- [ ] **Step 2: Bump the skill frontmatter version**

In `skills/config-sync/SKILL.md` frontmatter, change `metadata.version` from `0.7.0` to `0.8.0`. (Read the current value first to confirm; if it differs, bump by one minor.)

- [ ] **Step 3: Bump the plugin version (three files, kept in sync)**

- `.claude-plugin/plugin.json`: `"version": "0.8.0"` → `"0.9.0"`.
- `.claude-plugin/marketplace.json`: `"version": "0.8.0"` → `"0.9.0"`.
- `pyproject.toml`: `version = "0.8.0"` → `version = "0.9.0"`.

(Read each current value first; if any differs, bump it by one minor to keep all three aligned.)

- [ ] **Step 4: Run the full suite (nothing should regress)**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (skill prose + version metadata don't touch Python behavior).

- [ ] **Step 5: Confirm no stray warning wiring was missed**

Run: `grep -n "warnings" scripts/config_sync.py scripts/config_sync_plugins.py skills/config-sync/SKILL.md`
Expected: `cmd_propagate_export` serializes `warnings`; `MarketplacePropagator.export` builds `warnings`; the SKILL Step 1 block reads `data.get('marketplace', {}).get('warnings', [])`.

- [ ] **Step 6: Commit**

```bash
git add skills/config-sync/SKILL.md .claude-plugin/plugin.json .claude-plugin/marketplace.json pyproject.toml
git commit -m "feat(config-sync): surface plugin-provenance warnings in /config-sync; v0.9.0 (closes #25)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Verification + finish the branch

**Files:** none (verification + handoff)

- [ ] **Step 1: Full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 2: Read-only CLI smoke (real registry; mutates nothing)**

```bash
rm -rf /tmp/guardrail-smoke && mkdir -p /tmp/guardrail-smoke
.venv/bin/python scripts/config_sync.py propagate-export /tmp/guardrail-smoke | python3 -c "import json,sys; d=json.load(sys.stdin); print('marketplace warnings:', d['marketplace']['warnings'])"
rm -rf /tmp/guardrail-smoke
```
Expected: prints `marketplace warnings: []` — the owner's six plugins are all github/git-backed, so there are legitimately no warnings. (A non-empty list would only appear if a local-source plugin were installed.)

- [ ] **Step 3: Finish the branch**

**REQUIRED SUB-SKILL:** Use superpowers:finishing-a-development-branch — verify tests, then present the 4 options and execute the choice. If a PR is created, note it closes #25 (guardrail, not a new channel) and reference the design/plan docs. After merge, the config-sync audit backlog (#9–#32) is fully closed.

---

## Self-Review

**1. Spec coverage:**
- §3 classification / `_is_shareable_marketplace` → Task 1 Steps 1-4. ✓
- §4 `ExportResult.warnings` field → Task 1 Step 7. ✓
- §5 export warns instead of dropping, both return paths → Task 1 Step 8 + `test_export_warnings_persist_when_unchanged`. ✓
- §6 CLI serialization → Task 1 Steps 10-12. ✓
- §7 skill surfacing (soft, non-gating) → Task 2 Step 1. ✓
- §8 plugin-scoped (no skill warnings) → enforced by construction (only `MarketplacePropagator` warns); Global Constraints restate it. ✓
- §10 testing (predicate, three export cases, unchanged-path, CLI) → Task 1 tests. ✓
- §11 version bump → Task 2 Steps 2-3. ✓
- §12 #25 closure → Task 3 Step 3 (PR note); the closure record lives in the committed spec. ✓

**2. Placeholder scan:** No TBD/TODO; every code step shows complete code; the two grep/smoke steps are concrete commands with expected output. ✓

**3. Type consistency:** `ExportResult(propagator, written, skipped, warnings)`, `_is_shareable_marketplace(marketplace_meta) -> bool`, `SHAREABLE_SOURCE_KINDS`, `MarketplacePropagator.export(context) -> ExportResult` — names/signatures identical across every task and matched to the current source (`export` at line 109, `ExportResult` at line 42, `cmd_propagate_export` at line 1024). The SKILL parses `data['marketplace']['warnings']`, matching the CLI key added in Task 1 Step 12. ✓
