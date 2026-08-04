# Rejection Ledger Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The three remaining rejectable kinds — `settings-key`, `plugin`, and `hook-registration` — become addressable and enforceable, so an operator can durably decline a settings key, a marketplace plugin, or one specific hook registration.

**Architecture:** Phase 1 left three seams open: `REJECTION_KINDS` already names all five kinds, `RejectionRecord.tier` exists unused, and `_resolve_rejection_address` raises `ValueError` for anything it cannot yet address. This plan fills them. `settings-key` and `plugin` are ordinary `UnitAddressor`s living beside the snapshot ones. `hook-registration` gets its own module and its own **tiered** addressor protocol, because it is the only kind whose identity must be *resolved* rather than read — a hook registration is a list element with no natural key, and keying it on the whole command string is a defect this codebase already carries scar tissue from.

**Tech Stack:** Python 3.14, stdlib only (`json`, `hashlib`, `dataclasses`, `pathlib`), pytest, black, ruff.

## Global Constraints

- **No new runtime dependencies.** Stdlib only; the engine runs under `bin/mente-python`, which may resolve to a bare system interpreter.
- **Formatting is not hand-edited.** `uv run black .` owns whitespace; `uv run ruff check --fix .` must be clean before every commit. Lint ruff cannot autofix is a blocker, not a warning. Note **ruff N818**: every exception class name ends in `Error`.
- **Descriptive names throughout**, including in comprehensions and generator expressions — no single-letter or abbreviated loop variables.
- **Timestamps are UTC ISO 8601 strings** (`datetime.now(UTC).isoformat()`). They are compared lexicographically; do not parse them.
- **Fail closed.** A corrupt ledger aborts with `CorruptRejectionLedgerError`; it never degrades to "no rejections".
- **Scope is a correctness boundary.** Anything writing SHARED state (`cmd_consolidate`) gets a **network-only** policy. Anything writing LOCAL state (`SnapshotPropagator.apply`, the import merge, `plugins-plan`, `plan_hook_wiring`) gets the **composite**. Never hand the composite to a shared-state writer.
- **Never touch the operator's real `~/.claude` from a test.** `scripts/config_sync.py:74-75` computes `HOME`/`CLAUDE_DIR` as module-level globals **at import time**, so monkeypatching `pathlib.Path.home` does not work. Use the repo's `claude_home` fixture (`tests/conftest.py:52-70`), which patches `config_sync.HOME`, `CLAUDE_DIR`, `CONFIG_FILE`, `CONFIG_REPO`, `PLUGINS_DIR` and `INSTALLED_PLUGINS_FILE`. Follow the shape `tests/test_rejection_cli.py` settled on.
- **A rejection withholds; it never deletes.** Consistent with Phase 1: apply simply does not write the content. Removing something already on disk is `hooks-prune`'s job (hooks) or the operator's (settings). Say so where it could surprise.
- **Tests import from `scripts/` directly** — `tests/conftest.py` already puts `scripts/` on `sys.path`. `scripts/` is a flat set of sibling scripts, not a package, so cross-script imports inside `scripts/` are **deferred imports inside functions**, matching the existing code.
- **Run the suite with** `uv run pytest tests/ -q` from the repo root. Baseline at the start of this plan: **1328 passing**.
- Branch: `feat/config-sync-rejection-ledger-phase-2`. Commit after every task.

## File Structure

| File | Responsibility |
|---|---|
| `scripts/config_sync_rejections.py` (modify) | Gains `settings_key_address`, `SettingsKeyAddressor`, `filter_settings_keys`, `PluginAddressor`. Ordinary addressors only — nothing tiered. |
| `scripts/config_sync_rejection_hooks.py` (create) | The tiered hook addressor and nothing else. Separate because it is the only addressor with a resolution strategy, and the easy kinds must not inherit its machinery (ISP). |
| `scripts/config_sync.py` (modify) | `_resolve_rejection_address` learns three kinds; `cmd_reject` learns `--key`, `--event`, `--matcher` and records `tier`; `cmd_consolidate` filters settings keys; the whole-file guard. |
| `scripts/config_sync_propagators.py` (modify) | The import-merge filter point for local `settings-key` rejections. |
| `scripts/config_sync_plugins.py` (modify) | `plan_convergence` gains an injected policy. |
| `scripts/config_sync_hooks.py` (modify) | `plan_hook_wiring` gains an injected policy. |
| `skills/config-sync/SKILL.md` (modify) | Documents the three new kinds and their addressing options. |
| `tests/test_settings_key_rejections.py` (create) | Key-path addressing and the pure settings filter. |
| `tests/test_settings_key_wiring.py` (create) | Both settings filter points, and the scope asymmetry between them. |
| `tests/test_plugin_rejections.py` (create) | Plugin addressing and `plan_convergence` filtering. |
| `tests/test_hook_rejection_tiers.py` (create) | The three tiers, downward ambiguity, and the never-guess rule. This is the suite the design spec demands. |
| `tests/test_hook_rejection_wiring.py` (create) | `plan_hook_wiring` filtering, and that an already-registered hook is not deleted. |
| `tests/test_rejection_cli_phase2.py` (create) | The command surface for the three new kinds, plus the whole-file guard. |
| `tests/test_rejection_phase2_end_to_end.py` (create) | One walk per kind across every module boundary. |

**Out of scope.** Per-content provenance — the fix for Phase 1's bounded convergence — is **Phase 3** and needs a design session first. Nothing here may change the snapshot schema or add provenance fields.

---

### Task 1: Settings key addressing and the pure filter

**Files:**
- Modify: `scripts/config_sync_rejections.py`
- Test: `tests/test_settings_key_rejections.py`

**Interfaces:**
- Consumes: `RejectionTarget`, `NullRejectionPolicy` from Phase 1.
- Produces: `settings_key_address(key_path: tuple) -> str`; `SettingsKeyAddressor` with `kind = "settings-key"`, `identify(key_path: tuple) -> str`, `matches(address: str, key_path: tuple) -> bool`; `filter_settings_keys(settings: dict, policy, source_timestamp: str) -> tuple[dict, list[str]]` returning `(kept_settings, removed_addresses)`.

A key path is a tuple of strings naming a path into the deep-merged settings object: `("permissions", "defaultMode")`, `("enabledPlugins", "open-memory@open-memory")`. It is encoded as a JSON **list** — a settings key may legitimately contain a dot or a bracket, so no delimited encoding is safe.

`filter_settings_keys` is a **pure** filter with no I/O: it takes a parsed dict and returns a new one. It never mutates its input, and it never raises — Phase 1 established that a filter which raises cannot be used to preview anything.

- [ ] **Step 1: Write the failing test**

```python
"""Addressing one key inside settings.json, and subtracting rejected keys.

A settings key path is a LIST in JSON, not a delimited string: `permissions.allow`
would be indistinguishable from a literal top-level key named `permissions.allow`,
and plugin ids legitimately contain `@` and `-`.
"""

import json

import config_sync_rejections as rejections
from config_sync_rejections import (
    NullRejectionPolicy,
    SettingsKeyAddressor,
    filter_settings_keys,
)

SETTINGS = {
    "permissions": {"defaultMode": "acceptEdits", "allow": ["Bash(ls:*)"]},
    "enabledPlugins": {"open-memory@open-memory": True, "keep-me@keep-me": True},
    "model": "opus",
}


class _RejectingPolicy:
    """Rejects exactly the addresses it was given. Substitutes for the real policy
    so addressing is tested without a ledger on disk."""

    def __init__(self, rejected_addresses):
        self._rejected = set(rejected_addresses)

    def is_rejected(self, target, source_timestamp):
        return target.address in self._rejected


def test_a_key_path_is_json_so_a_key_may_contain_any_character():
    address = rejections.settings_key_address(("enabledPlugins", "open-memory@open-memory"))
    assert json.loads(address) == ["enabledPlugins", "open-memory@open-memory"]


def test_a_dotted_key_is_not_confused_with_a_nested_path():
    nested = rejections.settings_key_address(("permissions", "defaultMode"))
    literal = rejections.settings_key_address(("permissions.defaultMode",))
    assert nested != literal


def test_the_addressor_round_trips_a_key_path():
    addressor = SettingsKeyAddressor()
    address = addressor.identify(("permissions", "defaultMode"))
    assert addressor.matches(address, ("permissions", "defaultMode"))
    assert not addressor.matches(address, ("permissions", "allow"))
    assert addressor.kind == "settings-key"


def test_null_policy_leaves_settings_untouched():
    kept, removed = filter_settings_keys(SETTINGS, NullRejectionPolicy(), "2026-08-03T09:00:00+00:00")
    assert kept == SETTINGS
    assert removed == []


def test_a_rejected_leaf_is_removed_and_its_siblings_survive():
    address = rejections.settings_key_address(("permissions", "defaultMode"))
    kept, removed = filter_settings_keys(
        SETTINGS, _RejectingPolicy([address]), "2026-08-03T09:00:00+00:00"
    )
    assert "defaultMode" not in kept["permissions"]
    assert kept["permissions"]["allow"] == ["Bash(ls:*)"]
    assert removed == [address]


def test_a_rejected_subtree_takes_its_children_with_it():
    address = rejections.settings_key_address(("permissions",))
    kept, _removed = filter_settings_keys(
        SETTINGS, _RejectingPolicy([address]), "2026-08-03T09:00:00+00:00"
    )
    assert "permissions" not in kept
    assert kept["model"] == "opus"


def test_rejecting_one_plugin_entry_leaves_the_others():
    address = rejections.settings_key_address(("enabledPlugins", "open-memory@open-memory"))
    kept, _removed = filter_settings_keys(
        SETTINGS, _RejectingPolicy([address]), "2026-08-03T09:00:00+00:00"
    )
    assert kept["enabledPlugins"] == {"keep-me@keep-me": True}


def test_the_input_dict_is_never_mutated():
    address = rejections.settings_key_address(("model",))
    before = json.dumps(SETTINGS, sort_keys=True)
    filter_settings_keys(SETTINGS, _RejectingPolicy([address]), "2026-08-03T09:00:00+00:00")
    assert json.dumps(SETTINGS, sort_keys=True) == before


def test_a_rejected_key_that_is_absent_is_not_reported_as_removed():
    address = rejections.settings_key_address(("notPresent",))
    kept, removed = filter_settings_keys(
        SETTINGS, _RejectingPolicy([address]), "2026-08-03T09:00:00+00:00"
    )
    assert kept == SETTINGS
    assert removed == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_settings_key_rejections.py -q`
Expected: FAIL with `ImportError: cannot import name 'SettingsKeyAddressor'`

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/config_sync_rejections.py`:

```python
def settings_key_address(key_path: tuple) -> str:
    """A JSON list rather than a delimited path: a settings key may legitimately
    contain a dot, a bracket or an `@` (plugin ids do), so any separator a flat
    encoding could pick is also a legal key character."""
    return json.dumps(list(key_path), ensure_ascii=False)


class SettingsKeyAddressor:
    """One key path into the deep-merged settings object. Stable by construction —
    unlike a hook registration, a key IS its own identity."""

    kind = "settings-key"

    def identify(self, key_path: tuple) -> str:
        return settings_key_address(key_path)

    def matches(self, address: str, key_path: tuple) -> bool:
        return address == self.identify(key_path)


def filter_settings_keys(settings: dict, policy, source_timestamp: str) -> tuple:
    """Subtract rejected key paths from a parsed settings dict.

    Returns `(kept_settings, removed_addresses)`. Pure: the input is never
    mutated and nothing is read from disk, so a caller can use this to preview.
    A rejected subtree is dropped whole — rejecting `permissions` means the
    operator does not want any of it.
    """
    addressor = SettingsKeyAddressor()
    removed: list = []

    def prune(node, prefix: tuple):
        if not isinstance(node, dict):
            return node
        kept: dict = {}
        for key, value in node.items():
            key_path = prefix + (key,)
            target = RejectionTarget(
                kind=addressor.kind, address=addressor.identify(key_path)
            )
            if policy.is_rejected(target, source_timestamp):
                removed.append(target.address)
                continue
            kept[key] = prune(value, key_path)
        return kept

    return prune(settings, ()), removed
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_settings_key_rejections.py -q`
Expected: 9 passed

- [ ] **Step 5: Format, lint, commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black scripts/config_sync_rejections.py tests/test_settings_key_rejections.py
uv run ruff check --fix scripts/config_sync_rejections.py tests/test_settings_key_rejections.py
uv run pytest tests/ -q
git add scripts/config_sync_rejections.py tests/test_settings_key_rejections.py
git commit -m "feat(config-sync): address and filter settings keys"
```

---

### Task 2: Wire settings-key into both filter points

**Files:**
- Modify: `scripts/config_sync.py` (`cmd_consolidate`)
- Modify: `scripts/config_sync_propagators.py` (`SnapshotPropagator.apply`)
- Test: `tests/test_settings_key_wiring.py`

**Interfaces:**
- Consumes: `filter_settings_keys` from Task 1; `network_rejection_policy` and the `SnapshotPropagator(policy=...)` seam from Phase 1.
- Produces: no new public names. `cmd_consolidate` and `SnapshotPropagator.apply` both subtract settings keys; the `"rejected"` and `rejection_removals` outputs gain those addresses.

`settings.json` travels **inside** the snapshot's `files` dict (`SNAPSHOT_FILES`, `scripts/config_sync.py:89`) as a JSON *string*. `filter_snapshot_files` is markdown-shaped — sections for `.md`, whole-file for everything else — so it passes `settings.json` through untouched. That is why this needs its own pass, applied to the parsed JSON.

The scope asymmetry is the same one Phase 1 established: consolidate writes shared state and gets network-only; apply writes local files and gets the composite.

Note what a local rejection does and does not do: it stops the key being *written* on the way in. `_deep_merge` never deletes, so a key already in the live `settings.json` from an earlier sync stays there — exactly the Phase 1 semantics for a withheld section. Removing it is the operator's own edit.

- [ ] **Step 1: Write the failing test**

```python
"""Both settings filter points, and the scope boundary between them.

Consolidate writes SHARED state, so it must honour network rejections only.
Apply writes LOCAL files, so it honours both — a private veto that reached the
shared snapshot would impose one machine's taste on the network.
"""

import json

import config_sync
from config_sync_propagators import SnapshotPropagator, SyncContext
from config_sync_rejections import (
    CompositeRejectionPolicy,
    LocalRejectionStore,
    RejectionRecord,
    SharedRejectionStore,
    rejection_id_of,
    settings_key_address,
)

REJECTED_AT = "2026-08-03T09:00:00+00:00"
SETTINGS = {
    "permissions": {"defaultMode": "acceptEdits"},
    "model": "opus",
}
ADDRESS = settings_key_address(("permissions", "defaultMode"))


def _settings_blob(settings=None):
    return json.dumps(settings if settings is not None else SETTINGS)


def _record(scope, machine_id="machine-a"):
    return RejectionRecord(
        id=rejection_id_of("settings-key", ADDRESS),
        kind="settings-key",
        address=ADDRESS,
        scope=scope,
        rejected_at=REJECTED_AT,
        machine_id=machine_id,
    )


def _repo(tmp_path, consolidated_settings=None):
    repo = tmp_path / "repo"
    (repo / "machines").mkdir(parents=True)
    (repo / "consolidated").mkdir(parents=True)
    (repo / "machines" / "machine-a.json").write_text(
        json.dumps(
            {
                "machine_id": "machine-a",
                "timestamp": "2026-08-03T08:00:00+00:00",
                "files": {"settings.json": _settings_blob(consolidated_settings)},
            }
        ),
        encoding="utf-8",
    )
    (repo / "consolidated" / "snapshot.json").write_text(
        json.dumps({"files": {"settings.json": _settings_blob(consolidated_settings)}}),
        encoding="utf-8",
    )
    return repo


def _consolidated_settings(repo):
    payload = json.loads((repo / "consolidated" / "snapshot.json").read_text(encoding="utf-8"))
    return json.loads(payload["files"]["settings.json"])


def test_a_network_rejected_key_is_stripped_from_the_consolidated_snapshot(tmp_path, capsys):
    repo = _repo(tmp_path)
    SharedRejectionStore(repo, "machine-a").record(_record("network"))

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert "defaultMode" not in _consolidated_settings(repo)["permissions"]
    assert _consolidated_settings(repo)["model"] == "opus"


def test_a_local_rejected_key_does_not_touch_shared_state(tmp_path, capsys):
    repo = _repo(tmp_path)
    SharedRejectionStore(repo, "machine-a").record(_record("local"))

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert _consolidated_settings(repo)["permissions"]["defaultMode"] == "acceptEdits"


def test_the_stripped_address_is_reported_in_the_rejected_audit_trail(tmp_path, capsys):
    repo = _repo(tmp_path)
    SharedRejectionStore(repo, "machine-a").record(_record("network"))

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    payload = json.loads((repo / "consolidated" / "snapshot.json").read_text(encoding="utf-8"))
    assert ADDRESS in payload["rejected"]


def _apply_context(tmp_path):
    context = SyncContext(claude_dir=tmp_path / "claude", repo_dir=tmp_path / "repo")
    (context.repo_dir / "consolidated").mkdir(parents=True)
    (context.repo_dir / "consolidated" / "snapshot.json").write_text(
        json.dumps(
            {
                "timestamp": "2026-08-03T12:00:00+00:00",
                "files": {"settings.json": _settings_blob()},
            }
        ),
        encoding="utf-8",
    )
    context.claude_dir.mkdir(parents=True, exist_ok=True)
    return context


def test_a_locally_rejected_key_is_never_written_at_apply(tmp_path):
    context = _apply_context(tmp_path)
    store = LocalRejectionStore(tmp_path / "local.json")
    store.record(_record("local"))

    result = SnapshotPropagator(policy=CompositeRejectionPolicy([store])).apply(context)

    written = json.loads((context.claude_dir / "settings.json").read_text(encoding="utf-8"))
    assert "defaultMode" not in written.get("permissions", {})
    # `rejection_removals` carries RejectionRecord objects, not dicts — phase 1's
    # final review widened it from bare address strings so Step 4e could render
    # the machine and time and call `resolve-rejection <id>`. Only
    # `cmd_propagate_apply` serialises them, via `vars()`.
    assert ADDRESS in [removal.address for removal in result.rejection_removals]


def test_without_a_policy_apply_writes_settings_unchanged(tmp_path):
    context = _apply_context(tmp_path)
    SnapshotPropagator().apply(context)
    written = json.loads((context.claude_dir / "settings.json").read_text(encoding="utf-8"))
    assert written["permissions"]["defaultMode"] == "acceptEdits"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_settings_key_wiring.py -q`
Expected: FAIL — `test_a_network_rejected_key_is_stripped_from_the_consolidated_snapshot` finds `defaultMode` still present.

- [ ] **Step 3: Write minimal implementation**

Add this helper to `scripts/config_sync_rejections.py`, so both call sites share one implementation of "parse the blob, filter, re-encode":

```python
def filter_settings_blob(files: dict, policy, source_timestamp: str) -> tuple:
    """Apply `filter_settings_keys` to the `settings.json` entry of a snapshot
    `files` mapping, which carries it as a JSON *string*.

    `filter_snapshot_files` cannot do this: it is markdown-shaped (sections for
    `.md`, whole-file for everything else) and passes `settings.json` through
    untouched. Returns `(kept_files, removed_addresses)`. A blob that does not
    parse is left exactly as it is — repairing it is `clean-settings`' job, and
    a filter that rewrites unparseable input would destroy the evidence.
    """
    blob = files.get("settings.json")
    if not isinstance(blob, str):
        return files, []
    try:
        parsed = json.loads(blob)
    except (json.JSONDecodeError, ValueError):
        return files, []
    if not isinstance(parsed, dict):
        return files, []

    kept_settings, removed = filter_settings_keys(parsed, policy, source_timestamp)
    if not removed:
        return files, []

    kept_files = dict(files)
    kept_files["settings.json"] = json.dumps(kept_settings, indent=2, ensure_ascii=False)
    return kept_files, removed
```

In `scripts/config_sync.py`, inside `cmd_consolidate`, apply it in **both** the `base_files` position and the per-snapshot fold, immediately after the existing `filter_snapshot_files` call in each place:

```python
    base_files, base_removed = rejections_module.filter_snapshot_files(
        base_files, policy, ""
    )
    base_files, base_settings_removed = rejections_module.filter_settings_blob(
        base_files, policy, ""
    )
    rejected_addresses = list(base_removed) + list(base_settings_removed)
```

and, inside the per-snapshot loop:

```python
        incoming_files, incoming_removed = rejections_module.filter_snapshot_files(
            snapshot.get("files", {}), policy, snapshot.get("timestamp", "")
        )
        incoming_files, incoming_settings_removed = (
            rejections_module.filter_settings_blob(
                incoming_files, policy, snapshot.get("timestamp", "")
            )
        )
        rejected_addresses.extend(incoming_removed)
        rejected_addresses.extend(incoming_settings_removed)
```

Leave the existing dedupe of `rejected_addresses` exactly as it is — it now covers settings addresses too.

In `scripts/config_sync_propagators.py`, inside `SnapshotPropagator.apply`, immediately after the existing `filter_snapshot_files` call and its `rejection_removals` extension:

```python
        files, settings_removed_addresses = rejections_module.filter_settings_blob(
            files, self._policy, ""
        )
        result.rejection_removals.extend(
            rejections_module.records_for_addresses(self._policy, settings_removed_addresses)
        )
```

Pass `""`, not the snapshot's `timestamp`, for the same reason the existing call does: `cmd_consolidate` regenerates that timestamp on every run, so it is a *generation* time and can never carry fresh intent. Do not restore the field.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_settings_key_wiring.py -q`
Expected: 6 passed

Then confirm nothing regressed: `uv run pytest tests/ -q`

- [ ] **Step 5: Format, lint, commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black scripts/config_sync.py scripts/config_sync_propagators.py scripts/config_sync_rejections.py tests/test_settings_key_wiring.py
uv run ruff check --fix scripts/config_sync.py scripts/config_sync_propagators.py scripts/config_sync_rejections.py tests/test_settings_key_wiring.py
uv run pytest tests/ -q
git add scripts/config_sync.py scripts/config_sync_propagators.py scripts/config_sync_rejections.py tests/test_settings_key_wiring.py
git commit -m "feat(config-sync): subtract rejected settings keys at consolidate and apply"
```

---

### Task 3: Plugin addressing and plan filtering

**Files:**
- Modify: `scripts/config_sync_rejections.py`
- Modify: `scripts/config_sync_plugins.py` (`plan_convergence`, `scripts/config_sync_plugins.py:256`)
- Modify: `scripts/config_sync.py` (`cmd_plugins_plan` at `:1644`, `cmd_plugins_apply` at `:1668`)
- Test: `tests/test_plugin_rejections.py`

**Interfaces:**
- Consumes: `RejectionTarget`, `NullRejectionPolicy`, `CompositeRejectionPolicy` from Phase 1.
- Produces: `PluginAddressor` with `kind = "plugin"`, `identify(target: str) -> str`, `matches(address: str, target: str) -> bool`; `plan_convergence(context, reader, policy=None) -> MarketplacePlan` where `None` means `NullRejectionPolicy`.

This is the design spec's **third filter point**: `plugins-plan` drops rejected plugin actions before returning, so a plugin you do not want stops appearing in the plan every sync. A `PlannedAction` (`scripts/config_sync_plugins.py:244`) carries `verb`, `target` and `detail`; the plugin id *is* the `target`.

Both `cmd_plugins_plan` and `cmd_plugins_apply` call `plan_convergence`, so injecting the policy into the planner covers both with one change — and keeps the filter out of the two commands, where it would have been duplicated.

`plugins-plan` writes LOCAL state, so it gets the **composite** policy.

- [ ] **Step 1: Write the failing test**

```python
"""A rejected plugin stops being proposed, in the plan and in apply.

The plan is where this belongs: dropping the ACTION means the plugin never gets
installed and never reappears in the next sync's plan, which is the behaviour an
operator who declined it expects.
"""

import config_sync_plugins as plugins
import config_sync_rejections as rejections
from config_sync_plugins import PlannedAction
from config_sync_rejections import (
    CompositeRejectionPolicy,
    LocalRejectionStore,
    NullRejectionPolicy,
    PluginAddressor,
    RejectionRecord,
    rejection_id_of,
)

PLUGIN = "open-memory@open-memory"
REJECTED_AT = "2026-08-03T09:00:00+00:00"


def _policy(tmp_path, scope="local"):
    store = LocalRejectionStore(tmp_path / "local.json")
    store.record(
        RejectionRecord(
            id=rejection_id_of("plugin", PLUGIN),
            kind="plugin",
            address=PLUGIN,
            scope=scope,
            rejected_at=REJECTED_AT,
            machine_id="machine-a",
        )
    )
    return CompositeRejectionPolicy([store])


def test_the_addressor_uses_the_plugin_id_itself():
    addressor = PluginAddressor()
    assert addressor.kind == "plugin"
    assert addressor.identify(PLUGIN) == PLUGIN
    assert addressor.matches(PLUGIN, PLUGIN)
    assert not addressor.matches(PLUGIN, "other@other")


def test_filtering_drops_only_the_rejected_action(tmp_path):
    actions = [
        PlannedAction(verb="install", target=PLUGIN, detail={}),
        PlannedAction(verb="install", target="keep-me@keep-me", detail={}),
    ]
    kept, removed = rejections.filter_plugin_actions(
        actions, _policy(tmp_path), REJECTED_AT
    )
    assert [action.target for action in kept] == ["keep-me@keep-me"]
    assert removed == [PLUGIN]


def test_the_null_policy_keeps_every_action():
    actions = [PlannedAction(verb="install", target=PLUGIN, detail={})]
    kept, removed = rejections.filter_plugin_actions(
        actions, NullRejectionPolicy(), REJECTED_AT
    )
    assert kept == actions
    assert removed == []


def test_an_action_added_later_than_the_rejection_survives(tmp_path):
    actions = [PlannedAction(verb="install", target=PLUGIN, detail={})]
    kept, _removed = rejections.filter_plugin_actions(
        actions, _policy(tmp_path), "2026-08-03T11:00:00+00:00"
    )
    assert [action.target for action in kept] == [PLUGIN]


def test_plan_convergence_without_a_policy_behaves_exactly_as_before(monkeypatch):
    """The default path must be untouched — every existing caller relies on it."""
    seen = {}

    def _fake_plan(context, reader):
        seen["called"] = True
        return plugins.MarketplacePlan(
            actions=[PlannedAction(verb="install", target=PLUGIN, detail={})],
            skipped=[],
        )

    monkeypatch.setattr(plugins, "_plan_actions", _fake_plan, raising=False)
    plan = plugins.plan_convergence(context=None, reader=None)
    assert [action.target for action in plan.actions] == [PLUGIN]
```

If `plan_convergence` has no seam that `_plan_actions` can stand in for, drop `test_plan_convergence_without_a_policy_behaves_exactly_as_before` and instead assert the default-policy path through the real planner with a stub reader, following whatever `tests/test_plugin_convergence.py` already does. Read that file first and match its fixtures rather than inventing new ones — the default path must be covered either way.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_plugin_rejections.py -q`
Expected: FAIL with `ImportError: cannot import name 'PluginAddressor'`

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/config_sync_rejections.py`:

```python
class PluginAddressor:
    """A marketplace plugin, addressed by the id `plugins-plan` already uses as an
    action target. Like a snapshot file key, the id IS the identity."""

    kind = "plugin"

    def identify(self, target: str) -> str:
        return target

    def matches(self, address: str, target: str) -> bool:
        return address == target


def filter_plugin_actions(actions: list, policy, source_timestamp: str) -> tuple:
    """Drop planned plugin actions whose target the operator has rejected.

    Returns `(kept_actions, removed_addresses)`. Dropping the ACTION rather than
    undoing the install is what stops the plugin reappearing in every subsequent
    plan — the thing an operator who declined it is actually asking for.
    """
    addressor = PluginAddressor()
    kept: list = []
    removed: list = []
    for action in actions:
        target = RejectionTarget(
            kind=addressor.kind, address=addressor.identify(action.target)
        )
        if policy.is_rejected(target, source_timestamp):
            removed.append(target.address)
            continue
        kept.append(action)
    return kept, removed
```

In `scripts/config_sync_plugins.py`, give `plan_convergence` an injected policy defaulting to the null object, and filter the actions it is about to return:

```python
def plan_convergence(context, reader, policy=None):
    """...existing docstring, plus:

    `policy` is the rejection ledger, injected. It defaults to a null object so
    every existing caller is unaffected, and so this module never has to branch
    on a None policy. plugins-plan writes LOCAL state, so the caller hands it the
    COMPOSITE policy — both scopes are correct here.
    """
    # Deferred import: config_sync_rejections is a sibling script, not a package.
    import config_sync_rejections as rejections_module

    policy = policy if policy is not None else rejections_module.NullRejectionPolicy()

    # ... existing planning logic, producing `plan` ...

    plan.actions, rejected_targets = rejections_module.filter_plugin_actions(
        plan.actions, policy, ""
    )
    plan.skipped.extend(
        f"{target}: rejected in the config-sync ledger" for target in rejected_targets
    )
    return plan
```

Pass `""` as `source_timestamp` for the same reason as everywhere else on the local side: there is no content provenance to compare against, and the empty string reads as "no fresher intent". Freshness for plugins is decided by `unreject`.

In `scripts/config_sync.py`, build the composite policy at both plugin call sites. `_sync_context(repo_path)` already yields the context those commands use, so reuse `apply_propagators`' composition rather than writing a third one — extract it as a helper beside `network_rejection_policy`:

```python
def local_rejection_policy(context):
    """The composite policy for LOCAL-state writers (plugins-plan, hook wiring).

    Both scopes are correct here, unlike `cmd_consolidate`, which writes shared
    state and gets a network-only policy. Uses the context-injected machine id so
    a test never reaches the operator's real ~/.claude.
    """
    import config_sync_propagators as propagators_module
    import config_sync_rejections as rejections_module

    return rejections_module.CompositeRejectionPolicy(
        [
            rejections_module.LocalRejectionStore(
                context.claude_dir / "config-sync-rejections.json"
            ),
            rejections_module.SharedRejectionStore(
                context.repo_dir, propagators_module._machine_id(context)
            ),
        ]
    )
```

Then in both `cmd_plugins_plan` and `cmd_plugins_apply`, pass it:

```python
    plan = plugins_module.plan_convergence(
        context, reader, policy=local_rejection_policy(context)
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_plugin_rejections.py -q`
Expected: 5 passed

Then: `uv run pytest tests/ -q`

- [ ] **Step 5: Format, lint, commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black scripts/config_sync_rejections.py scripts/config_sync_plugins.py scripts/config_sync.py tests/test_plugin_rejections.py
uv run ruff check --fix scripts/config_sync_rejections.py scripts/config_sync_plugins.py scripts/config_sync.py tests/test_plugin_rejections.py
uv run pytest tests/ -q
git add scripts/config_sync_rejections.py scripts/config_sync_plugins.py scripts/config_sync.py tests/test_plugin_rejections.py
git commit -m "feat(config-sync): drop rejected plugin actions from the convergence plan"
```

---

### Task 4: The three hook identity tiers

**Files:**
- Create: `scripts/config_sync_rejection_hooks.py`
- Test: `tests/test_hook_rejection_tiers.py`

**Interfaces:**
- Consumes: `hook_id_in`, `script_name_of`, `strip_marker`, `HookSite` and `hook_sites` from `scripts/config_sync_hooks.py` (verified: `:112`, `:86`, `:119`, `:172`, `:186`).
- Produces: `HOOK_TIER_MARKER = 1`, `HOOK_TIER_SCRIPT = 2`, `HOOK_TIER_EXACT = 3`; `hook_address_at_tier(site, tier: int) -> str | None`.

This task builds only the **address at a given tier**. Choosing the tier — and the ambiguity rules that drive that choice — is Task 5, kept separate because it is where the design's real subtlety lives and it deserves its own review gate.

Why tiers at all: `script_key_of` (`scripts/config_sync_hooks.py:59`) exists because keying identity on the whole command string was a real defect — changing an interpreter (`python3 X` becoming `${ROOT}/bin/py X`) minted a fresh id, so the previous registration was never matched again and survived forever as a second, eventually-broken copy. A rejection keyed that way would rot the same way.

| Tier | Address | Survives |
|---|---|---|
| 1 | `hooks/<hook_id>` | interpreter change, relocation, matcher edit — anything. Available only when the command carries a `# config-sync:<id>` marker. |
| 2 | `hooks/<event>/<matcher>/<script basename>` | interpreter change and relocation. |
| 3 | `hooks/<event>/<matcher>/#<sha1 of strip_marker(command)>` | nothing — exact match. The floor for commands with no identifiable script, such as opaque shell fragments. |

- [ ] **Step 1: Write the failing test**

```python
"""One address per tier, computed from a hook site.

Tier selection is Task 5's job; this pins only that each tier computes the
address it promises, and that a tier which cannot apply says so with None rather
than inventing something.
"""

from config_sync_hooks import HookSite
from config_sync_rejection_hooks import (
    HOOK_TIER_EXACT,
    HOOK_TIER_MARKER,
    HOOK_TIER_SCRIPT,
    hook_address_at_tier,
)

MARKED = HookSite(
    event="PreToolUse",
    group_index=0,
    hook_index=0,
    matcher="Bash",
    command="/abs/bin/py /abs/scripts/enforce_gates.py  # config-sync:abc123def456",
)
UNMARKED = HookSite(
    event="PreToolUse",
    group_index=0,
    hook_index=1,
    matcher="Bash",
    command="python3 /other/place/enforce_gates.py",
)
OPAQUE = HookSite(
    event="SessionStart",
    group_index=0,
    hook_index=0,
    matcher="",
    command="echo hello && exit 0",
)


def test_tier_1_reads_the_marker():
    assert hook_address_at_tier(MARKED, HOOK_TIER_MARKER) == "hooks/abc123def456"


def test_tier_1_is_unavailable_without_a_marker():
    assert hook_address_at_tier(UNMARKED, HOOK_TIER_MARKER) is None


def test_tier_2_is_event_matcher_and_script_basename():
    assert (
        hook_address_at_tier(UNMARKED, HOOK_TIER_SCRIPT)
        == "hooks/PreToolUse/Bash/enforce_gates.py"
    )


def test_tier_2_ignores_the_interpreter_and_the_directory():
    """The whole point: these two differ only in interpreter and path."""
    assert hook_address_at_tier(MARKED, HOOK_TIER_SCRIPT) == hook_address_at_tier(
        UNMARKED, HOOK_TIER_SCRIPT
    )


def test_tier_2_is_unavailable_for_a_command_with_no_script():
    assert hook_address_at_tier(OPAQUE, HOOK_TIER_SCRIPT) is None


def test_tier_3_hashes_the_marker_stripped_command():
    address = hook_address_at_tier(MARKED, HOOK_TIER_EXACT)
    assert address.startswith("hooks/PreToolUse/Bash/#")
    assert len(address.rsplit("#", 1)[1]) == 12


def test_tier_3_ignores_the_marker_so_marking_a_hook_does_not_move_it():
    unmarked_twin = HookSite(
        event="PreToolUse",
        group_index=0,
        hook_index=0,
        matcher="Bash",
        command="/abs/bin/py /abs/scripts/enforce_gates.py",
    )
    assert hook_address_at_tier(MARKED, HOOK_TIER_EXACT) == hook_address_at_tier(
        unmarked_twin, HOOK_TIER_EXACT
    )


def test_tier_3_distinguishes_two_same_named_scripts_from_different_paths():
    assert hook_address_at_tier(MARKED, HOOK_TIER_EXACT) != hook_address_at_tier(
        UNMARKED, HOOK_TIER_EXACT
    )


def test_tier_3_is_always_available():
    assert hook_address_at_tier(OPAQUE, HOOK_TIER_EXACT) is not None


def test_an_unknown_tier_is_refused_rather_than_guessed():
    import pytest

    with pytest.raises(ValueError):
        hook_address_at_tier(MARKED, 99)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_hook_rejection_tiers.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'config_sync_rejection_hooks'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/config_sync_rejection_hooks.py`:

```python
"""Addressing one hook registration for the rejection ledger.

Its own module, and its own protocol, because it is the only addressor whose
identity must be RESOLVED rather than read. A hook registration is a list element
in settings.json with no natural key, and keying it on the whole command string
is a defect this codebase already carries scar tissue from -- see
`config_sync_hooks.script_key_of`. The easy kinds (settings-key, plugin) must not
inherit this machinery (ISP).

See docs/superpowers/specs/2026-08-03-config-sync-rejection-ledger-design.md §3.1.
"""

from __future__ import annotations

import hashlib

HOOK_TIER_MARKER = 1
HOOK_TIER_SCRIPT = 2
HOOK_TIER_EXACT = 3

HOOK_TIERS = (HOOK_TIER_MARKER, HOOK_TIER_SCRIPT, HOOK_TIER_EXACT)


def hook_address_at_tier(site, tier: int) -> str | None:
    """The address `site` has at `tier`, or None when that tier cannot apply.

    Tier 1 needs a marker; tier 2 needs an identifiable script; tier 3 always
    applies, which is what makes it the floor.
    """
    # Deferred import: config_sync_hooks is a sibling script, not a package.
    import config_sync_hooks as hooks_module

    if tier == HOOK_TIER_MARKER:
        hook_id = hooks_module.hook_id_in(site.command)
        return f"hooks/{hook_id}" if hook_id else None

    if tier == HOOK_TIER_SCRIPT:
        script_name = hooks_module.script_name_of(site.command)
        if not script_name:
            return None
        return f"hooks/{site.event}/{site.matcher}/{script_name}"

    if tier == HOOK_TIER_EXACT:
        # The marker is bookkeeping, not invocation: hashing it would move the
        # address the moment config-sync adopted a previously hand-added hook.
        stripped = hooks_module.strip_marker(site.command)
        digest = hashlib.sha1(stripped.encode("utf-8")).hexdigest()[:12]
        return f"hooks/{site.event}/{site.matcher}/#{digest}"

    raise ValueError(f"unknown hook identity tier {tier!r}; expected one of {HOOK_TIERS}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_hook_rejection_tiers.py -q`
Expected: 10 passed

If `test_tier_2_ignores_the_interpreter_and_the_directory` fails, read what `script_name_of` (`scripts/config_sync_hooks.py:86`) actually returns for each command before changing anything — it reads both the `${TOKEN}` and the localized absolute form, and the test's premise depends on that. Adapt the test's fixtures to the real helper rather than reimplementing the helper.

- [ ] **Step 5: Format, lint, commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black scripts/config_sync_rejection_hooks.py tests/test_hook_rejection_tiers.py
uv run ruff check --fix scripts/config_sync_rejection_hooks.py tests/test_hook_rejection_tiers.py
uv run pytest tests/ -q
git add scripts/config_sync_rejection_hooks.py tests/test_hook_rejection_tiers.py
git commit -m "feat(config-sync): compute hook rejection addresses at three identity tiers"
```

---

### Task 5: Tier selection — ambiguity falls downward

**Files:**
- Modify: `scripts/config_sync_rejection_hooks.py`
- Test: `tests/test_hook_rejection_tiers.py` (append)

**Interfaces:**
- Consumes: `hook_address_at_tier`, `HOOK_TIERS` from Task 4; `hook_sites` from `scripts/config_sync_hooks.py:186`.
- Produces: `AmbiguousHookRejectionError(RuntimeError)`; `HookRegistrationAddressor` with `kind = "hook-registration"`, `identify(site, all_sites) -> tuple[str, int]` returning `(address, tier)`.

**This is the subtle task of the plan.** Three rules, and each has a real motivating case in this repo:

1. **Most stable first.** Try tier 1, then 2, then 3.
2. **Ambiguity falls *downward*, to the more specific tier.** Today this repo has two `enforce_gates.py` registrations under the *same* event and matcher, differing only in full path (`~/.claude/mente-apex/…` vs `~/Projects/mente-apex-memory/…`). Tier 2 is ambiguous there, so resolution falls to tier 3, where the full path distinguishes them — and brittleness is then *correct*, because the operator rejected one specific copy. `hooks-doctor` already reports this as its advisory `duplicate-script` finding.
3. **Never guess between two matches** — inherited verbatim from `registrations_by_script` (`scripts/config_sync_hooks.py:232`), whose docstring says it outright: "better to leave both alone and register nothing than to rewrite the wrong one." If even tier 3 is ambiguous — two byte-identical registrations under one event and matcher — they are indistinguishable, and an exact duplicate is precisely what one wants gone, so **every match is rejected together** rather than refused. That is the one place ambiguity does *not* refuse.

Note `registrations_by_script` itself is **not** reused: it iterates `registered_hooks`, which yields only config-sync's own *marked* registrations, and 2 of the 3 hooks in the motivating case were hand-added and unmarked. This addressor scans `hook_sites` — every entry — and reuses only the pure helpers.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_hook_rejection_tiers.py`:

```python
from config_sync_rejection_hooks import HookRegistrationAddressor

TWIN_A = HookSite(
    event="PreToolUse",
    group_index=0,
    hook_index=0,
    matcher="Bash",
    command="python3 /Users/ai/.claude/mente-apex/enforce_gates.py",
)
TWIN_B = HookSite(
    event="PreToolUse",
    group_index=0,
    hook_index=1,
    matcher="Bash",
    command="python3 /Users/ai/Projects/mente-apex-memory/enforce_gates.py",
)
IDENTICAL_A = HookSite(
    event="Stop", group_index=0, hook_index=0, matcher="", command="run.sh"
)
IDENTICAL_B = HookSite(
    event="Stop", group_index=0, hook_index=1, matcher="", command="run.sh"
)


def test_a_marked_hook_resolves_to_tier_1():
    addressor = HookRegistrationAddressor()
    address, tier = addressor.identify(MARKED, [MARKED, UNMARKED])
    assert tier == HOOK_TIER_MARKER
    assert address == "hooks/abc123def456"


def test_an_unmarked_hook_with_a_unique_script_resolves_to_tier_2():
    addressor = HookRegistrationAddressor()
    address, tier = addressor.identify(UNMARKED, [UNMARKED, OPAQUE])
    assert tier == HOOK_TIER_SCRIPT
    assert address == "hooks/PreToolUse/Bash/enforce_gates.py"


def test_two_same_named_scripts_under_one_event_and_matcher_fall_to_tier_3():
    """The live enforce_gates.py case: tier 2 is ambiguous, tier 3 is not."""
    addressor = HookRegistrationAddressor()
    address_a, tier_a = addressor.identify(TWIN_A, [TWIN_A, TWIN_B])
    address_b, tier_b = addressor.identify(TWIN_B, [TWIN_A, TWIN_B])
    assert tier_a == tier_b == HOOK_TIER_EXACT
    assert address_a != address_b


def test_the_same_script_name_under_a_different_matcher_is_not_ambiguous():
    """Tier 2 is scoped BY event and matcher — a same-named script elsewhere is
    a different registration, not a collision."""
    elsewhere = HookSite(
        event="PreToolUse",
        group_index=1,
        hook_index=0,
        matcher="Write",
        command="python3 /somewhere/enforce_gates.py",
    )
    addressor = HookRegistrationAddressor()
    _address, tier = addressor.identify(UNMARKED, [UNMARKED, elsewhere])
    assert tier == HOOK_TIER_SCRIPT


def test_a_marked_hook_is_unaffected_by_a_tier_2_collision():
    """Tier 1 is checked first, so a marker wins even when the basename clashes."""
    addressor = HookRegistrationAddressor()
    _address, tier = addressor.identify(MARKED, [MARKED, TWIN_A, TWIN_B])
    assert tier == HOOK_TIER_MARKER


def test_two_byte_identical_registrations_share_one_address_rather_than_refusing():
    """Indistinguishable by construction, and an exact duplicate is precisely what
    one wants gone — so they are rejected together rather than refused."""
    addressor = HookRegistrationAddressor()
    address_a, tier_a = addressor.identify(IDENTICAL_A, [IDENTICAL_A, IDENTICAL_B])
    address_b, tier_b = addressor.identify(IDENTICAL_B, [IDENTICAL_A, IDENTICAL_B])
    assert tier_a == tier_b == HOOK_TIER_EXACT
    assert address_a == address_b


def test_an_opaque_command_resolves_to_tier_3():
    addressor = HookRegistrationAddressor()
    _address, tier = addressor.identify(OPAQUE, [OPAQUE])
    assert tier == HOOK_TIER_EXACT


def test_identify_refuses_a_site_that_is_not_among_the_sites_given():
    import pytest

    addressor = HookRegistrationAddressor()
    with pytest.raises(ValueError):
        addressor.identify(OPAQUE, [MARKED, UNMARKED])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_hook_rejection_tiers.py -q`
Expected: FAIL with `ImportError: cannot import name 'HookRegistrationAddressor'`

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/config_sync_rejection_hooks.py`:

```python
class AmbiguousHookRejectionError(RuntimeError):
    """A hook registration cannot be told apart from another at any usable tier.

    Named rather than swallowed so the operator learns which registrations
    collided, instead of a rejection silently attaching to the wrong one.
    """


class HookRegistrationAddressor:
    """One hook registration, addressed at the most stable tier that is unambiguous.

    Resolution walks the tiers most-stable-first and falls DOWNWARD on ambiguity,
    to the more specific tier. That is not a compromise: when two registrations
    share an event, a matcher and a script basename, the operator rejected one
    specific copy, so brittleness at tier 3 is the correct behaviour.

    `registrations_by_script` is deliberately NOT reused. It iterates
    `registered_hooks`, which yields only config-sync's own marked registrations,
    and hand-added unmarked hooks are exactly the ones that need addressing. This
    scans every site and reuses only the pure helpers.
    """

    kind = "hook-registration"

    def identify(self, site, all_sites) -> tuple:
        """The `(address, tier)` for `site`, resolved against `all_sites`.

        `all_sites` is every entry in the settings hooks block, from
        `config_sync_hooks.hook_sites`. It is a parameter rather than something
        this class reads, so the addressor stays pure and testable.
        """
        sites = list(all_sites)
        if not any(_same_site(site, candidate) for candidate in sites):
            raise ValueError(
                "site is not among the sites given; identify resolves ambiguity "
                "against the whole hooks block and cannot do so for a stranger"
            )

        for tier in HOOK_TIERS:
            address = hook_address_at_tier(site, tier)
            if address is None:
                continue
            sharing = [
                candidate
                for candidate in sites
                if hook_address_at_tier(candidate, tier) == address
            ]
            if len(sharing) == 1:
                return address, tier
            if tier == HOOK_TIER_EXACT:
                # Byte-identical under one event and matcher: indistinguishable,
                # and an exact duplicate is precisely what one wants gone. They
                # share the address and are rejected together.
                return address, tier
            # Ambiguous at this tier — fall downward to the more specific one.

        raise AmbiguousHookRejectionError(
            f"cannot address the hook at {site.event}/{site.matcher!r} "
            f"(index {site.group_index}/{site.hook_index}) at any tier"
        )


def _same_site(left, right) -> bool:
    """Identity by position in the hooks block, not by command — two entries can
    carry the same command and still be different registrations."""
    return (
        left.event == right.event
        and left.group_index == right.group_index
        and left.hook_index == right.hook_index
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_hook_rejection_tiers.py -q`
Expected: 18 passed (10 from Task 4, 8 here)

- [ ] **Step 5: Format, lint, commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black scripts/config_sync_rejection_hooks.py tests/test_hook_rejection_tiers.py
uv run ruff check --fix scripts/config_sync_rejection_hooks.py tests/test_hook_rejection_tiers.py
uv run pytest tests/ -q
git add scripts/config_sync_rejection_hooks.py tests/test_hook_rejection_tiers.py
git commit -m "feat(config-sync): resolve hook identity, falling downward on ambiguity"
```

---

### Task 6: Matching a stored address back to a hook

**Files:**
- Modify: `scripts/config_sync_rejection_hooks.py`
- Test: `tests/test_hook_rejection_tiers.py` (append)

**Interfaces:**
- Consumes: `hook_address_at_tier`, `HookRegistrationAddressor` from Tasks 4 and 5.
- Produces: `HookRegistrationAddressor.matches(address: str, tier: int, site) -> bool`.

**Why `matches` takes the tier.** This is what `RejectionRecord.tier` — the field Phase 1 defined and left unused — exists for. At match time there is no ambiguity resolution: the record already says which tier produced its address, so matching recomputes **only that tier** for the candidate. That is both cheaper and more correct, because the candidate being matched is often a *declared* hook that is not in the settings block at all, so there is no set to resolve ambiguity against.

This is why `HookRegistrationAddressor` does **not** satisfy the `UnitAddressor` shape the snapshot addressors use (`identify(unit)`, `matches(address, unit)`). Forcing it to would mean either hiding the tier in the address string or resolving ambiguity at match time against a set that does not exist. Two small, client-specific protocols beat one that fits neither (ISP).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_hook_rejection_tiers.py`:

```python
def test_matches_recomputes_only_the_recorded_tier():
    addressor = HookRegistrationAddressor()
    address, tier = addressor.identify(UNMARKED, [UNMARKED])
    relocated = HookSite(
        event="PreToolUse",
        group_index=7,
        hook_index=3,
        matcher="Bash",
        command="/new/uv/bin/python /completely/different/enforce_gates.py",
    )
    assert addressor.matches(address, tier, relocated)


def test_a_tier_2_address_does_not_match_a_different_script():
    addressor = HookRegistrationAddressor()
    address, tier = addressor.identify(UNMARKED, [UNMARKED])
    other = HookSite(
        event="PreToolUse",
        group_index=0,
        hook_index=0,
        matcher="Bash",
        command="python3 /somewhere/other_script.py",
    )
    assert not addressor.matches(address, tier, other)


def test_a_tier_2_address_does_not_match_under_a_different_matcher():
    addressor = HookRegistrationAddressor()
    address, tier = addressor.identify(UNMARKED, [UNMARKED])
    elsewhere = HookSite(
        event="PreToolUse",
        group_index=0,
        hook_index=0,
        matcher="Write",
        command="python3 /somewhere/enforce_gates.py",
    )
    assert not addressor.matches(address, tier, elsewhere)


def test_a_tier_3_address_stops_matching_once_the_command_changes():
    """Deliberate: tier 3 is the exact-match floor. The operator rejected one
    specific command, so a changed command is a different registration."""
    addressor = HookRegistrationAddressor()
    address, tier = addressor.identify(OPAQUE, [OPAQUE])
    changed = HookSite(
        event="SessionStart",
        group_index=0,
        hook_index=0,
        matcher="",
        command="echo hello && exit 1",
    )
    assert addressor.matches(address, tier, OPAQUE)
    assert not addressor.matches(address, tier, changed)


def test_a_tier_1_address_survives_everything_but_losing_the_marker():
    addressor = HookRegistrationAddressor()
    address, tier = addressor.identify(MARKED, [MARKED])
    moved = HookSite(
        event="Stop",
        group_index=4,
        hook_index=1,
        matcher="Other",
        command="/anything/at/all.sh  # config-sync:abc123def456",
    )
    unmarked_now = HookSite(
        event="PreToolUse",
        group_index=0,
        hook_index=0,
        matcher="Bash",
        command="/abs/bin/py /abs/scripts/enforce_gates.py",
    )
    assert addressor.matches(address, tier, moved)
    assert not addressor.matches(address, tier, unmarked_now)


def test_matching_a_tier_that_cannot_apply_is_false_not_an_error():
    addressor = HookRegistrationAddressor()
    address, tier = addressor.identify(UNMARKED, [UNMARKED])
    assert not addressor.matches(address, tier, OPAQUE)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_hook_rejection_tiers.py -q`
Expected: FAIL with `AttributeError: 'HookRegistrationAddressor' object has no attribute 'matches'`

- [ ] **Step 3: Write minimal implementation**

Append the method to `HookRegistrationAddressor` in `scripts/config_sync_rejection_hooks.py`:

```python
    def matches(self, address: str, tier: int, site) -> bool:
        """Does `site` carry `address` at `tier`?

        Only the recorded tier is recomputed — no resolution, no ambiguity pass.
        `RejectionRecord.tier` exists precisely so this stays a single cheap
        comparison, and so a candidate that is not in the settings block at all
        (a hook the wiring is merely PROPOSING) can still be matched.

        A tier that cannot apply to `site` is a non-match, not an error: asking
        whether an opaque command carries a script-tier address is a fair
        question with the answer "no".
        """
        computed = hook_address_at_tier(site, tier)
        return computed is not None and computed == address
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_hook_rejection_tiers.py -q`
Expected: 24 passed

- [ ] **Step 5: Format, lint, commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black scripts/config_sync_rejection_hooks.py tests/test_hook_rejection_tiers.py
uv run ruff check --fix scripts/config_sync_rejection_hooks.py tests/test_hook_rejection_tiers.py
uv run pytest tests/ -q
git add scripts/config_sync_rejection_hooks.py tests/test_hook_rejection_tiers.py
git commit -m "feat(config-sync): match a stored hook address by its recorded tier"
```

---

### Task 7: A rejected hook is never wired

**Files:**
- Modify: `scripts/config_sync_hooks.py` (`plan_hook_wiring`, `scripts/config_sync_hooks.py:367`)
- Modify: `scripts/config_sync.py` (`cmd_hooks_plan`, `cmd_hooks_apply`)
- Test: `tests/test_hook_rejection_wiring.py`

**Interfaces:**
- Consumes: `HookRegistrationAddressor` from Tasks 5-6; `local_rejection_policy` from Task 3.
- Produces: `plan_hook_wiring(declarations, settings, localize=identity, checker=None, policy=None) -> HookPlan` — `None` means `NullRejectionPolicy`; rejected declarations appear in `plan.skipped`.

The filter point is the **plan**, exactly parallel to `plugins-plan`: a rejected declaration is never registered, so it stops being proposed on every sync.

**A rejection withholds; it does not delete.** A registration already in `settings.json` stays there — config-sync only ever edits its own marked entries, and removing a hook is `hooks-prune`'s job. The two compose: `reject` stops it coming back, `hooks-prune` takes out what is already there. Document that rather than making `plan_hook_wiring` delete, which would give it a second reason to change.

Matching a *declaration* against a rejection needs a `HookSite`-shaped value. A declaration has an event, a matcher and a command but no position in the block, so build a pseudo-site with sentinel indices — and use the **localized** command, because `plan_hook_wiring` already works in localized space (its docstring at `:380-387` explains why planning in portable space is not an option).

- [ ] **Step 1: Write the failing test**

```python
"""A rejected hook is never wired, and an already-wired one is left alone.

Rejection withholds; it never deletes. `hooks-prune` removes what is already
registered — the two compose rather than compete.
"""

from config_sync_hooks import DeclaredHook, plan_hook_wiring
from config_sync_rejection_hooks import HookRegistrationAddressor
from config_sync_rejections import (
    CompositeRejectionPolicy,
    LocalRejectionStore,
    NullRejectionPolicy,
    RejectionRecord,
    rejection_id_of,
)

REJECTED_AT = "2026-08-03T09:00:00+00:00"

DECLARED = DeclaredHook(
    hook_id="aaaaaaaaaaaa",
    event="PreToolUse",
    matcher="Bash",
    command="${ROOT}/scripts/unwanted.py",
    timeout=None,
)
KEPT = DeclaredHook(
    hook_id="bbbbbbbbbbbb",
    event="PreToolUse",
    matcher="Bash",
    command="${ROOT}/scripts/wanted.py",
    timeout=None,
)


def _localize(command):
    return command.replace("${ROOT}", "/abs/root")


def _policy(tmp_path, address, tier):
    store = LocalRejectionStore(tmp_path / "local.json")
    store.record(
        RejectionRecord(
            id=rejection_id_of("hook-registration", address),
            kind="hook-registration",
            address=address,
            scope="local",
            rejected_at=REJECTED_AT,
            machine_id="machine-a",
            tier=str(tier),
        )
    )
    return CompositeRejectionPolicy([store])


def _address_of(declared):
    """The address the operator would have recorded, seen from settings."""
    from config_sync_hooks import HookSite

    site = HookSite(
        event=declared.event,
        group_index=0,
        hook_index=0,
        matcher=declared.matcher,
        command=_localize(declared.command),
    )
    return HookRegistrationAddressor().identify(site, [site])


def test_without_a_policy_every_declaration_is_planned():
    plan = plan_hook_wiring([DECLARED, KEPT], {}, localize=_localize)
    assert {action.hook_id for action in plan.actions} == {"aaaaaaaaaaaa", "bbbbbbbbbbbb"}


def test_a_rejected_declaration_is_not_registered(tmp_path):
    address, tier = _address_of(DECLARED)
    plan = plan_hook_wiring(
        [DECLARED, KEPT], {}, localize=_localize, policy=_policy(tmp_path, address, tier)
    )
    assert {action.hook_id for action in plan.actions} == {"bbbbbbbbbbbb"}


def test_the_rejected_declaration_is_reported_as_skipped(tmp_path):
    address, tier = _address_of(DECLARED)
    plan = plan_hook_wiring(
        [DECLARED, KEPT], {}, localize=_localize, policy=_policy(tmp_path, address, tier)
    )
    assert any("unwanted.py" in str(entry) or "rejected" in str(entry) for entry in plan.skipped)


def test_the_null_policy_plans_exactly_what_it_did_before():
    with_null = plan_hook_wiring(
        [DECLARED, KEPT], {}, localize=_localize, policy=NullRejectionPolicy()
    )
    without = plan_hook_wiring([DECLARED, KEPT], {}, localize=_localize)
    assert [action.hook_id for action in with_null.actions] == [
        action.hook_id for action in without.actions
    ]


def test_an_already_registered_rejected_hook_is_not_deleted(tmp_path):
    """Rejection withholds; removal is hooks-prune's job. The settings block the
    planner was handed must come back untouched."""
    address, tier = _address_of(DECLARED)
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "/abs/root/scripts/unwanted.py"}],
                }
            ]
        }
    }
    before = dict(settings)
    plan_hook_wiring(
        [DECLARED], settings, localize=_localize, policy=_policy(tmp_path, address, tier)
    )
    assert settings == before
```

Read `tests/test_hook_wiring.py` before writing this file and match its fixture style — `plan_hook_wiring` is existing, tested code and its call shape must not be guessed at.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_hook_rejection_wiring.py -q`
Expected: FAIL with `TypeError: plan_hook_wiring() got an unexpected keyword argument 'policy'`

- [ ] **Step 3: Write minimal implementation**

In `scripts/config_sync_hooks.py`, extend `plan_hook_wiring`'s signature and drop rejected declarations before the existing planning logic runs:

```python
def plan_hook_wiring(
    declarations: list[DeclaredHook],
    settings: dict,
    localize=identity,
    checker: CommandChecker | None = None,
    policy=None,
) -> HookPlan:
    """...existing docstring, plus:

    `policy` is the rejection ledger, injected and defaulted to a null object so
    every existing caller is unaffected. A rejected declaration is never
    registered — that is what stops it being proposed on every sync. It is NOT
    unregistered if already present: config-sync only edits its own marked
    entries, and removing a registration is `hooks-prune`'s job. The two compose.
    """
    # Deferred imports: siblings, not a package.
    import config_sync_rejection_hooks as rejection_hooks_module
    import config_sync_rejections as rejections_module

    policy = policy if policy is not None else rejections_module.NullRejectionPolicy()

    plan = HookPlan()
    declarations = list(declarations)

    addressor = rejection_hooks_module.HookRegistrationAddressor()
    kept_declarations = []
    for declaration in declarations:
        # A declaration has no position in the block, so its sentinel indices say
        # "proposed, not present". Localized because this planner works in
        # localized space -- see the note on `localize` above.
        proposed = HookSite(
            event=declaration.event,
            group_index=-1,
            hook_index=-1,
            matcher=declaration.matcher,
            command=localize(declaration.command),
        )
        rejected_record = _matching_hook_rejection(policy, addressor, proposed)
        if rejected_record is not None:
            plan.skipped.append(
                f"{declaration.hook_id}: rejected in the config-sync ledger "
                f"({rejected_record.address})"
            )
            continue
        kept_declarations.append(declaration)
    declarations = kept_declarations

    checker = checker or AssumeRunnable()

    # ... existing planning logic, unchanged, from the collision guard onward ...
```

Add the lookup helper beside it. It lives here rather than in the addressor because it is the only place that needs to walk *records* — the addressor stays pure:

```python
def _matching_hook_rejection(policy, addressor, site):
    """The first active hook-registration rejection whose address matches `site`
    at its own recorded tier, or None.

    Walks records rather than calling `policy.is_rejected`, because a hook
    address alone is not enough to ask that question -- the tier that produced it
    is part of the identity, and only the record knows it.
    """
    import config_sync_rejections as rejections_module

    for record in policy.all():
        if record.kind != "hook-registration" or record.revives is not None:
            continue
        try:
            tier = int(record.tier)
        except (TypeError, ValueError):
            continue
        if not addressor.matches(record.address, tier, site):
            continue
        target = rejections_module.RejectionTarget(
            kind=record.kind, address=record.address
        )
        if policy.is_rejected(target, ""):
            return record
    return None
```

In `scripts/config_sync.py`, pass the composite policy from both hook commands. `cmd_hooks_plan` and `cmd_hooks_apply` take no repo argument, so build the context the way they already do and reuse `local_rejection_policy` from Task 3 — read those two commands first and match how they obtain their context rather than inventing one.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_hook_rejection_wiring.py -q`
Expected: 5 passed

Then: `uv run pytest tests/ -q` — `plan_hook_wiring` has substantial existing coverage (`tests/test_hook_wiring.py`, `tests/test_hooks_cli.py`, `tests/test_hook_path_portability.py`) and none of it may regress.

- [ ] **Step 5: Format, lint, commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black scripts/config_sync_hooks.py scripts/config_sync.py tests/test_hook_rejection_wiring.py
uv run ruff check --fix scripts/config_sync_hooks.py scripts/config_sync.py tests/test_hook_rejection_wiring.py
uv run pytest tests/ -q
git add scripts/config_sync_hooks.py scripts/config_sync.py tests/test_hook_rejection_wiring.py
git commit -m "feat(config-sync): never wire a rejected hook registration"
```

---

### Task 8: The command surface for the three new kinds

**Files:**
- Modify: `scripts/config_sync.py` (`_resolve_rejection_address`, `cmd_reject`)
- Test: `tests/test_rejection_cli_phase2.py`

**Interfaces:**
- Consumes: `SettingsKeyAddressor`, `PluginAddressor` from Tasks 1 and 3; `HookRegistrationAddressor` from Task 5.
- Produces: `_resolve_rejection_address(repo_dir, kind, subject, section_heading, occurrence, key_path=None, event=None, matcher=None) -> tuple[str, str]` returning `(address, tier)` where `tier` is `""` for every kind but `hook-registration`. `cmd_reject` gains `--key`, `--event` and `--matcher`, and records `tier`.

Phase 1's `_resolve_rejection_address` returns a bare address and raises `ValueError` for anything it cannot address — that `ValueError` **is** the seam this task extends. Its return type widens to a 2-tuple so the hook tier can travel with the address; update the two `snapshot-*` branches to return `(address, "")`.

Each kind resolves against real state and **errors when nothing matches**, exactly as Phase 1 does for snapshot kinds, so a typo cannot sit in the ledger forever doing nothing:

| Kind | Subject | Extra options | Resolved against |
|---|---|---|---|
| `settings-key` | ignored | `--key a --key b …` (repeatable, in order) | the `settings.json` blob in the consolidated snapshot |
| `plugin` | the plugin id | none | `enabledPlugins` in that same blob |
| `hook-registration` | the script basename, or `#<sha1>` | `--event`, `--matcher` | the live `settings.json` hooks block |

`hook-registration` addresses the **live** settings, not the snapshot: the operator is rejecting a registration they can see on this machine, and the tier resolution needs the whole local hooks block to detect ambiguity.

`--key` is repeatable because a key path is a sequence, and joining on a delimiter would reintroduce exactly the ambiguity `settings_key_address` avoids.

- [ ] **Step 1: Write the failing test**

```python
"""Rejecting a settings key, a plugin, and one hook registration from the CLI."""

import json

import pytest

import config_sync


@pytest.fixture(autouse=True)
def _isolated_claude_home(claude_home):
    """Never let a test read or write the operator's real ~/.claude.

    `config_sync.CLAUDE_DIR` is a module-level global computed at import time, so
    monkeypatching `pathlib.Path.home` does not reach it — this fixture does.
    """
    return claude_home


SETTINGS = {
    "permissions": {"defaultMode": "acceptEdits"},
    "enabledPlugins": {"open-memory@open-memory": True},
    "model": "opus",
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [
                    {"type": "command", "command": "python3 /abs/scripts/enforce_gates.py"}
                ],
            }
        ]
    },
}

TWIN_SETTINGS = {
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [
                    {"type": "command", "command": "python3 /one/place/enforce_gates.py"},
                    {"type": "command", "command": "python3 /other/place/enforce_gates.py"},
                ],
            }
        ]
    }
}


def _repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "consolidated").mkdir(parents=True)
    (repo / "consolidated" / "snapshot.json").write_text(
        json.dumps({"files": {"settings.json": json.dumps(SETTINGS)}}),
        encoding="utf-8",
    )
    return repo


def _live_settings(claude_home):
    (claude_home / "settings.json").write_text(json.dumps(SETTINGS), encoding="utf-8")


def test_rejecting_a_settings_key_records_the_key_path(tmp_path, capsys):
    repo = _repo(tmp_path)
    config_sync.cmd_reject(
        str(repo), "settings-key", "-", "--key", "permissions", "--key", "defaultMode"
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "settings-key"
    assert json.loads(payload["address"]) == ["permissions", "defaultMode"]


def test_a_settings_key_that_is_absent_is_refused(tmp_path):
    repo = _repo(tmp_path)
    with pytest.raises(config_sync.UnknownRejectionTargetError):
        config_sync.cmd_reject(str(repo), "settings-key", "-", "--key", "notThere")


def test_rejecting_a_plugin_records_its_id(tmp_path, capsys):
    repo = _repo(tmp_path)
    config_sync.cmd_reject(str(repo), "plugin", "open-memory@open-memory")
    assert json.loads(capsys.readouterr().out)["address"] == "open-memory@open-memory"


def test_a_plugin_that_is_not_enabled_anywhere_is_refused(tmp_path):
    repo = _repo(tmp_path)
    with pytest.raises(config_sync.UnknownRejectionTargetError):
        config_sync.cmd_reject(str(repo), "plugin", "never-heard-of@it")


def test_rejecting_a_hook_records_its_address_and_tier(tmp_path, capsys, claude_home):
    repo = _repo(tmp_path)
    _live_settings(claude_home)
    config_sync.cmd_reject(
        str(repo),
        "hook-registration",
        "enforce_gates.py",
        "--event",
        "PreToolUse",
        "--matcher",
        "Bash",
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["address"] == "hooks/PreToolUse/Bash/enforce_gates.py"
    assert payload["tier"] == "2"


def test_a_hook_matching_nothing_is_refused(tmp_path, claude_home):
    repo = _repo(tmp_path)
    _live_settings(claude_home)
    with pytest.raises(config_sync.UnknownRejectionTargetError):
        config_sync.cmd_reject(
            str(repo), "hook-registration", "nope.py", "--event", "PreToolUse", "--matcher", "Bash"
        )


def test_a_hook_rejection_without_an_event_is_refused(tmp_path, claude_home):
    repo = _repo(tmp_path)
    _live_settings(claude_home)
    with pytest.raises(ValueError):
        config_sync.cmd_reject(str(repo), "hook-registration", "enforce_gates.py")


def test_the_new_options_are_in_the_known_vocabulary(tmp_path):
    """Phase 1 made an unrecognised flag fail closed — these must be recognised."""
    repo = _repo(tmp_path)
    config_sync.cmd_reject(str(repo), "settings-key", "-", "--key", "model")


def test_a_mistyped_new_option_is_still_refused(tmp_path):
    repo = _repo(tmp_path)
    with pytest.raises(ValueError):
        config_sync.cmd_reject(str(repo), "settings-key", "-", "--kye", "model")


def test_a_script_name_matching_two_registrations_is_refused(tmp_path, claude_home):
    """Never guess between two matches — the rule `registrations_by_script` states
    outright. Both are addressable at tier 3, but the CLI cannot know which copy
    the operator meant, and rejecting the wrong one silently is worse."""
    repo = _repo(tmp_path)
    (claude_home / "settings.json").write_text(json.dumps(TWIN_SETTINGS), encoding="utf-8")
    with pytest.raises(config_sync.UnknownRejectionTargetError) as refusal:
        config_sync.cmd_reject(
            str(repo),
            "hook-registration",
            "enforce_gates.py",
            "--event",
            "PreToolUse",
            "--matcher",
            "Bash",
        )
    assert "hooks-doctor" in str(refusal.value)


def test_an_exact_hash_subject_addresses_one_of_two_twins(tmp_path, capsys, claude_home):
    """The discriminator the refusal points at: take the `#<hash>` suffix and use
    it as the subject. Resolution then lands on tier 3, as it must."""
    from config_sync_hooks import hook_sites
    from config_sync_rejection_hooks import HOOK_TIER_EXACT, hook_address_at_tier

    repo = _repo(tmp_path)
    (claude_home / "settings.json").write_text(json.dumps(TWIN_SETTINGS), encoding="utf-8")
    first_site = hook_sites(TWIN_SETTINGS)[0]
    suffix = hook_address_at_tier(first_site, HOOK_TIER_EXACT).rsplit("/", 1)[1]

    config_sync.cmd_reject(
        str(repo), "hook-registration", suffix, "--event", "PreToolUse", "--matcher", "Bash"
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["tier"] == "3"
    assert payload["address"].endswith(suffix)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rejection_cli_phase2.py -q`
Expected: FAIL — `ValueError: kind 'settings-key' is not addressable in phase 1`

- [ ] **Step 3: Write minimal implementation**

In `scripts/config_sync.py`, widen `_resolve_rejection_address` to return `(address, tier)` and teach it the three kinds. Update its two existing `snapshot-*` returns to `(address, "")` and the single `cmd_reject` call site to unpack both:

```python
def _resolve_rejection_address(
    repo_dir,
    kind,
    subject,
    section_heading,
    occurrence,
    key_path=None,
    event=None,
    matcher=None,
):
    """The `(address, tier)` for `subject`, proven to exist.

    `tier` is empty for every kind but `hook-registration`, which is the only one
    whose identity is resolved rather than read. Every kind is checked against
    real state and refuses when nothing matches, so a typo cannot sit in the
    ledger forever suppressing nothing.
    """
    import config_sync_merge as merge
    import config_sync_rejections as rejections_module

    files = _consolidated_files(repo_dir)

    # ... existing snapshot-file / snapshot-section branches, each returning
    #     (address, "") instead of a bare address ...

    if kind == "settings-key":
        settings = _snapshot_settings(files)
        node = settings
        for key in key_path or ():
            if not isinstance(node, dict) or key not in node:
                raise UnknownRejectionTargetError(
                    f"no settings key {list(key_path)!r}; "
                    f"{key!r} is not present under {sorted(node) if isinstance(node, dict) else node!r}"
                )
            node = node[key]
        if not key_path:
            raise ValueError("settings-key needs at least one --key")
        return rejections_module.settings_key_address(tuple(key_path)), ""

    if kind == "plugin":
        enabled = _snapshot_settings(files).get("enabledPlugins", {})
        if subject not in enabled:
            raise UnknownRejectionTargetError(
                f"no enabled plugin {subject!r}; known: {sorted(enabled)}"
            )
        return rejections_module.PluginAddressor().identify(subject), ""

    if kind == "hook-registration":
        return _resolve_hook_rejection_address(subject, event, matcher)

    raise ValueError(f"kind {kind!r} is not addressable")


def _snapshot_settings(files) -> dict:
    """The parsed `settings.json` carried inside a snapshot `files` mapping.

    It travels as a JSON *string* there, which is why it needs unwrapping before
    a key path can be checked against it.
    """
    blob = files.get("settings.json")
    if not isinstance(blob, str):
        return {}
    try:
        parsed = json.loads(blob)
    except (json.JSONDecodeError, ValueError) as exc:
        raise UnknownRejectionTargetError(
            f"the consolidated settings.json does not parse ({exc}); "
            "run clean-settings before rejecting a key"
        ) from exc
    return parsed if isinstance(parsed, dict) else {}


def _resolve_hook_rejection_address(subject, event, matcher):
    """Address one registration in the LIVE settings hooks block.

    The live file, not the snapshot: the operator is rejecting a registration
    they can see on this machine, and tier resolution needs the whole local block
    to detect ambiguity.
    """
    import config_sync_hooks as hooks_module
    import config_sync_rejection_hooks as rejection_hooks_module

    if event is None or matcher is None:
        raise ValueError(
            "hook-registration needs --event and --matcher; a script basename is "
            "only unique within one event and matcher"
        )

    settings_path = CLAUDE_DIR / "settings.json"
    settings = json.loads(_read(settings_path)) if settings_path.exists() else {}
    sites = hooks_module.hook_sites(settings)
    addressor = rejection_hooks_module.HookRegistrationAddressor()

    scoped = [
        site for site in sites if site.event == event and site.matcher == matcher
    ]
    chosen = [
        site
        for site in scoped
        if hooks_module.script_name_of(site.command) == subject
        or (subject.startswith("#") and rejection_hooks_module.hook_address_at_tier(
            site, rejection_hooks_module.HOOK_TIER_EXACT
        ).endswith(subject))
    ]
    if not chosen:
        raise UnknownRejectionTargetError(
            f"no hook under {event}/{matcher!r} matching {subject!r}; "
            f"found: {[hooks_module.script_name_of(site.command) for site in scoped]}"
        )
    if len(chosen) > 1:
        # Never guess between two matches -- the same rule `registrations_by_script`
        # states outright. `identify` would resolve these to distinct tier-3
        # addresses, but it cannot know WHICH one the operator meant, and silently
        # rejecting the wrong copy is worse than refusing. Point them at the
        # discriminator instead.
        raise UnknownRejectionTargetError(
            f"{subject!r} matches {len(chosen)} registrations under "
            f"{event}/{matcher!r}: "
            f"{[site.command for site in chosen]}. "
            f"Reject one by its exact-match address instead — take the `#<hash>` "
            f"suffix from `hooks-doctor` and pass it as the subject."
        )
    address, tier = addressor.identify(chosen[0], sites)
    return address, str(tier)
```

In `cmd_reject`: add `--key`, `--event` and `--matcher` to `KNOWN_REJECT_OPTIONS`; collect `--key` as a repeatable list (the existing `_parse_reject_options` returns a dict, so give `--key` an accumulating list rather than last-wins); unpack the 2-tuple; and put `tier` on the record:

```python
    address, tier = _resolve_rejection_address(
        repo_path, kind, subject, section_heading, occurrence,
        key_path=key_path, event=event, matcher=matcher,
    )
    record = rejections_module.RejectionRecord(
        id=rejections_module.rejection_id_of(kind, address),
        kind=kind,
        address=address,
        scope=scope,
        rejected_at=datetime.now(UTC).isoformat(),
        machine_id=_machine_id(),
        reason=reason,
        tier=tier,
    )
```

Keep the mass-rejection guard's `kind == "snapshot-section"` condition exactly as it is — it does not apply to the new kinds.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_rejection_cli_phase2.py -q`
Expected: 11 passed

Then: `uv run pytest tests/ -q` — `tests/test_rejection_cli.py` covers the Phase 1 surface and must not regress.

- [ ] **Step 5: Format, lint, commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black scripts/config_sync.py tests/test_rejection_cli_phase2.py
uv run ruff check --fix scripts/config_sync.py tests/test_rejection_cli_phase2.py
uv run pytest tests/ -q
git add scripts/config_sync.py tests/test_rejection_cli_phase2.py
git commit -m "feat(config-sync): address settings keys, plugins and hook registrations from the CLI"
```

---

### Task 9: Guard a whole-file rejection of a synced config file

**Files:**
- Modify: `scripts/config_sync.py` (`cmd_reject`)
- Test: `tests/test_rejection_cli_phase2.py` (append)

**Interfaces:**
- Consumes: `MassRejectionRefusedError` and `SNAPSHOT_FILES` (`scripts/config_sync.py:89`).
- Produces: no new names. `cmd_reject` refuses `snapshot-file` rejection of a `SNAPSHOT_FILES` member without `--force`.

Phase 1's guard covers `snapshot-section` only. But `reject <repo> snapshot-file settings.json` already works today and would silently stop the entire settings sync — a much larger blast radius than the section case the guard was built for, and now a foreseeable mistake because Task 8 teaches operators to think about `settings.json` as a rejectable thing.

`--force` says they meant it, mirroring the existing guard exactly.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_rejection_cli_phase2.py`:

```python
def test_rejecting_a_whole_synced_config_file_is_refused(tmp_path):
    """settings.json, CLAUDE.md and keybindings.json are the files the whole sync
    exists to carry — rejecting one wholesale is almost never what was meant."""
    repo = tmp_path / "repo3"
    (repo / "consolidated").mkdir(parents=True)
    (repo / "consolidated" / "snapshot.json").write_text(
        json.dumps({"files": {"settings.json": json.dumps(SETTINGS)}}), encoding="utf-8"
    )
    with pytest.raises(config_sync.MassRejectionRefusedError):
        config_sync.cmd_reject(str(repo), "snapshot-file", "settings.json")


def test_force_overrides_the_synced_config_file_guard(tmp_path, capsys):
    repo = tmp_path / "repo4"
    (repo / "consolidated").mkdir(parents=True)
    (repo / "consolidated" / "snapshot.json").write_text(
        json.dumps({"files": {"settings.json": json.dumps(SETTINGS)}}), encoding="utf-8"
    )
    config_sync.cmd_reject(str(repo), "snapshot-file", "settings.json", "--force")
    assert json.loads(capsys.readouterr().out)["address"] == "settings.json"


def test_rejecting_an_ordinary_file_is_not_guarded(tmp_path, capsys):
    repo = tmp_path / "repo5"
    (repo / "consolidated").mkdir(parents=True)
    (repo / "consolidated" / "snapshot.json").write_text(
        json.dumps({"files": {"rules/a.md": "hi"}}), encoding="utf-8"
    )
    config_sync.cmd_reject(str(repo), "snapshot-file", "rules/a.md")
    assert json.loads(capsys.readouterr().out)["address"] == "rules/a.md"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rejection_cli_phase2.py -q`
Expected: FAIL — `test_rejecting_a_whole_synced_config_file_is_refused` records the rejection instead of raising.

- [ ] **Step 3: Write minimal implementation**

In `cmd_reject`, beside the existing `snapshot-section` guard:

```python
    if kind == "snapshot-file" and subject in SNAPSHOT_FILES and not force:
        raise MassRejectionRefusedError(
            f"rejecting {subject!r} wholesale would stop syncing it entirely; "
            f"reject a section with kind snapshot-section, or a key with kind "
            f"settings-key, or pass --force if that is really what you want"
        )
```

Place it after address resolution, so an unknown subject still reports as `UnknownRejectionTargetError` rather than being masked by a guard message — the same ordering Phase 1's section guard uses.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_rejection_cli_phase2.py -q`
Expected: 14 passed

Then: `uv run pytest tests/ -q`

- [ ] **Step 5: Format, lint, commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black scripts/config_sync.py tests/test_rejection_cli_phase2.py
uv run ruff check --fix scripts/config_sync.py tests/test_rejection_cli_phase2.py
uv run pytest tests/ -q
git add scripts/config_sync.py tests/test_rejection_cli_phase2.py
git commit -m "fix(config-sync): refuse a wholesale rejection of a synced config file"
```

---

### Task 10: One walk per kind, across every module boundary

**Files:**
- Test: `tests/test_rejection_phase2_end_to_end.py` (create)

**Interfaces:**
- Consumes: everything from Tasks 1-9.
- Produces: no code.

Phase 1's final review found three Criticals that nine task-scoped reviews could not see, because every suite was unit-level and the one test crossing two modules had a fixture that hid the defect. This task exists so that does not repeat.

Each walk must use **production-shaped state**: a consolidated snapshot with a real `timestamp` field, a rejection recorded *before* it, and the assertion that the content is still withheld. That ordering is what would have caught Phase 1's C1.

- [ ] **Step 1: Write the failing test**

```python
"""One walk per new kind, across every module boundary.

Production-shaped on purpose: the consolidated snapshot carries a `timestamp`
that is STRICTLY NEWER than the rejection, because `cmd_consolidate` regenerates
it on every run. A filter that passed that timestamp as `source_timestamp` would
never suppress anything — which is exactly the defect that survived nine
unit-level suites in phase 1.
"""

import json

import pytest

import config_sync

REJECTED_AT = "2026-08-03T09:00:00+00:00"
CONSOLIDATED_AT = "2026-08-03T12:00:00+00:00"

SETTINGS = {
    "permissions": {"defaultMode": "acceptEdits"},
    "enabledPlugins": {"open-memory@open-memory": True},
    "model": "opus",
}


@pytest.fixture(autouse=True)
def _isolated_claude_home(claude_home):
    return claude_home


def _repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "machines").mkdir(parents=True)
    (repo / "consolidated").mkdir(parents=True)
    (repo / "machines" / "machine-a.json").write_text(
        json.dumps(
            {
                "machine_id": "machine-a",
                "timestamp": "2026-08-03T08:00:00+00:00",
                "files": {"settings.json": json.dumps(SETTINGS)},
            }
        ),
        encoding="utf-8",
    )
    (repo / "consolidated" / "snapshot.json").write_text(
        json.dumps(
            {"timestamp": CONSOLIDATED_AT, "files": {"settings.json": json.dumps(SETTINGS)}}
        ),
        encoding="utf-8",
    )
    return repo


def _consolidated(repo):
    return json.loads((repo / "consolidated" / "snapshot.json").read_text(encoding="utf-8"))


def _settings_in(repo):
    return json.loads(_consolidated(repo)["files"]["settings.json"])


def test_a_settings_key_walks_from_reject_to_a_stripped_consolidated_snapshot(
    tmp_path, capsys
):
    repo = _repo(tmp_path)

    # Hop 1 — the operator rejects it network-wide.
    config_sync.cmd_reject(
        str(repo),
        "settings-key",
        "-",
        "--key",
        "permissions",
        "--key",
        "defaultMode",
        "--scope",
        "network",
    )
    recorded = json.loads(capsys.readouterr().out)
    assert recorded["scope"] == "network"

    # Hop 2 — the record landed in the SHARED repo, not the local ledger.
    assert list((repo / "rejections").glob("*.json"))

    # Hop 3 — consolidate strips it, and says so in the audit trail.
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()
    assert "defaultMode" not in _settings_in(repo)["permissions"]
    assert recorded["address"] in _consolidated(repo)["rejected"]

    # Hop 4 — the precondition that makes hop 3 meaningful: the snapshot's own
    # timestamp is NEWER than the rejection, so a generation-time comparison
    # would have let the key through.
    assert _consolidated(repo)["timestamp"] > REJECTED_AT

    # Hop 5 — its siblings survived.
    assert _settings_in(repo)["model"] == "opus"

    # Hop 6 — unreject puts it back on the next consolidate.
    config_sync.cmd_unreject(str(repo), recorded["id"])
    capsys.readouterr()
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()
    assert _settings_in(repo)["permissions"]["defaultMode"] == "acceptEdits"


def test_a_plugin_rejection_is_visible_to_rejections_and_reversible(tmp_path, capsys):
    repo = _repo(tmp_path)

    config_sync.cmd_reject(str(repo), "plugin", "open-memory@open-memory")
    recorded = json.loads(capsys.readouterr().out)

    config_sync.cmd_rejections(str(repo))
    listed = json.loads(capsys.readouterr().out)["rejections"]
    assert [entry["address"] for entry in listed] == ["open-memory@open-memory"]
    assert [entry["kind"] for entry in listed] == ["plugin"]

    config_sync.cmd_unreject(str(repo), recorded["id"])
    capsys.readouterr()
    config_sync.cmd_rejections(str(repo))
    assert json.loads(capsys.readouterr().out)["rejections"] == []


def test_a_hook_rejection_records_its_tier_and_survives_an_interpreter_change(
    tmp_path, capsys, claude_home
):
    repo = _repo(tmp_path)
    (claude_home / "settings.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python3 /abs/scripts/enforce_gates.py",
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    config_sync.cmd_reject(
        str(repo),
        "hook-registration",
        "enforce_gates.py",
        "--event",
        "PreToolUse",
        "--matcher",
        "Bash",
    )
    recorded = json.loads(capsys.readouterr().out)
    assert recorded["tier"] == "2"

    # The whole reason tier 2 exists: the same registration, reinstalled under a
    # different interpreter and a different directory, is still the same hook.
    from config_sync_hooks import HookSite
    from config_sync_rejection_hooks import HookRegistrationAddressor

    reinstalled = HookSite(
        event="PreToolUse",
        group_index=0,
        hook_index=0,
        matcher="Bash",
        command="/new/uv/bin/python /somewhere/else/enforce_gates.py",
    )
    assert HookRegistrationAddressor().matches(
        recorded["address"], int(recorded["tier"]), reinstalled
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rejection_phase2_end_to_end.py -q`
Expected: PASS if Tasks 1-9 are correct. If any hop fails, that hop names the module boundary that is wrong — fix the production code, not the test's expectations.

- [ ] **Step 3: Reconcile**

There is no implementation step here. If a walk fails, diagnose which task's deliverable is at fault and fix it there, then re-run this file and that task's own suite.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest tests/ -q`
Then confirm hermeticity: `HOME=$(mktemp -d) uv run pytest tests/test_rejection_phase2_end_to_end.py -q` and check no `.claude` directory appears in that temp dir.

- [ ] **Step 5: Format, lint, commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black tests/test_rejection_phase2_end_to_end.py
uv run ruff check --fix tests/test_rejection_phase2_end_to_end.py
uv run pytest tests/ -q
git add tests/test_rejection_phase2_end_to_end.py
git commit -m "test(config-sync): walk each phase 2 kind across every module boundary"
```

---

### Task 11: Document the three new kinds

**Files:**
- Modify: `skills/config-sync/SKILL.md`
- Test: `tests/test_rejection_skill_docs.py` (append)

**Interfaces:**
- Consumes: the command surface from Task 8.
- Produces: no code. The SKILL is what an operator actually reads; a kind nobody documents is a kind nobody uses.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_rejection_skill_docs.py`:

```python
def test_every_phase_2_kind_is_documented():
    text = SKILL.read_text(encoding="utf-8")
    for kind in ("settings-key", "plugin", "hook-registration"):
        assert kind in text, f"{kind} is not documented in SKILL.md"


def test_the_hook_addressing_options_are_documented():
    text = SKILL.read_text(encoding="utf-8")
    for option in ("--event", "--matcher", "--key"):
        assert option in text, f"{option} is not documented in SKILL.md"


def test_the_documented_kinds_match_the_engine():
    import config_sync_rejections as rejections

    text = SKILL.read_text(encoding="utf-8")
    for kind in rejections.REJECTION_KINDS:
        assert kind in text, f"{kind} is advertised by the engine but undocumented"


def test_the_skill_says_rejection_does_not_delete_an_existing_hook():
    text = SKILL.read_text(encoding="utf-8")
    assert "hooks-prune" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rejection_skill_docs.py -q`
Expected: FAIL — `settings-key is not documented in SKILL.md`

- [ ] **Step 3: Write the documentation**

In the Step 4 "Reject content you never want" block that Phase 1 added, extend the examples to cover all five kinds:

````markdown
Phase 1 kinds address the snapshot; phase 2 adds the rest of what syncs:

```bash
# a section of a markdown file, or a whole file
py "$ENGINE" reject "$REPO" snapshot-section CLAUDE.md --section "## Memory protocol"
py "$ENGINE" reject "$REPO" snapshot-file rules/unwanted.md --scope local

# one key inside settings.json -- --key is repeatable and gives the path in order
py "$ENGINE" reject "$REPO" settings-key - --key permissions --key defaultMode

# a marketplace plugin, by the id plugins-plan uses
py "$ENGINE" reject "$REPO" plugin open-memory@open-memory

# one hook registration -- a script basename is only unique within an
# event and matcher, so both are required
py "$ENGINE" reject "$REPO" hook-registration enforce_gates.py \
  --event PreToolUse --matcher Bash
```

A hook rejection records the **identity tier** it resolved to. Tier 2 (event +
matcher + script name) survives an interpreter change or a relocation, which is
what stops a reinstalled hook coming back under a new identity. When two
registrations share an event, a matcher and a script name, resolution falls to
tier 3 — an exact match on the command — because at that point you are rejecting
one specific copy.

> **Rejecting a hook stops it being wired; it does not unregister it.**
> config-sync only ever edits its own marked entries, so a registration already
> in `settings.json` stays until `hooks-prune` removes it. The two compose:
> `reject` stops it coming back, `hooks-prune` takes out what is already there.
````

In the Step 3 union-only warning, add a sentence noting that `settings.json` keys are rejectable individually, so retiring one setting no longer means rejecting the whole file.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_rejection_skill_docs.py -q`
Expected: 8 passed (4 from phase 1, 4 here)

Then: `uv run pytest tests/ -q`

- [ ] **Step 5: Commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black tests/test_rejection_skill_docs.py
uv run ruff check --fix tests/test_rejection_skill_docs.py
uv run pytest tests/ -q
git add skills/config-sync/SKILL.md tests/test_rejection_skill_docs.py
git commit -m "docs(config-sync): document the phase 2 rejection kinds"
```

---

## Verification

After Task 11, prove each new kind end to end against a scratch repo:

```bash
cd /tmp && rm -rf phase2-check && mkdir -p phase2-check/{machines,consolidated}
cd phase2-check
SETTINGS='{"permissions":{"defaultMode":"acceptEdits"},"model":"opus"}'
python3 -c "
import json
json.dump({'machine_id':'m1','timestamp':'2026-08-03T08:00:00+00:00',
           'files':{'settings.json':'''$SETTINGS'''}}, open('machines/m1.json','w'))
json.dump({'files':{'settings.json':'''$SETTINGS'''}}, open('consolidated/snapshot.json','w'))
"

ENGINE=/Users/ai/Projects/mente-apex-plugin/scripts/config_sync.py
python3 "$ENGINE" reject . settings-key - --key permissions --key defaultMode --scope network
python3 "$ENGINE" consolidate .
python3 - <<'PY'
import json
snapshot = json.load(open("consolidated/snapshot.json"))
settings = json.loads(snapshot["files"]["settings.json"])
present = "defaultMode" in settings.get("permissions", {})
print("STILL PRESENT - FAIL" if present else "stripped - PASS")
print("model survived:", settings.get("model") == "opus")
PY
```

Expected: `stripped - PASS` and `model survived: True`.

Inspect `.files` rather than grepping the raw snapshot — `cmd_consolidate` writes the `"rejected"` audit trail into the same document, and each address contains the rejected key's own text, so a naive grep matches the audit trail and reports a false failure. Phase 1's verification section carries the same note for the same reason.

## Phase 3

Per-content provenance — the fix for the bounded convergence Phase 1 documents, where a machine still holding rejected content resurrects it via its always-fresh export timestamp — is a separate plan and needs a design session first. Nothing in phase 2 assumes it: every local-side filter passes `""` as `source_timestamp` precisely because there is no content provenance to compare against yet.
