# MarketplacePropagator (Phase C2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the legacy cache-copying plugin sync with a desired-state `MarketplacePropagator` that records a per-machine plugin manifest on export and converges other machines via `claude plugin` (plan-then-consent) on apply.

**Architecture:** Split C1's `Propagator` protocol into `Exporter` + `Applier` (ISP/LSP) so the marketplace channel is an `Exporter` with a separate consent-gated `plan()`/`execute()` pair. A new `scripts/config_sync_plugins.py` holds the plugin concerns: two ISP-segregated ports (`PluginRegistryReader` read-only file reads; `PluginInstaller` the only subprocess boundary), the real `ClaudePluginHost` implementing both, `MarketplacePropagator.export`, the pure `plan_convergence`, and `execute_plan`. The `claude`-shelling concretion is injected via the CLI wrappers and faked in every test.

**Tech Stack:** Python 3.14 stdlib only (`json`, `subprocess`, `dataclasses`, `pathlib`, `typing.Protocol`); pytest.

## Global Constraints

- **Python:** pyenv **3.14.6**, pinned by `.python-version` + `pyproject.toml` `requires-python = ">=3.14"`. The venv is built from `$(pyenv root)/versions/3.14.6/bin/python3` (pyenv shims are absent on the non-interactive shell PATH). **Run every test via `.venv/bin/python -m pytest`**, never bare `pytest`/`python3`.
- **SOLID/DIP:** depend on the `Exporter`, `PluginRegistryReader`, `PluginInstaller` abstractions; inject the concrete `ClaudePluginHost` through the CLI wrappers (default arg `host=None` → construct it; tests pass a fake). No module globals in new code. Open/closed — `MarketplacePropagator` is *added*; C1 propagators are untouched except the one protocol split.
- **Descriptive names** — no single-letter/abbreviated variables, including in comprehensions and generator expressions (e.g. `for plugin_key in …`, never `for k in …`).
- **Never uninstall / union-only** — a plugin installed locally but absent from every manifest is left alone.
- **Commit trailer (every commit):** `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- **Branch:** work happens on `audit/marketplace-propagator-c2` (already created). Do not commit to `main`.
- **Reference files:** spec `docs/superpowers/specs/2026-07-07-marketplace-propagator-c2-design.md`; C1 seam `scripts/config_sync_propagators.py`; engine `scripts/config_sync.py`; fixtures `tests/conftest.py` (the `claude_home` fixture monkeypatches `CLAUDE_DIR`/`PLUGINS_DIR`/… onto a temp dir).

**Registry file shapes (real, verified 2026-07-07):**
- `~/.claude/plugins/installed_plugins.json` → `{"version": 2, "plugins": {"<name>@<marketplace>": [{"scope","installPath","version","installedAt","lastUpdated"}]}}` (value is a **list**; `version` may be `"unknown"`).
- `~/.claude/plugins/known_marketplaces.json` → `{"<marketplace>": {"source": {"source": "github", "repo": "owner/name"} | {"source": "git", "url": "https://…"}, "installLocation", "lastUpdated"}}`.

---

### Task 1: Split `Propagator` → `Exporter` + `Applier`; add `apply_propagators()`

**Files:**
- Modify: `scripts/config_sync_propagators.py` (protocol block ~lines 56-70; `default_propagators` ~lines 317-320)
- Modify: `scripts/config_sync.py:1095-1097` (`cmd_propagate_apply`)
- Test: `tests/test_protocol_split.py` (new)

**Interfaces:**
- Consumes: `SyncContext`, `SnapshotPropagator`, `ContentBundlePropagator` (C1, unchanged).
- Produces: `Exporter` (Protocol, `name`, `export(context)->ExportResult`), `Applier` (Protocol, `name`, `apply(context)->ApplyResult`), `apply_propagators() -> list` = `[SnapshotPropagator(), ContentBundlePropagator()]`. `default_propagators()` stays for now (removed in Task 6).

- [ ] **Step 1: Write the failing test**

Create `tests/test_protocol_split.py`:

```python
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import config_sync_propagators as propagators  # noqa: E402


def test_snapshot_and_bundle_satisfy_both_protocols():
    snapshot = propagators.SnapshotPropagator()
    bundle = propagators.ContentBundlePropagator()
    assert isinstance(snapshot, propagators.Exporter)
    assert isinstance(snapshot, propagators.Applier)
    assert isinstance(bundle, propagators.Exporter)
    assert isinstance(bundle, propagators.Applier)


def test_apply_propagators_returns_snapshot_and_bundle():
    names = {propagator.name for propagator in propagators.apply_propagators()}
    assert names == {"snapshot", "content-bundle"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_protocol_split.py -v`
Expected: FAIL — `AttributeError: module 'config_sync_propagators' has no attribute 'Exporter'`.

- [ ] **Step 3: Implement the protocol split**

In `scripts/config_sync_propagators.py`, replace the `Propagator` protocol block:

```python
@runtime_checkable
class Propagator(Protocol):
    name: str

    def export(self, context: SyncContext) -> ExportResult: ...

    def apply(self, context: SyncContext) -> ApplyResult: ...
```

with two segregated protocols:

```python
@runtime_checkable
class Exporter(Protocol):
    """Writes this machine's state into the repo. One reason to change: export format."""
    name: str

    def export(self, context: SyncContext) -> ExportResult: ...


@runtime_checkable
class Applier(Protocol):
    """Idempotently converges LOCAL files from the repo and reports what changed.
    Plugins deliberately do NOT implement this — their apply mutates external
    install state and needs consent, so it lives in a separate plan/execute pair."""
    name: str

    def apply(self, context: SyncContext) -> ApplyResult: ...
```

Then add `apply_propagators()` next to the existing `default_propagators()` (leave `default_propagators()` in place — Task 6 removes it):

```python
def apply_propagators() -> list:
    """Composition root for the local-file apply sweep (Snapshot + ContentBundle)."""
    return [SnapshotPropagator(), ContentBundlePropagator()]
```

- [ ] **Step 4: Point `cmd_propagate_apply` at `apply_propagators()`**

In `scripts/config_sync.py`, in `cmd_propagate_apply`, change the one line:

```python
    results = propagators.run_apply(context, propagators.default_propagators())
```
to:
```python
    results = propagators.run_apply(context, propagators.apply_propagators())
```

- [ ] **Step 5: Confirm nothing else references the removed `Propagator` name**

Run: `grep -rn "propagators.Propagator\|\bPropagator\b" scripts/ tests/`
Expected: only the two new protocol definitions match — no other reference. (If any surfaces, it is dead and should be updated to `Exporter`/`Applier`.)

- [ ] **Step 6: Run the full suite to verify green**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — new protocol tests pass; all C1 tests (including `test_default_propagators_runs_both_channels`, which still uses the retained `default_propagators()`) stay green.

- [ ] **Step 7: Commit**

```bash
git add scripts/config_sync_propagators.py scripts/config_sync.py tests/test_protocol_split.py
git commit -m "refactor(config-sync): split Propagator into Exporter + Applier (ISP/LSP)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Registry read helpers + `PluginRegistryReader` port + `ClaudePluginHost` (read side)

**Files:**
- Create: `scripts/config_sync_plugins.py`
- Test: `tests/test_plugin_registry.py` (new)

**Interfaces:**
- Consumes: `SyncContext` (from `config_sync_propagators`).
- Produces:
  - `_read_installed_plugins(claude_dir: Path) -> dict` (whole file, `{}` on missing/corrupt)
  - `_read_known_marketplaces(claude_dir: Path) -> dict` (whole file, `{}` on missing/corrupt)
  - `PluginRegistryReader` Protocol: `installed_plugins() -> dict` (**flattened** `{key: entry_dict}`), `known_marketplaces() -> dict` (`{name: {"source": …}}`)
  - `ClaudePluginHost(context: SyncContext)` implementing the read side.

- [ ] **Step 1: Write the failing test**

Create `tests/test_plugin_registry.py`:

```python
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import config_sync_plugins as plugins_module  # noqa: E402
import config_sync_propagators as propagators  # noqa: E402


def _write_registry(claude_dir):
    plugins_dir = claude_dir / "plugins"
    plugins_dir.mkdir(parents=True)
    (plugins_dir / "installed_plugins.json").write_text(json.dumps({
        "version": 2,
        "plugins": {"superpowers@claude-plugins-official": [
            {"scope": "user", "installPath": "/x", "version": "6.1.1"}]},
    }))
    (plugins_dir / "known_marketplaces.json").write_text(json.dumps({
        "claude-plugins-official": {"source": {"source": "github", "repo": "anthropics/claude-plugins-official"}}}))


def test_read_helpers_return_empty_on_missing(tmp_path):
    assert plugins_module._read_installed_plugins(tmp_path) == {}
    assert plugins_module._read_known_marketplaces(tmp_path) == {}


def test_reader_flattens_installed_entries(tmp_path):
    claude_dir = tmp_path / ".claude"
    _write_registry(claude_dir)
    context = propagators.SyncContext(claude_dir=claude_dir, repo_dir=tmp_path / "repo")
    reader = plugins_module.ClaudePluginHost(context)

    installed = reader.installed_plugins()
    assert installed["superpowers@claude-plugins-official"]["version"] == "6.1.1"   # list flattened to entry
    assert "claude-plugins-official" in reader.known_marketplaces()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_plugin_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'config_sync_plugins'`.

- [ ] **Step 3: Create the module with read helpers + reader port + ClaudePluginHost**

Create `scripts/config_sync_plugins.py`:

```python
"""Plugin propagation for config-sync — the marketplace desired-state channel.

DIP: the planner depends only on PluginRegistryReader (pure file reads);
the executor depends only on PluginInstaller (the sole subprocess boundary).
ClaudePluginHost is the injected concretion implementing both; tests fake them.
Dependency direction is one-way: this module imports config_sync_propagators,
never the reverse.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, runtime_checkable

import config_sync_propagators as propagators


def _read_installed_plugins(claude_dir: Path) -> dict:
    path = claude_dir / "plugins" / "installed_plugins.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _read_known_marketplaces(claude_dir: Path) -> dict:
    path = claude_dir / "plugins" / "known_marketplaces.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


@runtime_checkable
class PluginRegistryReader(Protocol):
    def installed_plugins(self) -> dict: ...      # {key: entry_dict}

    def known_marketplaces(self) -> dict: ...     # {name: {"source": {...}}}


class ClaudePluginHost:
    """Real host: reads the two registry JSON files; shells out to `claude plugin`
    for mutations (added in Task 5). Injected via the CLI wrappers; faked in tests."""

    def __init__(self, context: propagators.SyncContext):
        self._context = context

    def installed_plugins(self) -> dict:
        raw = _read_installed_plugins(self._context.claude_dir)
        flattened = {}
        for plugin_key, entries in raw.get("plugins", {}).items():
            entry = entries[0] if isinstance(entries, list) and entries else entries
            if isinstance(entry, dict):
                flattened[plugin_key] = entry
        return flattened

    def known_marketplaces(self) -> dict:
        return _read_known_marketplaces(self._context.claude_dir)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_plugin_registry.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/config_sync_plugins.py tests/test_plugin_registry.py
git commit -m "feat(config-sync): plugin registry read helpers + PluginRegistryReader port

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `MarketplacePropagator.export` (classification + manifest + change-gate)

**Files:**
- Modify: `scripts/config_sync_plugins.py`
- Test: `tests/test_marketplace_propagator.py` (new)

**Interfaces:**
- Consumes: `_read_installed_plugins`, `_read_known_marketplaces`, `propagators._machine_id(context)`, `propagators.ExportResult`, `propagators.SyncContext`.
- Produces: `MarketplacePropagator` with `name = "marketplace"` and `export(context) -> ExportResult`. Writes `repo_dir/plugins/<machine_id>.json` = `{"machine_id","exported_at","marketplaces":{name:{"source":…}},"plugins":{key:{"marketplace","name","version"}}}`. Change-gated on `(marketplaces, plugins)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_marketplace_propagator.py`:

```python
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import config_sync_plugins as plugins_module  # noqa: E402
import config_sync_propagators as propagators  # noqa: E402


def _setup(claude_dir, installed, marketplaces, machine_id="m1"):
    plugins_dir = claude_dir / "plugins"
    plugins_dir.mkdir(parents=True)
    (plugins_dir / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": installed}))
    (plugins_dir / "known_marketplaces.json").write_text(json.dumps(marketplaces))
    (claude_dir / "config-sync-machine-id").write_text(machine_id)


def test_export_records_only_resolvable_marketplace_plugins(tmp_path):
    claude_dir = tmp_path / ".claude"
    _setup(
        claude_dir,
        installed={
            "superpowers@claude-plugins-official": [{"version": "6.1.1"}],
            "private-thing@nowhere": [{"version": "0.1"}],       # marketplace not registered → excluded
        },
        marketplaces={"claude-plugins-official": {
            "source": {"source": "github", "repo": "anthropics/claude-plugins-official"}}},
    )
    context = propagators.SyncContext(claude_dir=claude_dir, repo_dir=tmp_path / "repo")

    result = plugins_module.MarketplacePropagator().export(context)

    manifest = json.loads((context.repo_dir / "plugins" / "m1.json").read_text())
    assert list(manifest["plugins"]) == ["superpowers@claude-plugins-official"]   # unresolvable excluded
    assert manifest["plugins"]["superpowers@claude-plugins-official"]["version"] == "6.1.1"
    assert manifest["marketplaces"]["claude-plugins-official"]["source"]["repo"] == \
        "anthropics/claude-plugins-official"
    assert "plugins/m1.json" in result.written


def test_export_is_change_gated(tmp_path):
    claude_dir = tmp_path / ".claude"
    _setup(claude_dir, installed={"superpowers@claude-plugins-official": [{"version": "6.1.1"}]},
           marketplaces={"claude-plugins-official": {"source": {"source": "github", "repo": "a/b"}}})
    context = propagators.SyncContext(claude_dir=claude_dir, repo_dir=tmp_path / "repo")
    marketplace_propagator = plugins_module.MarketplacePropagator()

    marketplace_propagator.export(context)
    second = marketplace_propagator.export(context)
    assert second.written == [] and any("unchanged" in entry for entry in second.skipped)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_marketplace_propagator.py -v`
Expected: FAIL — `AttributeError: module 'config_sync_plugins' has no attribute 'MarketplacePropagator'`.

- [ ] **Step 3: Implement `MarketplacePropagator`**

Append to `scripts/config_sync_plugins.py`:

```python
class MarketplacePropagator:
    """Exporter for marketplace-sourced plugins (desired-state manifest).

    Classification: a plugin is marketplace-sourced iff the `@marketplace`
    segment of its key is registered in known_marketplaces.json. Only those are
    recorded; the rest are silently deferred to the (unbuilt) local channel.
    Not an Applier — plugin apply is the consent-gated plan/execute pair below.
    """

    name = "marketplace"

    def export(self, context: propagators.SyncContext) -> propagators.ExportResult:
        installed = _read_installed_plugins(context.claude_dir)
        known = _read_known_marketplaces(context.claude_dir)
        marketplaces: dict = {}
        plugins: dict = {}
        for plugin_key, entries in installed.get("plugins", {}).items():
            marketplace_name = plugin_key.split("@", 1)[1] if "@" in plugin_key else ""
            if marketplace_name not in known:
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
                    return propagators.ExportResult(self.name, skipped=[f"plugins/{machine_id}.json (unchanged)"])
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
        return propagators.ExportResult(self.name, written=[f"plugins/{machine_id}.json"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_marketplace_propagator.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/config_sync_plugins.py tests/test_marketplace_propagator.py
git commit -m "feat(config-sync): MarketplacePropagator.export — desired-state manifest, change-gated

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: `plan_convergence` (pure planner)

**Files:**
- Modify: `scripts/config_sync_plugins.py`
- Test: `tests/test_plugin_convergence.py` (new)

**Interfaces:**
- Consumes: `PluginRegistryReader` (injected), `SyncContext`. Reads `repo_dir/plugins/*.json`.
- Produces:
  - `@dataclass PlannedAction`: `verb: str`, `target: str`, `detail: dict = {}`. Verbs: `"add_marketplace" | "update_marketplace" | "install_plugin" | "update_plugin"`.
  - `@dataclass MarketplacePlan`: `actions: list = []`, `skipped: list = []`.
  - `plan_convergence(context: SyncContext, reader: PluginRegistryReader) -> MarketplacePlan`. Never emits any uninstall verb.

- [ ] **Step 1: Write the failing test**

Create `tests/test_plugin_convergence.py`:

```python
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import config_sync_plugins as plugins_module  # noqa: E402
import config_sync_propagators as propagators  # noqa: E402


class _FakeReader:
    def __init__(self, installed=None, marketplaces=None):
        self._installed = installed or {}
        self._marketplaces = marketplaces or {}

    def installed_plugins(self):
        return dict(self._installed)

    def known_marketplaces(self):
        return dict(self._marketplaces)


def _write_manifest(repo_dir, machine_id, marketplaces, plugins):
    manifest_dir = repo_dir / "plugins"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / f"{machine_id}.json").write_text(json.dumps({
        "machine_id": machine_id, "exported_at": "2026-01-01T00:00:00+00:00",
        "marketplaces": marketplaces, "plugins": plugins,
    }))


def _verbs(plan):
    return [(action.verb, action.target) for action in plan.actions]


def test_plan_installs_absent_updates_present_and_registers_marketplace(tmp_path):
    repo_dir = tmp_path / "repo"
    _write_manifest(
        repo_dir, "m1",
        marketplaces={"official": {"source": {"source": "github", "repo": "a/b"}}},
        plugins={
            "new@official": {"marketplace": "official", "name": "new", "version": "1.0"},
            "have@official": {"marketplace": "official", "name": "have", "version": "2.0"},
        },
    )
    context = propagators.SyncContext(claude_dir=tmp_path / ".claude", repo_dir=repo_dir)
    reader = _FakeReader(installed={"have@official": {"version": "1.9"}}, marketplaces={})  # marketplace absent

    plan = plugins_module.plan_convergence(context, reader)
    verbs = _verbs(plan)

    assert ("add_marketplace", "official") in verbs          # not registered locally + source known
    assert ("update_marketplace", "official") in verbs       # always refresh (the #22 fix)
    assert ("install_plugin", "new@official") in verbs       # absent → install
    assert ("update_plugin", "have@official") in verbs       # present → converge to latest
    assert not any(verb.startswith("uninstall") for verb, _ in verbs)   # never uninstall


def test_plan_never_uninstalls_local_only_plugin(tmp_path):
    repo_dir = tmp_path / "repo"
    _write_manifest(repo_dir, "m1", marketplaces={}, plugins={})   # manifest desires nothing
    context = propagators.SyncContext(claude_dir=tmp_path / ".claude", repo_dir=repo_dir)
    reader = _FakeReader(installed={"local-only@official": {"version": "1.0"}},
                         marketplaces={"official": {"source": {"source": "github", "repo": "a/b"}}})

    plan = plugins_module.plan_convergence(context, reader)
    assert plan.actions == []


def test_plan_skips_plugin_when_marketplace_source_unknown(tmp_path):
    repo_dir = tmp_path / "repo"
    _write_manifest(repo_dir, "m1",
                    marketplaces={"ghost": {"source": None}},   # unregistered + no source
                    plugins={"x@ghost": {"marketplace": "ghost", "name": "x", "version": "1"}})
    context = propagators.SyncContext(claude_dir=tmp_path / ".claude", repo_dir=repo_dir)
    reader = _FakeReader(installed={}, marketplaces={})

    plan = plugins_module.plan_convergence(context, reader)
    assert plan.actions == []
    assert any("ghost" in reason for reason in plan.skipped)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_plugin_convergence.py -v`
Expected: FAIL — `AttributeError: module 'config_sync_plugins' has no attribute 'plan_convergence'`.

- [ ] **Step 3: Implement the dataclasses + planner**

Append to `scripts/config_sync_plugins.py`:

```python
@dataclass
class PlannedAction:
    verb: str            # add_marketplace | update_marketplace | install_plugin | update_plugin
    target: str          # marketplace name or plugin key
    detail: dict = field(default_factory=dict)


@dataclass
class MarketplacePlan:
    actions: list = field(default_factory=list)     # list[PlannedAction]
    skipped: list = field(default_factory=list)     # list[str] human reasons


def plan_convergence(context: propagators.SyncContext, reader: PluginRegistryReader) -> MarketplacePlan:
    """Pure planner: union all repo manifests, diff against the live registry,
    emit ordered actions (marketplaces first). Never emits an uninstall."""
    desired_marketplaces: dict = {}    # name -> source (or None)
    desired_plugins: dict = {}         # key -> meta
    manifests_dir = context.repo_dir / "plugins"
    if manifests_dir.exists():
        for manifest_path in sorted(manifests_dir.glob("*.json")):
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            for marketplace_name, marketplace_meta in data.get("marketplaces", {}).items():
                desired_marketplaces.setdefault(marketplace_name, (marketplace_meta or {}).get("source"))
            for plugin_key, plugin_meta in data.get("plugins", {}).items():
                desired_plugins[plugin_key] = plugin_meta

    local_marketplaces = reader.known_marketplaces()
    installed = reader.installed_plugins()

    plan = MarketplacePlan()
    unresolved_marketplaces = set()
    for marketplace_name in sorted(desired_marketplaces):
        source = desired_marketplaces[marketplace_name]
        if marketplace_name not in local_marketplaces:
            if source:
                plan.actions.append(PlannedAction("add_marketplace", marketplace_name, {"source": source}))
            else:
                plan.skipped.append(f"marketplace {marketplace_name}: not registered and source unknown")
                unresolved_marketplaces.add(marketplace_name)
                continue
        plan.actions.append(PlannedAction("update_marketplace", marketplace_name))

    for plugin_key in sorted(desired_plugins):
        marketplace_name = plugin_key.split("@", 1)[1] if "@" in plugin_key else ""
        if marketplace_name in unresolved_marketplaces:
            plan.skipped.append(f"plugin {plugin_key}: marketplace {marketplace_name} unavailable")
            continue
        if plugin_key in installed:
            current_version = installed[plugin_key].get("version", "unknown")
            plan.actions.append(PlannedAction("update_plugin", plugin_key, {"current_version": current_version}))
        else:
            plan.actions.append(PlannedAction("install_plugin", plugin_key))
    return plan
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_plugin_convergence.py -v`
Expected: PASS (all three tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/config_sync_plugins.py tests/test_plugin_convergence.py
git commit -m "feat(config-sync): plan_convergence — pure planner, union manifests, never uninstall

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: `PluginInstaller` port + `execute_plan` + `ClaudePluginHost` (mutate side)

**Files:**
- Modify: `scripts/config_sync_plugins.py`
- Test: `tests/test_plugin_convergence.py` (extend)

**Interfaces:**
- Consumes: `MarketplacePlan`, `PlannedAction`, `SyncContext`.
- Produces:
  - `@dataclass ActionOutcome`: `verb: str`, `target: str`, `ok: bool`, `message: str = ""`.
  - `@dataclass MarketplaceResult`: `outcomes: list = []`, `skipped: list = []`.
  - `PluginInstaller` Protocol: `add_marketplace(name, source) -> ActionOutcome`, `update_marketplace(name) -> ActionOutcome`, `install_plugin(key) -> ActionOutcome`, `update_plugin(key) -> ActionOutcome`.
  - `execute_plan(context, plan, installer) -> MarketplaceResult`.
  - `ClaudePluginHost` mutate methods (subprocess).

- [ ] **Step 0: Verify the real `claude plugin` subcommands (do not skip)**

Run: `claude plugin --help` and `claude plugin marketplace --help`
Confirm the exact spellings used below: `claude plugin marketplace add <spec>`, `claude plugin marketplace update <name>`, `claude plugin install <key>`, `claude plugin update <key>`. If any differ, adjust the `ClaudePluginHost` `_run([...])` argument lists in Step 3 to match — the tests use a fake installer and do not depend on the exact strings, so only the real host needs correcting.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_plugin_convergence.py`:

```python
class _FakeInstaller:
    def __init__(self, fail_targets=None):
        self.calls = []
        self._fail_targets = set(fail_targets or [])

    def _outcome(self, verb, target):
        self.calls.append((verb, target))
        ok = target not in self._fail_targets
        return plugins_module.ActionOutcome(verb, target, ok=ok, message="" if ok else "boom")

    def add_marketplace(self, name, source):
        return self._outcome("add_marketplace", name)

    def update_marketplace(self, name):
        return self._outcome("update_marketplace", name)

    def install_plugin(self, key):
        return self._outcome("install_plugin", key)

    def update_plugin(self, key):
        return self._outcome("update_plugin", key)


def test_execute_plan_runs_each_action_and_preserves_skips():
    plan = plugins_module.MarketplacePlan(
        actions=[
            plugins_module.PlannedAction("add_marketplace", "official", {"source": {"source": "github", "repo": "a/b"}}),
            plugins_module.PlannedAction("install_plugin", "new@official"),
        ],
        skipped=["plugin z@ghost: marketplace ghost unavailable"],
    )
    installer = _FakeInstaller()
    context = propagators.SyncContext(claude_dir=Path("/x"), repo_dir=Path("/y"))

    result = plugins_module.execute_plan(context, plan, installer)

    assert installer.calls == [("add_marketplace", "official"), ("install_plugin", "new@official")]
    assert all(outcome.ok for outcome in result.outcomes)
    assert result.skipped == ["plugin z@ghost: marketplace ghost unavailable"]


def test_execute_plan_captures_failure_without_aborting():
    plan = plugins_module.MarketplacePlan(actions=[
        plugins_module.PlannedAction("install_plugin", "bad@official"),
        plugins_module.PlannedAction("install_plugin", "good@official"),
    ])
    installer = _FakeInstaller(fail_targets={"bad@official"})
    context = propagators.SyncContext(claude_dir=Path("/x"), repo_dir=Path("/y"))

    result = plugins_module.execute_plan(context, plan, installer)

    outcomes = {outcome.target: outcome.ok for outcome in result.outcomes}
    assert outcomes == {"bad@official": False, "good@official": True}   # continues past failure
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_plugin_convergence.py -k execute_plan -v`
Expected: FAIL — `AttributeError: module 'config_sync_plugins' has no attribute 'ActionOutcome'`.

- [ ] **Step 3: Implement the dataclasses, `execute_plan`, and the mutate side**

Append the dataclasses + `execute_plan` to `scripts/config_sync_plugins.py`:

```python
@dataclass
class ActionOutcome:
    verb: str
    target: str
    ok: bool
    message: str = ""


@dataclass
class MarketplaceResult:
    outcomes: list = field(default_factory=list)    # list[ActionOutcome]
    skipped: list = field(default_factory=list)


@runtime_checkable
class PluginInstaller(Protocol):
    def add_marketplace(self, name: str, source: dict) -> ActionOutcome: ...

    def update_marketplace(self, name: str) -> ActionOutcome: ...

    def install_plugin(self, key: str) -> ActionOutcome: ...

    def update_plugin(self, key: str) -> ActionOutcome: ...


def execute_plan(context: propagators.SyncContext, plan: MarketplacePlan,
                 installer: PluginInstaller) -> MarketplaceResult:
    """Run each planned action via the injected installer; capture per-action
    outcomes and never abort the batch on a single failure."""
    result = MarketplaceResult(skipped=list(plan.skipped))
    for action in plan.actions:
        if action.verb == "add_marketplace":
            outcome = installer.add_marketplace(action.target, action.detail.get("source", {}))
        elif action.verb == "update_marketplace":
            outcome = installer.update_marketplace(action.target)
        elif action.verb == "install_plugin":
            outcome = installer.install_plugin(action.target)
        elif action.verb == "update_plugin":
            outcome = installer.update_plugin(action.target)
        else:
            outcome = ActionOutcome(action.verb, action.target, ok=False, message="unknown verb")
        result.outcomes.append(outcome)
    return result
```

Then add the mutate methods to the existing `ClaudePluginHost` class (below its read methods):

```python
    def _run(self, arguments: list) -> tuple:
        try:
            completed = subprocess.run(
                ["claude", "plugin", *arguments],
                capture_output=True, text=True, timeout=180,
            )
            ok = completed.returncode == 0
            message = (completed.stderr or completed.stdout or "").strip()[-500:]
            return ok, message
        except FileNotFoundError:
            return False, "claude CLI not found"
        except subprocess.TimeoutExpired:
            return False, "claude plugin command timed out"

    def add_marketplace(self, name: str, source: dict) -> ActionOutcome:
        source = source or {}
        spec = source.get("repo") if source.get("source") == "github" else source.get("url")
        if not spec:
            return ActionOutcome("add_marketplace", name, ok=False, message="no source spec")
        ok, message = self._run(["marketplace", "add", spec])
        return ActionOutcome("add_marketplace", name, ok=ok, message=message)

    def update_marketplace(self, name: str) -> ActionOutcome:
        ok, message = self._run(["marketplace", "update", name])
        return ActionOutcome("update_marketplace", name, ok=ok, message=message)

    def install_plugin(self, key: str) -> ActionOutcome:
        ok, message = self._run(["install", key])
        return ActionOutcome("install_plugin", key, ok=ok, message=message)

    def update_plugin(self, key: str) -> ActionOutcome:
        ok, message = self._run(["update", key])
        return ActionOutcome("update_plugin", key, ok=ok, message=message)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_plugin_convergence.py -v`
Expected: PASS (all five tests). No subprocess is spawned — the fake installer is used.

- [ ] **Step 5: Commit**

```bash
git add scripts/config_sync_plugins.py tests/test_plugin_convergence.py
git commit -m "feat(config-sync): PluginInstaller port + execute_plan + ClaudePluginHost mutations

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: `export_propagators()` + wire `propagate-export`; retire `default_propagators()`

**Files:**
- Modify: `scripts/config_sync_plugins.py` (add `export_propagators`)
- Modify: `scripts/config_sync.py:1088-1092` (`cmd_propagate_export`)
- Modify: `scripts/config_sync_propagators.py` (remove `default_propagators`)
- Test: `tests/test_propagators.py` (update the `default_propagators` test); `tests/test_propagate_cli.py` (extend)

**Interfaces:**
- Consumes: `MarketplacePropagator`, `propagators.SnapshotPropagator`, `propagators.ContentBundlePropagator`, `propagators.run_export`.
- Produces: `export_propagators() -> list` = `[SnapshotPropagator(), ContentBundlePropagator(), MarketplacePropagator()]`. `cmd_propagate_export` now sweeps it.

- [ ] **Step 1: Write/adjust the failing tests**

Add to `scripts/config_sync_plugins.py` consumers — first the test. In `tests/test_propagators.py`, replace `test_default_propagators_runs_both_channels` (the last test, ~lines 191-200) with:

```python
def test_export_propagators_include_marketplace(tmp_path):
    import config_sync_plugins as plugins_module
    names = {propagator.name for propagator in plugins_module.export_propagators()}
    assert names == {"snapshot", "content-bundle", "marketplace"}
```

Then extend `tests/test_propagate_cli.py` with a case proving the CLI now writes a plugin manifest:

```python
def test_propagate_export_writes_plugin_manifest(claude_home, tmp_path, capsys):
    plugins_dir = claude_home / "plugins"
    plugins_dir.mkdir(parents=True)
    (plugins_dir / "installed_plugins.json").write_text(config_sync.json.dumps({
        "version": 2, "plugins": {"superpowers@official": [{"version": "6.1.1"}]}}))
    (plugins_dir / "known_marketplaces.json").write_text(config_sync.json.dumps({
        "official": {"source": {"source": "github", "repo": "a/b"}}}))
    (claude_home / "config-sync-machine-id").write_text("cli1")
    repo = tmp_path / "repo"
    repo.mkdir()

    config_sync.cmd_propagate_export(str(repo))
    capsys.readouterr()

    manifest = config_sync.json.loads((repo / "plugins" / "cli1.json").read_text())
    assert "superpowers@official" in manifest["plugins"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_propagators.py::test_export_propagators_include_marketplace tests/test_propagate_cli.py::test_propagate_export_writes_plugin_manifest -v`
Expected: FAIL — `AttributeError: module 'config_sync_plugins' has no attribute 'export_propagators'`.

- [ ] **Step 3: Add `export_propagators()` and remove `default_propagators()`**

Append to `scripts/config_sync_plugins.py`:

```python
def export_propagators() -> list:
    """Composition root for the export sweep: config snapshot, skill/agent
    bundles, and the marketplace plugin manifest. Open/closed extension point."""
    return [
        propagators.SnapshotPropagator(),
        propagators.ContentBundlePropagator(),
        MarketplacePropagator(),
    ]
```

In `scripts/config_sync_propagators.py`, **delete** the now-obsolete `default_propagators()`:

```python
def default_propagators() -> list:
    """Composition root — the ordered list injected into run_export/run_apply.
    C2 appends MarketplacePropagator() here (open/closed)."""
    return [SnapshotPropagator(), ContentBundlePropagator()]
```

- [ ] **Step 4: Point `cmd_propagate_export` at `export_propagators()`**

In `scripts/config_sync.py`, rewrite `cmd_propagate_export`:

```python
def cmd_propagate_export(repo_path):
    propagators, context = _sync_context(repo_path)
    import config_sync_plugins as plugins_module
    results = propagators.run_export(context, plugins_module.export_propagators())
    print(json.dumps({result.propagator: {"written": result.written, "skipped": result.skipped}
                      for result in results}, indent=2))
```

- [ ] **Step 5: Confirm `default_propagators` is fully gone**

Run: `grep -rn "default_propagators" scripts/ tests/`
Expected: no matches.

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — export sweep now includes the marketplace channel; all prior tests green.

- [ ] **Step 7: Commit**

```bash
git add scripts/config_sync_plugins.py scripts/config_sync.py scripts/config_sync_propagators.py tests/test_propagators.py tests/test_propagate_cli.py
git commit -m "feat(config-sync): export_propagators() wires MarketplacePropagator into propagate-export

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: CLI commands `plugins-plan` / `plugins-apply`

**Files:**
- Modify: `scripts/config_sync.py` (add two commands; register in `COMMANDS` ~line 1118)
- Test: `tests/test_plugins_cli.py` (new)

**Interfaces:**
- Consumes: `plugins_module.plan_convergence`, `plugins_module.execute_plan`, `plugins_module.ClaudePluginHost`, `_sync_context`.
- Produces: `cmd_plugins_plan(repo_path, host=None)` prints `{"actions":[{verb,target,detail}], "skipped":[…]}`; `cmd_plugins_apply(repo_path, host=None)` prints `{"outcomes":[{verb,target,ok,message}], "skipped":[…]}`. Both default `host=None` → `ClaudePluginHost(context)`; a fake host (implementing both ports) is injected in tests. Registered as `("plugins-plan", 1)` / `("plugins-apply", 1)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_plugins_cli.py`:

```python
import json
import config_sync


class _FakeHost:
    """Implements both ports so it can drive plan (reader) and apply (installer)."""
    def __init__(self):
        self.calls = []

    def installed_plugins(self):
        return {}

    def known_marketplaces(self):
        return {"official": {"source": {"source": "github", "repo": "a/b"}}}

    def add_marketplace(self, name, source):
        import config_sync_plugins as plugins_module
        self.calls.append(("add_marketplace", name))
        return plugins_module.ActionOutcome("add_marketplace", name, ok=True)

    def update_marketplace(self, name):
        import config_sync_plugins as plugins_module
        self.calls.append(("update_marketplace", name))
        return plugins_module.ActionOutcome("update_marketplace", name, ok=True)

    def install_plugin(self, key):
        import config_sync_plugins as plugins_module
        self.calls.append(("install_plugin", key))
        return plugins_module.ActionOutcome("install_plugin", key, ok=True)

    def update_plugin(self, key):
        import config_sync_plugins as plugins_module
        self.calls.append(("update_plugin", key))
        return plugins_module.ActionOutcome("update_plugin", key, ok=True)


def _seed_manifest(repo):
    manifest_dir = repo / "plugins"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "m1.json").write_text(json.dumps({
        "machine_id": "m1", "exported_at": "2026-01-01T00:00:00+00:00",
        "marketplaces": {"official": {"source": {"source": "github", "repo": "a/b"}}},
        "plugins": {"new@official": {"marketplace": "official", "name": "new", "version": "1.0"}},
    }))


def test_cmd_plugins_plan_prints_actions(claude_home, tmp_path, capsys):
    repo = tmp_path / "repo"
    _seed_manifest(repo)

    config_sync.cmd_plugins_plan(str(repo), host=_FakeHost())
    payload = json.loads(capsys.readouterr().out)

    verbs = {(action["verb"], action["target"]) for action in payload["actions"]}
    assert ("update_marketplace", "official") in verbs
    assert ("install_plugin", "new@official") in verbs


def test_cmd_plugins_apply_executes_and_reports(claude_home, tmp_path, capsys):
    repo = tmp_path / "repo"
    _seed_manifest(repo)
    host = _FakeHost()

    config_sync.cmd_plugins_apply(str(repo), host=host)
    payload = json.loads(capsys.readouterr().out)

    assert ("install_plugin", "new@official") in host.calls          # actually executed
    assert all(outcome["ok"] for outcome in payload["outcomes"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_plugins_cli.py -v`
Expected: FAIL — `AttributeError: module 'config_sync' has no attribute 'cmd_plugins_plan'`.

- [ ] **Step 3: Implement the two commands and register them**

In `scripts/config_sync.py`, add after `cmd_resolve_bundle` (~line 1111):

```python
def cmd_plugins_plan(repo_path, host=None):
    propagators, context = _sync_context(repo_path)
    import config_sync_plugins as plugins_module
    reader = host if host is not None else plugins_module.ClaudePluginHost(context)
    plan = plugins_module.plan_convergence(context, reader)
    print(json.dumps({
        "actions": [{"verb": action.verb, "target": action.target, "detail": action.detail}
                    for action in plan.actions],
        "skipped": plan.skipped,
    }, indent=2))


def cmd_plugins_apply(repo_path, host=None):
    propagators, context = _sync_context(repo_path)
    import config_sync_plugins as plugins_module
    plugin_host = host if host is not None else plugins_module.ClaudePluginHost(context)
    plan = plugins_module.plan_convergence(context, plugin_host)
    result = plugins_module.execute_plan(context, plan, plugin_host)
    print(json.dumps({
        "outcomes": [{"verb": outcome.verb, "target": outcome.target,
                      "ok": outcome.ok, "message": outcome.message}
                     for outcome in result.outcomes],
        "skipped": result.skipped,
    }, indent=2))
```

Register both in the `COMMANDS` dict (after the `"resolve-bundle"` line):

```python
    "plugins-plan": (cmd_plugins_plan, 1),
    "plugins-apply": (cmd_plugins_apply, 1),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_plugins_cli.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/config_sync.py tests/test_plugins_cli.py
git commit -m "feat(config-sync): plugins-plan / plugins-apply CLI commands (injectable host)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Retire the legacy plugin path (engine + skill) and bump versions

**Files:**
- Modify: `scripts/config_sync.py` (remove the `shared/plugins/` block from `cmd_apply_shared`, ~lines 780-840)
- Modify: `skills/config-sync/SKILL.md` (delete the export heredoc in Step 1; rewrite Step 4b; frontmatter version)
- Modify: `pyproject.toml`, `.claude-plugin/marketplace.json` (version bump)
- Test: `tests/test_apply_shared_no_plugins.py` (new)

**Interfaces:**
- Consumes: `cmd_apply_shared` (retains only `shared/skills|rules|agents`).
- Produces: `cmd_apply_shared` no longer reads `shared/plugins/` or writes `installed_plugins.json`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_apply_shared_no_plugins.py`:

```python
import json
import config_sync


def test_apply_shared_ignores_plugins_and_never_writes_registry(claude_home, tmp_path, capsys):
    repo = tmp_path / "repo"
    plugin_dir = repo / "shared" / "plugins" / "foo@bar"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin-meta.json").write_text(json.dumps({
        "key": "foo@bar", "marketplace": "bar", "name": "foo", "version": "1.0"}))
    (plugin_dir / "somefile.txt").write_text("x")

    config_sync.cmd_apply_shared(str(repo))
    payload = json.loads(capsys.readouterr().out)

    assert not any("foo@bar" in entry for entry in payload["installed"])        # plugins no longer installed here
    assert not (claude_home / "plugins" / "installed_plugins.json").exists()    # registry never hand-written
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_apply_shared_no_plugins.py -v`
Expected: FAIL — the current `cmd_apply_shared` still processes `shared/plugins/`, so `installed_plugins.json` is created and/or `foo@bar` appears in `installed`.

- [ ] **Step 3: Remove the plugin half of `cmd_apply_shared`**

In `scripts/config_sync.py`, delete the entire `shared/plugins/` handling block inside `cmd_apply_shared` — from the comment `# Handle shared plugins: each subdir is named <plugin-key> …` through the end of its `for plugin_dir in sorted(plugins_src.iterdir()):` loop (the block that reads `plugin-meta.json`, copies cache files, and writes `installed_plugins_path`). Keep the earlier `skills`/`rules`/`agents` mapping loop and the final `print(json.dumps({"installed": installed, "skipped": skipped}))`. The function keeps its signature and its skills/rules/agents behavior; it simply no longer touches plugins.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_apply_shared_no_plugins.py -v`
Expected: PASS.

- [ ] **Step 5: Delete the plugin-export heredoc in the skill (Step 1)**

In `skills/config-sync/SKILL.md`, delete the entire plugin-export block in Step 1: the prose paragraph beginning "Then export installed **plugins** to `shared/plugins/`…" and the fenced ```bash python3 - "$REPO" <<'PYEOF' … PYEOF``` heredoc that follows it. Update the immediately-following `git add` line to drop `shared/plugins/`:

```bash
cd "$REPO"
git add machines/ bundles/ plugins/
git diff --cached --quiet && echo "no local changes" || \
  git commit -m "sync: $MACHINE_ID at $(date -u +%Y-%m-%dT%H:%M:%SZ)"

git push origin main 2>&1
```

(The `propagate-export` call already present in Step 1 now writes `plugins/<machine_id>.json` via `MarketplacePropagator`.)

- [ ] **Step 6: Rewrite Step 4b to the plan-then-consent plugin flow**

In `skills/config-sync/SKILL.md`, replace the body of **Step 4b** with the marketplace convergence flow. It must:
1. Run `PLAN=$(python3 "$ENGINE" plugins-plan "$REPO")` and parse `.actions` / `.skipped`.
2. If `.actions` is empty, report "plugins already converged" and skip to the next step.
3. If non-empty, render the actions (`add_marketplace` / `update_marketplace` / `install_plugin` / `update_plugin` with targets) and use **AskUserQuestion** — "Apply these plugin changes? (refresh N marketplace(s), install M, update K)". On decline, stop (nothing is mutated).
4. On consent, run `python3 "$ENGINE" plugins-apply "$REPO"`, parse `.outcomes`, and tell the user what installed/updated (and surface any `ok:false` messages).
5. Keep the existing `apply-shared` call, but reword its prose to "installs legacy shared skills/rules/agents from older machines" (plugins are handled above).

Use this replacement Markdown for Step 4b:

````markdown
## Step 4b — Converge marketplace plugins (plan → consent → apply)

Skills/agents flow through `propagate-apply` (above); config through the snapshot
propagator. **Plugins** converge here from the desired-state manifest. First compute
the plan (pure — nothing is mutated):

```bash
PLAN=$(python3 "$ENGINE" plugins-plan "$REPO")
echo "$PLAN"
```

Parse `$PLAN`. If `.actions` is empty, tell the user "plugins already up to date" and
continue. Otherwise render the actions (each has `verb` + `target`) and ask with
**AskUserQuestion**: "Apply these plugin changes? — refresh N marketplace(s),
install M, update K plugin(s)." Also surface any `.skipped` entries (e.g. a
marketplace whose source is unknown).

If the user declines, stop here — nothing has been changed. If they accept, execute:

```bash
APPLIED_PLUGINS=$(python3 "$ENGINE" plugins-apply "$REPO")
echo "$APPLIED_PLUGINS"
```

Parse `.outcomes` and report which plugins were installed/updated; surface any
`ok:false` entries with their `message`. Remind the user to restart Claude to
activate newly installed plugins.

Finally, install any **legacy** shared skills/rules/agents from older machines
(never overwriting local copies):

```bash
SHARED_RESULT=$(python3 "$ENGINE" apply-shared "$REPO")
echo "$SHARED_RESULT"
```
````

- [ ] **Step 7: Bump versions**

- `.claude-plugin/marketplace.json`: bump the plugin `version` `0.7.0` → `0.8.0`.
- `pyproject.toml`: bump `version` `0.7.0` → `0.8.0`.
- `skills/config-sync/SKILL.md` frontmatter: bump `metadata.version` `0.6.0` → `0.7.0`.

(Read each file first to confirm the current value; if it differs, bump from whatever is present by one minor for the two `0.7.0`s and the skill.)

- [ ] **Step 8: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — entire suite green (C1 + all C2 tests).

- [ ] **Step 9: Commit**

```bash
git add scripts/config_sync.py skills/config-sync/SKILL.md pyproject.toml .claude-plugin/marketplace.json tests/test_apply_shared_no_plugins.py
git commit -m "feat(config-sync): retire legacy plugin cache-copy; skill uses plan-then-consent (closes #16 #22 #26)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: End-to-end verification + finish the branch

**Files:** none (verification + handoff)

- [ ] **Step 1: Full suite + module import sanity**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all tests).

Run: `.venv/bin/python -c "import sys; sys.path.insert(0,'scripts'); import config_sync, config_sync_propagators, config_sync_plugins; print('imports OK')"`
Expected: `imports OK` (no circular-import error — dependency is one-way `plugins → propagators`).

- [ ] **Step 2: Smoke-test the CLI surface against a throwaway repo**

```bash
python3 scripts/config_sync.py propagate-export /tmp/c2-smoke-repo 2>&1 | head -20
python3 scripts/config_sync.py plugins-plan /tmp/c2-smoke-repo 2>&1 | head -40
```
Expected: `propagate-export` prints a JSON block including a `"marketplace"` key; `plugins-plan` prints `{"actions": […], "skipped": […]}` reflecting the real local registry. (This reads real `~/.claude` registry files but writes only to `/tmp/c2-smoke-repo` and **mutates nothing** — `plugins-apply` is intentionally not run here.) Clean up: `rm -rf /tmp/c2-smoke-repo`.

- [ ] **Step 3: Finish the branch**

**REQUIRED SUB-SKILL:** Use superpowers:finishing-a-development-branch — verify tests, then present the 4 options (merge / PR / keep / discard) and execute the choice. The issues closed by this branch are #22, #16, #26 (fully) and #24, #25 (for marketplace plugins); include that in the PR body if a PR is created, and note the deferred private-plugin channel as a follow-up.

---

## Self-Review

**1. Spec coverage:**
- §2 decision 1 (registry source of truth) → Tasks 2/3 read `installed_plugins.json` + `known_marketplaces.json`; nothing else is a source. ✓
- §2 decision 2 (marketplace-only, defer local) → Task 3 classification excludes unresolvable marketplaces (no local channel built). ✓
- §2 decision 3 (plan-then-consent) → Task 4 pure planner + Task 7 `plugins-plan`, Task 8 Step 6 AskUserQuestion + `plugins-apply`. ✓
- §2 decision 4 (converge-to-latest, never uninstall) → Task 4 update/install verbs, no uninstall, `test_plan_never_uninstalls_local_only_plugin`. ✓
- §3.1 Exporter/Applier split → Task 1. ✓
- §3.2 two ISP ports + injected ClaudePluginHost → Tasks 2 (reader), 5 (installer), 7 (injection). ✓
- §5 manifest shape + change-gate → Task 3. ✓
- §6 data flow (export sweep, plan/consent/execute) → Tasks 6, 7, 8. ✓
- §7 real host + verification step → Task 5 Step 0 + mutate methods. ✓
- §8 error handling (claude absent, per-action failure, source unknown) → Task 5 `_run` FileNotFoundError, `test_execute_plan_captures_failure`, Task 4 source-unknown skip. ✓
- §9 backward-compat (apply-shared ignores plugins) → Task 8. ✓
- §10 tests → every task is TDD. ✓
- §12 issue closure → Task 9 Step 3 PR body. ✓

**2. Placeholder scan:** No TBD/TODO; every code step shows complete code; the one runtime-verification step (Task 5 Step 0) is a concrete `--help` check with a named fallback, not a placeholder. ✓

**3. Type consistency:** `SyncContext(claude_dir, repo_dir)`, `ExportResult(propagator, written, skipped)`, `PlannedAction(verb, target, detail)`, `MarketplacePlan(actions, skipped)`, `ActionOutcome(verb, target, ok, message)`, `MarketplaceResult(outcomes, skipped)`, `plan_convergence(context, reader)`, `execute_plan(context, plan, installer)`, `export_propagators()`, `apply_propagators()`, `cmd_plugins_plan/apply(repo_path, host=None)` — names/signatures identical across every task that references them. Reader returns **flattened** `{key: entry}` in Task 2 and is consumed as such in Task 4. ✓
