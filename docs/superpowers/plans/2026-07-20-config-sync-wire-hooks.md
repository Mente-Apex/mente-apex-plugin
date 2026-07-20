# config-sync wire-hooks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a gated, idempotent `hooks-plan`/`hooks-apply` pair to config-sync that registers declared, repo-shipped hooks a machine is missing — written in portable `${TOKEN}` form — closing the provisioning half of #65 (#68).

**Architecture:** A new `scripts/config_sync_hooks.py` mirrors `config_sync_plugins.py`: a **pure planner** (`plan_hook_wiring`) diffs hook *declarations* (discovered from `hooks/hooks.json` files under the named roots from #67) against the live `settings.json`, emitting union-only `register` actions; a **gated executor** (`execute_hook_plan`) writes marker-tagged, tokenised registrations through an injected `SettingsHost`. Two thin CLI wrappers in `config_sync.py` register the commands. No module globals; DIP throughout.

**Tech Stack:** Python 3.14 stdlib only (`json`, `hashlib`, `pathlib`, `dataclasses`, `typing.Protocol`); pytest. Depends on `config_sync_roots` (#67, already merged).

## Global Constraints

- **Branch:** all work on `feat/config-sync-wire-hooks` (already created off `main`). Never commit to `main`.
- **Python / tests:** run every test via `.venv/bin/python -m pytest` (pyenv 3.14.6). Never bare `pytest`/`python3` (system Python 3.9 lacks `tomllib` and fails collection).
- **Stdlib only:** engine files import nothing third-party.
- **DIP / no globals:** the planner is pure (takes data in, returns a plan); the executor depends only on the `SettingsHost` Protocol. Production wiring injects the real host; tests inject a fake. Mirror `config_sync_plugins.py`'s `PluginRegistryReader` / `PluginInstaller` split.
- **Union-only:** never unregister, prune, move, or edit a hook config-sync did not itself register. Only *add* missing declared hooks.
- **Marker:** every registered hook's command ends with ` # config-sync:<hook_id>` where `hook_id` is a 12-hex SHA-1 of the clean (pre-marker) declaration. This is the sole identity config-sync recognises as "its own."
- **Portability:** stored commands are always in `${TOKEN}` form via `config_sync_roots`; `${CLAUDE_PLUGIN_ROOT}` in a declaration resolves to the discovering root's token.
- **Descriptive names** everywhere — no single-letter or abbreviated variables, including in comprehensions/generators.
- **Commit trailer (every commit):** `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## File Structure

- **Create** `scripts/config_sync_hooks.py` — declaration discovery, identity/marker helpers, pure planner, gated executor, `SettingsHost` Protocol + `ClaudeSettingsHost`.
- **Modify** `scripts/config_sync_roots.py` — add `RootRegistry.named_roots()` (roots excluding the HOME catch-all; discovery sources).
- **Modify** `scripts/config_sync.py` — add `cmd_hooks_plan` / `cmd_hooks_apply` and register both in `COMMANDS`.
- **Modify** `skills/config-sync/SKILL.md` and `skills/config-sync-setup/SKILL.md` — surface the wire-hooks step (plan → consent → apply).
- **Create** `tests/test_hook_wiring.py` — unit tests for roots accessor, discovery, identity, planner, executor.
- **Create** `tests/test_hooks_cli.py` — CLI-level plan/apply + idempotency + #67 round-trip.

---

### Task 1: `named_roots()` accessor on `RootRegistry`

Discovery scans the declared repo roots but **not** the `HOME` catch-all (HOME is a portability root, not a hook source). Expose that subset.

**Files:**
- Modify: `scripts/config_sync_roots.py`
- Test: `tests/test_hook_wiring.py`

**Interfaces:**
- Consumes: existing `config_sync_roots.Root` (`.token`, `.path`), `RootRegistry`.
- Produces: `RootRegistry.named_roots() -> list[Root]` — every root whose token is not `"HOME"`, in declaration order.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hook_wiring.py
import config_sync_roots


def test_named_roots_excludes_home_catch_all():
    registry = config_sync_roots.RootRegistry([
        config_sync_roots.Root("HOME", "/Users/ai"),
        config_sync_roots.Root("MENTE_APEX_MEMORY", "/Users/ai/Projects/mente-apex-memory"),
    ])
    named = registry.named_roots()
    assert [root.token for root in named] == ["MENTE_APEX_MEMORY"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_hook_wiring.py::test_named_roots_excludes_home_catch_all -v`
Expected: FAIL — `AttributeError: 'RootRegistry' object has no attribute 'named_roots'`

- [ ] **Step 3: Write minimal implementation**

Add to `RootRegistry` in `scripts/config_sync_roots.py` (next to `_roots_longest_first`):

```python
    def named_roots(self) -> List[Root]:
        """Declared repo roots (everything except the HOME catch-all) — the
        places wire-hooks scans for hook declarations."""
        return [root for root in self._roots if root.token != "HOME"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_hook_wiring.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/config_sync_roots.py tests/test_hook_wiring.py
git commit -m "feat(config-sync): expose RootRegistry.named_roots for hook discovery (#68)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Identity + command-token helpers

Pure helpers: resolve `${CLAUDE_PLUGIN_ROOT}` to a root token, compute the stable `hook_id`, and build/parse the marker.

**Files:**
- Create: `scripts/config_sync_hooks.py`
- Test: `tests/test_hook_wiring.py`

**Interfaces:**
- Produces:
  - `MARKER_PREFIX = "# config-sync:"`
  - `resolve_command(command: str, root_token: str) -> str` — replaces `${CLAUDE_PLUGIN_ROOT}` with `${<root_token>}`.
  - `hook_id_of(root_token: str, event: str, matcher: str, command: str) -> str` — 12-hex SHA-1 of the four fields (command is the clean, resolved, pre-marker string).
  - `marker_for(hook_id: str) -> str` — returns `"# config-sync:<hook_id>"`.
  - `registered_hook_ids(settings: dict) -> set[str]` — every `hook_id` whose marker appears in a hook command in `settings["hooks"]`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_hook_wiring.py
import config_sync_hooks


def test_resolve_command_maps_plugin_root_to_token():
    assert config_sync_hooks.resolve_command(
        "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/protect_brain.py", "MENTE_APEX_MEMORY"
    ) == "python3 ${MENTE_APEX_MEMORY}/hooks/protect_brain.py"


def test_hook_id_is_stable_12_hex_and_marker_round_trips():
    hook_id = config_sync_hooks.hook_id_of(
        "MENTE_APEX_MEMORY", "PreToolUse", "Write|Edit",
        "python3 ${MENTE_APEX_MEMORY}/hooks/protect_brain.py",
    )
    assert len(hook_id) == 12 and all(character in "0123456789abcdef" for character in hook_id)
    # same inputs -> same id
    assert hook_id == config_sync_hooks.hook_id_of(
        "MENTE_APEX_MEMORY", "PreToolUse", "Write|Edit",
        "python3 ${MENTE_APEX_MEMORY}/hooks/protect_brain.py",
    )
    marked = "python3 x.py " + config_sync_hooks.marker_for(hook_id)
    assert config_sync_hooks.registered_hook_ids(
        {"hooks": {"PreToolUse": [{"matcher": "Write|Edit",
                                   "hooks": [{"type": "command", "command": marked}]}]}}
    ) == {hook_id}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_hook_wiring.py::test_resolve_command_maps_plugin_root_to_token -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'config_sync_hooks'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/config_sync_hooks.py`:

```python
"""Hook provisioning for config-sync — the wire-hooks channel (#68).

Discovers `hooks/hooks.json` declarations under the named roots from
config_sync_roots (#67), diffs them against the live settings.json, and
registers any missing hooks in portable ${TOKEN} form behind a consent gate.

DIP: the planner is pure (data in, plan out); the executor depends only on the
SettingsHost Protocol. Union-only — config-sync only ever adds hooks it marks as
its own, and never touches hand-added or unmarked hooks.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import List, Optional, Protocol, runtime_checkable

PLUGIN_ROOT_PLACEHOLDER = "${CLAUDE_PLUGIN_ROOT}"
MARKER_PREFIX = "# config-sync:"
_MARKER_RE = re.compile(re.escape(MARKER_PREFIX) + r"([0-9a-f]{12})")


def resolve_command(command: str, root_token: str) -> str:
    """Map the native ${CLAUDE_PLUGIN_ROOT} placeholder onto the discovering
    root's portable token, so the stored registration is machine-independent."""
    return command.replace(PLUGIN_ROOT_PLACEHOLDER, "${" + root_token + "}")


def hook_id_of(root_token: str, event: str, matcher: str, command: str) -> str:
    """Stable 12-hex identity for a declared hook, over its clean (pre-marker)
    fields. Null-joined so no field boundary can be forged by another."""
    payload = "\0".join([root_token, event, matcher, command]).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:12]


def marker_for(hook_id: str) -> str:
    return MARKER_PREFIX + hook_id


def registered_hook_ids(settings: dict) -> set:
    """Every config-sync hook_id already present in settings.json, read from the
    marker trailing each managed hook's command."""
    found = set()
    for matcher_groups in settings.get("hooks", {}).values():
        for matcher_group in matcher_groups:
            for hook in matcher_group.get("hooks", []):
                command = hook.get("command", "")
                if isinstance(command, str):
                    match = _MARKER_RE.search(command)
                    if match:
                        found.add(match.group(1))
    return found
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_hook_wiring.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/config_sync_hooks.py tests/test_hook_wiring.py
git commit -m "feat(config-sync): hook identity + marker + command-token helpers (#68)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Declaration discovery from named roots

Read each named root's `hooks/hooks.json`, walk its `hooks` block, and produce one `DeclaredHook` per hook entry — commands resolved to `${TOKEN}` form, ids assigned. Malformed/missing files are skipped, never fatal.

**Files:**
- Modify: `scripts/config_sync_hooks.py`
- Test: `tests/test_hook_wiring.py`

**Interfaces:**
- Consumes: `config_sync_roots.RootRegistry.named_roots()`; helpers from Task 2.
- Produces:
  - `@dataclass(frozen=True) class DeclaredHook: hook_id: str; event: str; matcher: str; command: str; timeout: Optional[int]`
  - `discover_declarations(registry) -> list[DeclaredHook]` — reads `<root.path>/hooks/hooks.json` for each named root.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_hook_wiring.py — uses tmp_path
import json


def _write_declaration(root_dir, block):
    hooks_dir = root_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    (hooks_dir / "hooks.json").write_text(json.dumps(block))


def test_discover_reads_declaration_and_resolves_token(tmp_path):
    repo = tmp_path / "mem"
    _write_declaration(repo, {"hooks": {"PreToolUse": [
        {"matcher": "Write|Edit", "hooks": [
            {"type": "command",
             "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/protect_brain.py",
             "timeout": 10}]}]}})
    registry = config_sync_roots.RootRegistry([
        config_sync_roots.Root("HOME", str(tmp_path)),
        config_sync_roots.Root("MEM", str(repo)),
    ])

    declarations = config_sync_hooks.discover_declarations(registry)

    assert len(declarations) == 1
    declaration = declarations[0]
    assert declaration.event == "PreToolUse"
    assert declaration.matcher == "Write|Edit"
    assert declaration.command == "python3 ${MEM}/hooks/protect_brain.py"
    assert declaration.timeout == 10
    assert declaration.hook_id == config_sync_hooks.hook_id_of(
        "MEM", "PreToolUse", "Write|Edit", declaration.command)


def test_discover_ignores_missing_and_malformed(tmp_path):
    repo_missing = tmp_path / "nohooks"
    repo_missing.mkdir()
    repo_bad = tmp_path / "bad"
    (repo_bad / "hooks").mkdir(parents=True)
    (repo_bad / "hooks" / "hooks.json").write_text("{ not json")
    registry = config_sync_roots.RootRegistry([
        config_sync_roots.Root("HOME", str(tmp_path)),
        config_sync_roots.Root("NOHOOKS", str(repo_missing)),
        config_sync_roots.Root("BAD", str(repo_bad)),
    ])
    assert config_sync_hooks.discover_declarations(registry) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_hook_wiring.py::test_discover_reads_declaration_and_resolves_token -v`
Expected: FAIL — `AttributeError: module 'config_sync_hooks' has no attribute 'discover_declarations'`

- [ ] **Step 3: Write minimal implementation**

Add to `scripts/config_sync_hooks.py` (import `json` and `Path` at top: extend the import block to `import hashlib`, `import json`, `import re`, and `from pathlib import Path`):

```python
@dataclass(frozen=True)
class DeclaredHook:
    hook_id: str
    event: str
    matcher: str
    command: str            # tokenised (${TOKEN}/...), pre-marker
    timeout: Optional[int]


def discover_declarations(registry) -> List[DeclaredHook]:
    """Read each named root's hooks/hooks.json and flatten it into DeclaredHooks
    with resolved tokens and stable ids. Missing/malformed files are skipped."""
    declarations: List[DeclaredHook] = []
    for root in registry.named_roots():
        declaration_path = Path(root.path) / "hooks" / "hooks.json"
        try:
            data = json.loads(declaration_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        for event, matcher_groups in data.get("hooks", {}).items():
            if not isinstance(matcher_groups, list):
                continue
            for matcher_group in matcher_groups:
                matcher = matcher_group.get("matcher", "")
                for hook in matcher_group.get("hooks", []):
                    raw_command = hook.get("command")
                    if not isinstance(raw_command, str):
                        continue
                    command = resolve_command(raw_command, root.token)
                    declarations.append(DeclaredHook(
                        hook_id=hook_id_of(root.token, event, matcher, command),
                        event=event,
                        matcher=matcher,
                        command=command,
                        timeout=hook.get("timeout"),
                    ))
    return declarations
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_hook_wiring.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/config_sync_hooks.py tests/test_hook_wiring.py
git commit -m "feat(config-sync): discover hook declarations from named roots (#68)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Pure planner `plan_hook_wiring`

Diff declared hooks against the ids already registered in settings; emit a `register` action per missing hook. Never unregister. Already-present → empty plan (idempotent). Unmarked hand-added hooks are invisible to the diff.

**Files:**
- Modify: `scripts/config_sync_hooks.py`
- Test: `tests/test_hook_wiring.py`

**Interfaces:**
- Consumes: `DeclaredHook` (Task 3); `registered_hook_ids` (Task 2).
- Produces:
  - `@dataclass class HookAction: verb: str; hook_id: str; detail: dict = field(default_factory=dict)` — verb is always `"register"`; `detail` carries `{"event","matcher","command","timeout"}`.
  - `@dataclass class HookPlan: actions: list = field(default_factory=list); skipped: list = field(default_factory=list)`
  - `plan_hook_wiring(declarations: list[DeclaredHook], settings: dict) -> HookPlan`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_hook_wiring.py
def _declaration(command="python3 ${MEM}/hooks/protect_brain.py"):
    hook_id = config_sync_hooks.hook_id_of("MEM", "PreToolUse", "Write|Edit", command)
    return config_sync_hooks.DeclaredHook(hook_id, "PreToolUse", "Write|Edit", command, 10)


def test_plan_registers_missing_hook():
    declaration = _declaration()
    plan = config_sync_hooks.plan_hook_wiring([declaration], {"hooks": {}})
    assert len(plan.actions) == 1
    action = plan.actions[0]
    assert action.verb == "register"
    assert action.hook_id == declaration.hook_id
    assert action.detail["command"] == declaration.command
    assert action.detail["event"] == "PreToolUse"


def test_plan_is_empty_when_already_registered():
    declaration = _declaration()
    marked = declaration.command + " " + config_sync_hooks.marker_for(declaration.hook_id)
    settings = {"hooks": {"PreToolUse": [
        {"matcher": "Write|Edit", "hooks": [{"type": "command", "command": marked}]}]}}
    plan = config_sync_hooks.plan_hook_wiring([declaration], settings)
    assert plan.actions == []


def test_plan_ignores_unmarked_hand_added_hook_for_same_script():
    declaration = _declaration()
    # Same script path, but NO marker -> config-sync must not consider it its own.
    settings = {"hooks": {"PreToolUse": [
        {"matcher": "Write|Edit",
         "hooks": [{"type": "command", "command": declaration.command}]}]}}
    plan = config_sync_hooks.plan_hook_wiring([declaration], settings)
    assert len(plan.actions) == 1   # still proposes its own marked registration
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_hook_wiring.py::test_plan_registers_missing_hook -v`
Expected: FAIL — `AttributeError: module 'config_sync_hooks' has no attribute 'plan_hook_wiring'`

- [ ] **Step 3: Write minimal implementation**

Add to `scripts/config_sync_hooks.py`:

```python
@dataclass
class HookAction:
    verb: str                       # always "register" (union-only)
    hook_id: str
    detail: dict = field(default_factory=dict)


@dataclass
class HookPlan:
    actions: list = field(default_factory=list)
    skipped: list = field(default_factory=list)


def plan_hook_wiring(declarations: List[DeclaredHook], settings: dict) -> HookPlan:
    """Pure planner: emit a register action for every declared hook whose id is
    not already marked in settings. Never unregisters; unmarked hooks are ignored."""
    already_registered = registered_hook_ids(settings)
    plan = HookPlan()
    for declaration in declarations:
        if declaration.hook_id in already_registered:
            plan.skipped.append(f"{declaration.hook_id}: already registered")
            continue
        plan.actions.append(HookAction("register", declaration.hook_id, {
            "event": declaration.event,
            "matcher": declaration.matcher,
            "command": declaration.command,
            "timeout": declaration.timeout,
        }))
    return plan
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_hook_wiring.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/config_sync_hooks.py tests/test_hook_wiring.py
git commit -m "feat(config-sync): pure planner for hook wiring (union-only) (#68)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: `SettingsHost` + gated executor `execute_hook_plan`

Write each `register` action into settings as a new marker-tagged matcher group, through an injected host. One read + one write per apply. Idempotent by construction (re-plan against fresh settings yields no actions).

**Files:**
- Modify: `scripts/config_sync_hooks.py`
- Test: `tests/test_hook_wiring.py`

**Interfaces:**
- Consumes: `HookPlan`, `HookAction`, `marker_for` (Tasks 2/4).
- Produces:
  - `@runtime_checkable class SettingsHost(Protocol): def read_settings(self) -> dict: ...; def write_settings(self, settings: dict) -> None: ...`
  - `@dataclass class HookOutcome: hook_id: str; ok: bool; message: str = ""`
  - `@dataclass class HookResult: outcomes: list = field(default_factory=list); skipped: list = field(default_factory=list)`
  - `execute_hook_plan(plan: HookPlan, host: SettingsHost) -> HookResult`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_hook_wiring.py
class FakeSettingsHost:
    def __init__(self, settings=None):
        self.settings = settings if settings is not None else {}
        self.writes = 0

    def read_settings(self):
        import copy
        return copy.deepcopy(self.settings)

    def write_settings(self, settings):
        self.settings = settings
        self.writes += 1


def test_execute_writes_marked_registration_and_is_idempotent():
    declaration = _declaration()
    host = FakeSettingsHost({"hooks": {}})

    plan = config_sync_hooks.plan_hook_wiring([declaration], host.read_settings())
    result = config_sync_hooks.execute_hook_plan(plan, host)

    assert [outcome.ok for outcome in result.outcomes] == [True]
    groups = host.settings["hooks"]["PreToolUse"]
    command = groups[0]["hooks"][0]["command"]
    assert command == declaration.command + " " + config_sync_hooks.marker_for(declaration.hook_id)
    assert groups[0]["hooks"][0]["timeout"] == 10
    assert host.writes == 1

    # Second pass: nothing to do, no extra write.
    plan2 = config_sync_hooks.plan_hook_wiring([declaration], host.read_settings())
    result2 = config_sync_hooks.execute_hook_plan(plan2, host)
    assert result2.outcomes == []
    assert host.writes == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_hook_wiring.py::test_execute_writes_marked_registration_and_is_idempotent -v`
Expected: FAIL — `AttributeError: module 'config_sync_hooks' has no attribute 'execute_hook_plan'`

- [ ] **Step 3: Write minimal implementation**

Add to `scripts/config_sync_hooks.py`:

```python
@runtime_checkable
class SettingsHost(Protocol):
    def read_settings(self) -> dict: ...

    def write_settings(self, settings: dict) -> None: ...


@dataclass
class HookOutcome:
    hook_id: str
    ok: bool
    message: str = ""


@dataclass
class HookResult:
    outcomes: list = field(default_factory=list)
    skipped: list = field(default_factory=list)


def execute_hook_plan(plan: HookPlan, host: SettingsHost) -> HookResult:
    """Apply each register action as a new marker-tagged matcher group. One write
    total, only when there is at least one action (idempotent no-op otherwise)."""
    result = HookResult(skipped=list(plan.skipped))
    if not plan.actions:
        return result
    settings = host.read_settings()
    hooks_block = settings.setdefault("hooks", {})
    for action in plan.actions:
        event_groups = hooks_block.setdefault(action.detail["event"], [])
        marked_command = action.detail["command"] + " " + marker_for(action.hook_id)
        hook_entry = {"type": "command", "command": marked_command}
        if action.detail.get("timeout") is not None:
            hook_entry["timeout"] = action.detail["timeout"]
        event_groups.append({"matcher": action.detail["matcher"], "hooks": [hook_entry]})
        result.outcomes.append(HookOutcome(action.hook_id, ok=True))
    host.write_settings(settings)
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_hook_wiring.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/config_sync_hooks.py tests/test_hook_wiring.py
git commit -m "feat(config-sync): gated executor writes marked hook registrations (#68)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Real `ClaudeSettingsHost` + CLI commands `hooks-plan` / `hooks-apply`

Wire the pure core to the live `~/.claude/settings.json` and expose two commands mirroring `plugins-plan`/`plugins-apply`.

**Files:**
- Modify: `scripts/config_sync_hooks.py` (add `ClaudeSettingsHost`)
- Modify: `scripts/config_sync.py` (add `cmd_hooks_plan`, `cmd_hooks_apply`, register in `COMMANDS`)
- Test: `tests/test_hooks_cli.py`

**Interfaces:**
- Consumes: `_root_registry()` (existing, `config_sync.py:128`), `discover_declarations`, `plan_hook_wiring`, `execute_hook_plan`, `ClaudeSettingsHost`.
- Produces:
  - `config_sync_hooks.ClaudeSettingsHost(claude_dir: Path)` implementing `SettingsHost` (reads/writes `claude_dir/"settings.json"`; missing file → `{}`; write is pretty-printed JSON).
  - `config_sync.cmd_hooks_plan()` — arity 0; prints `{"actions":[...],"skipped":[...]}`.
  - `config_sync.cmd_hooks_apply()` — arity 0; prints `{"outcomes":[...],"skipped":[...]}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hooks_cli.py
import json
import config_sync


def _declare_memory_hook(tmp_path, monkeypatch):
    """A named-root repo shipping a hooks/hooks.json, declared via env var."""
    repo = tmp_path / "mem"
    (repo / "hooks").mkdir(parents=True)
    (repo / "hooks" / "hooks.json").write_text(json.dumps({"hooks": {"PreToolUse": [
        {"matcher": "Write|Edit", "hooks": [
            {"type": "command",
             "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/protect_brain.py",
             "timeout": 10}]}]}}))
    monkeypatch.setenv("CONFIG_SYNC_ROOT_MEM", str(repo))
    return repo


def test_hooks_plan_then_apply_is_idempotent(claude_home, tmp_path, monkeypatch, capsys):
    _declare_memory_hook(tmp_path, monkeypatch)
    (claude_home / "settings.json").write_text('{"model":"opus"}')

    config_sync.cmd_hooks_plan()
    plan = json.loads(capsys.readouterr().out)
    assert len(plan["actions"]) == 1 and plan["actions"][0]["verb"] == "register"

    config_sync.cmd_hooks_apply()
    apply_output = json.loads(capsys.readouterr().out)
    assert len(apply_output["outcomes"]) == 1 and apply_output["outcomes"][0]["ok"] is True

    written = json.loads((claude_home / "settings.json").read_text())
    command = written["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert command.startswith("python3 ${MEM}/hooks/protect_brain.py # config-sync:")
    assert written["model"] == "opus"   # untouched

    # Second apply: no actions, settings unchanged.
    config_sync.cmd_hooks_apply()
    second = json.loads(capsys.readouterr().out)
    assert second["outcomes"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_hooks_cli.py -v`
Expected: FAIL — `AttributeError: module 'config_sync' has no attribute 'cmd_hooks_plan'`

- [ ] **Step 3: Write minimal implementation**

Add to `scripts/config_sync_hooks.py` (needs `import json` and `from pathlib import Path`, already added in Task 3):

```python
class ClaudeSettingsHost:
    """Real SettingsHost over ~/.claude/settings.json. Injected into the CLI
    wrappers; faked in tests."""

    def __init__(self, claude_dir: Path):
        self._settings_path = claude_dir / "settings.json"

    def read_settings(self) -> dict:
        try:
            return json.loads(self._settings_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def write_settings(self, settings: dict) -> None:
        self._settings_path.write_text(
            json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
```

Add to `scripts/config_sync.py` (near `cmd_plugins_plan`, ~line 905):

```python
def cmd_hooks_plan():
    """Query: what declared hooks are missing from local settings.json."""
    registry = _root_registry()
    declarations = config_sync_hooks.discover_declarations(registry)
    host = config_sync_hooks.ClaudeSettingsHost(CLAUDE_DIR)
    plan = config_sync_hooks.plan_hook_wiring(declarations, host.read_settings())
    print(json.dumps({
        "actions": [{"verb": action.verb, "hook_id": action.hook_id, "detail": action.detail}
                    for action in plan.actions],
        "skipped": plan.skipped,
    }, indent=2))


def cmd_hooks_apply():
    """Gated mutation: register the missing declared hooks (marker-tagged)."""
    registry = _root_registry()
    declarations = config_sync_hooks.discover_declarations(registry)
    host = config_sync_hooks.ClaudeSettingsHost(CLAUDE_DIR)
    plan = config_sync_hooks.plan_hook_wiring(declarations, host.read_settings())
    result = config_sync_hooks.execute_hook_plan(plan, host)
    print(json.dumps({
        "outcomes": [{"hook_id": outcome.hook_id, "ok": outcome.ok, "message": outcome.message}
                     for outcome in result.outcomes],
        "skipped": result.skipped,
    }, indent=2))
```

Register both in the `COMMANDS` dict (both arity 0):

```python
    "hooks-plan": (cmd_hooks_plan, 0),
    "hooks-apply": (cmd_hooks_apply, 0),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_hooks_cli.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/config_sync_hooks.py scripts/config_sync.py tests/test_hooks_cli.py
git commit -m "feat(config-sync): hooks-plan/hooks-apply CLI over live settings.json (#68)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Portability round-trip guard (#67 integration)

Prove a wired hook survives export→import portably: register on machine A (HOME=`/A`), export (portabilizes to `${HOME}`/`${MEM}`), import on machine B (HOME=`/B`) resolves to B's paths, and the marker/id is preserved so B never double-registers.

**Files:**
- Test: `tests/test_hooks_cli.py`

**Interfaces:**
- Consumes: `config_sync.cmd_hooks_apply`, `config_sync.cmd_export`, `config_sync._apply_snapshot_file` / `cmd_import` (existing), `config_sync_hooks.registered_hook_ids`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_hooks_cli.py
import config_sync_hooks


def test_wired_hook_survives_export_import_portably(claude_home, tmp_path, monkeypatch, capsys):
    _declare_memory_hook(tmp_path, monkeypatch)   # CONFIG_SYNC_ROOT_MEM -> tmp/mem
    (claude_home / "settings.json").write_text('{"model":"opus"}')
    config_sync.cmd_hooks_apply()
    capsys.readouterr()

    config_sync.cmd_export()
    snapshot = json.loads(capsys.readouterr().out)
    exported = json.loads(snapshot["files"]["settings.json"])
    exported_command = exported["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    # HOME (the claude_home tmp path) is tokenised; MEM stays a token too.
    assert "${MEM}/hooks/protect_brain.py" in exported_command
    assert "# config-sync:" in exported_command

    # Import the snapshot back; MEM still resolves via the same env var here.
    snap_file = tmp_path / "snap.json"
    snap_file.write_text(json.dumps(snapshot))
    config_sync.cmd_import(str(snap_file))
    capsys.readouterr()

    reimported = json.loads((claude_home / "settings.json").read_text())
    reimported_command = reimported["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert reimported_command.startswith(f"python3 {tmp_path / 'mem'}/hooks/protect_brain.py")
    # Marker preserved -> a re-plan sees it as already registered (no double-wire).
    assert config_sync_hooks.registered_hook_ids(reimported)
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `.venv/bin/python -m pytest tests/test_hooks_cli.py::test_wired_hook_survives_export_import_portably -v`
Expected: PASS (this is a guard over already-built behaviour; if it FAILS, the portability/marker interaction is broken — fix before proceeding).

- [ ] **Step 3: (only if red) fix the interaction**

If the marker is lost or the command isn't tokenised, reconcile `config_sync_roots.portabilize`/`localize` (they must leave `# config-sync:<id>` untouched — the marker has no path prefix, so they should). No change expected.

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all prior tests + these).

- [ ] **Step 5: Commit**

```bash
git add tests/test_hooks_cli.py
git commit -m "test(config-sync): wired hook survives export/import portably (#68)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: Skill-workflow docs (plan → consent → apply)

Surface wire-hooks in the sync flow: `/config-sync` shows the plan and applies only on consent; `/config-sync-setup` mentions it for first-machine setup.

**Files:**
- Modify: `skills/config-sync/SKILL.md`
- Modify: `skills/config-sync-setup/SKILL.md`
- Test: `tests/test_skill_integrity.py` (existing guard must still pass; no new test unless it flags the additions).

**Interfaces:** none (docs).

- [ ] **Step 1: Add the wire-hooks step to `skills/config-sync/SKILL.md`**

Find the section that runs `plugins-plan` / `plugins-apply` (the desired-state convergence step) and add an analogous paragraph immediately after it:

```markdown
### Wire declared hooks

After the plugin convergence step, provision any repo-shipped hooks this machine
is missing:

1. Run `python3 scripts/config_sync.py hooks-plan`. It scans the declared roots
   (`CONFIG_SYNC_ROOT_*`) for `hooks/hooks.json` files and lists the hook
   registrations missing from `~/.claude/settings.json`.
2. If `actions` is empty, say so and move on.
3. Otherwise show the user each hook it would register (event, matcher, command)
   and ask once for confirmation — this is the single consent gate.
4. On yes, run `python3 scripts/config_sync.py hooks-apply`. It writes each
   registration in portable `${TOKEN}` form, tagged `# config-sync:<id>` so it is
   never confused with a hand-added hook. Re-running is a safe no-op.

Never run `hooks-apply` without the user's confirmation.
```

- [ ] **Step 2: Add a first-machine note to `skills/config-sync-setup/SKILL.md`**

Immediately after the portability note added in #67 (the `CONFIG_SYNC_ROOT_<NAME>` paragraph), add:

```markdown
> **Provisioning hooks.** A repo that ships hooks can declare them in a
> `hooks/hooks.json` (the same format Claude Code plugins use). On this machine,
> run `/config-sync` and accept the *wire-hooks* step to register any declared
> hooks that aren't in `settings.json` yet — no hand-editing. Declare where each
> such repo lives with `CONFIG_SYNC_ROOT_<NAME>` so its `${CLAUDE_PLUGIN_ROOT}`
> hook paths resolve on every machine.
```

- [ ] **Step 3: Run the skill-integrity guard + full suite**

Run: `.venv/bin/python -m pytest tests/test_skill_integrity.py -q && .venv/bin/python -m pytest -q`
Expected: PASS. If the integrity guard flags a broken link or structure in the edited SKILL.md files, fix the flagged item and re-run.

- [ ] **Step 4: Commit**

```bash
git add skills/config-sync/SKILL.md skills/config-sync-setup/SKILL.md
git commit -m "docs(config-sync): surface wire-hooks step in sync + setup skills (#68)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Out-of-repo follow-up (not in this plan/PR)

For the memory hooks to actually be wired, `mente-apex-memory` needs a
`hooks/hooks.json` declaring `protect_brain.py` and `enforce_gates.py`, and this
machine needs `CONFIG_SYNC_ROOT_MENTE_APEX_MEMORY` set. Ship that as a small
separate change in that repo, with the user's go-ahead, after this lands.

## Deferred (out of scope, per spec §11)

1. **Update-in-place** for a marked hook whose declaration changed (matcher/timeout
   edited) — this plan is add-only; changed declarations get a new id and register
   alongside. Revisit if it causes churn.
2. **Auto-run in `/config-sync`** vs. explicit command — this plan shows the plan in
   the flow but keeps apply behind explicit consent; no always-on automation.

## Self-Review

- **Spec coverage:** §2 commands → Tasks 4–6; §3 declaration/discovery → Task 3 (+`named_roots` Task 1); §4 unit module/dataclasses → Tasks 2–5; §5 identity/marker/idempotency/no-clobber/token-resolution → Tasks 2,4,5,7; §6 CLI+skills → Tasks 6,8; §7 memory-repo file → "Out-of-repo follow-up"; §8 testing → Tasks 1–7; §10 scope → union-only asserted in Tasks 4/5; §11 open questions → "Deferred". All covered.
- **Placeholder scan:** every code/step block contains real code and exact commands; no TBD/TODO.
- **Type consistency:** `DeclaredHook`/`HookAction`/`HookPlan`/`HookOutcome`/`HookResult`, `discover_declarations`, `plan_hook_wiring(declarations, settings)`, `execute_hook_plan(plan, host)`, `SettingsHost.read_settings/write_settings`, `ClaudeSettingsHost(claude_dir)`, `cmd_hooks_plan`/`cmd_hooks_apply` (arity 0), `hook_id_of`/`marker_for`/`registered_hook_ids`/`resolve_command` — names match across all tasks.
