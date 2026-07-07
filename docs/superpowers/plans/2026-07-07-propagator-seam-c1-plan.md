# Propagator Seam C1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce the `Propagator` seam and two propagators (`SnapshotPropagator`, `ContentBundlePropagator`) so locally-authored skills/agents propagate as complete, hash-gated, atomic bundles — closing PS2 #23 (data loss), PS3 #24 (freeze), D8 #16 (churn), SK1 #26 (heredoc), PS4 #25 (root cause).

**Architecture:** A `Propagator` Protocol is the only abstraction the sync cycle depends on. Concrete propagators receive an injected `SyncContext(claude_dir, repo_dir)` per call — no module globals, so each is unit-testable in isolation. `run_export`/`run_apply` iterate an **injected list** of propagators; `default_propagators()` is the composition root. Adding `MarketplacePropagator` (C2) only appends to that factory (open/closed).

**Tech Stack:** Python 3.14 (pyenv, `.venv`), pytest, `typing.Protocol`, `dataclasses`, `hashlib`.

**Spec:** `docs/superpowers/specs/2026-07-07-propagator-seam-c1-design.md`

## Global Constraints

- **Python 3.14** dev/test (`.venv/bin/python`); engine stays broadly `python3`-runnable.
- **DIP:** propagators depend on `SyncContext` (injected paths) and the `Propagator` Protocol — never the module globals `CLAUDE_DIR`/`CONFIG_REPO`. Reuse the pure helpers from `config_sync` that already take a path or a string (`_collect_dir(base, rel)`, `_clean_settings(raw)`, `_merge_import_settings(a, b)`, `_is_within(path, root)`, `_read`, `_write`).
- **Descriptive names** everywhere (no single-letter loop/comprehension vars).
- **TDD:** red → green → refactor → commit, one test at a time. Run `.venv/bin/python -m pytest tests/ -q`.
- **Union-only deletions** unchanged. **Do not** alter the global `SNAPSHOT_DIRS`/`cmd_scan` (skills must still be secret-scanned locally).
- **Commit per task**, message ends with `Refs #<n>` (issues close via the C2 or a final PR body; use `Refs` here since multiple tasks share issues). Branch: `audit/propagator-seam-c1` (already created).

---

## File Structure

| File | Responsibility |
|---|---|
| `scripts/config_sync_propagators.py` | **New.** `SyncContext`, result/conflict dataclasses, `Propagator` Protocol, `SnapshotPropagator`, `ContentBundlePropagator`, bundle hashing, `run_export`/`run_apply`/`resolve_bundle`, `default_propagators`. |
| `scripts/config_sync.py` | Thin CLI wrappers `cmd_propagate_export` / `cmd_propagate_apply` / `cmd_resolve_bundle`; register in `COMMANDS`. |
| `tests/test_propagators.py` | **New.** Seam + both propagators + resolve, all via injected `SyncContext`. |
| `skills/config-sync/SKILL.md` | Step 1 export → `propagate-export`; Step 4 → `propagate-apply` + conflict `AskUserQuestion` → `resolve-bundle`. |
| `skills/config-sync-manage/SKILL.md` | Note: skills/agents auto-propagate; `share` is plugin-only. |

**Bundle data model (used across tasks):**
- A *bundle source* is a top-level entry in `~/.claude/skills/` or `~/.claude/agents/` — a **dir** (skills, single-file agents-as-dir) or a **file** (single-file agents).
- Manifest `bundle-manifest.json` = `{"name": <entry name>, "kind": "skill"|"agent", "is_dir": bool, "content_hash": <sha256>, "exported_at": <iso8601>, "machine_id": <id>}`.
- Repo storage: `bundles/<kind>s/<name>/` holds the payload files (preserving relative structure) + the manifest. For a file entry `foo.md`, `name="foo.md"`, `is_dir=false`, payload is that one file.
- `content_hash` = sha256 over sorted `(relative_posix_path, file_bytes)` of payload files (manifest excluded).

---

## Task 1: The seam — Protocol, SyncContext, results, run_export/run_apply

**Files:** Create `scripts/config_sync_propagators.py`; Create `tests/test_propagators.py`.

**Interfaces:**
- Produces: `SyncContext(claude_dir, repo_dir)`; `ExportResult(propagator, written, skipped)`; `ApplyResult(propagator, applied, skipped, conflicts)`; `BundleConflict(kind, name, local_hash, repo_hash, local_exported_at, repo_exported_at)`; `Propagator` Protocol with `name`, `export(context)->ExportResult`, `apply(context)->ApplyResult`; `run_export(context, propagators)->list[ExportResult]`; `run_apply(context, propagators)->list[ApplyResult]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_propagators.py
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import config_sync_propagators as propagators


class _FakePropagator:
    name = "fake"
    def __init__(self, written):
        self._written = written
    def export(self, context):
        return propagators.ExportResult(self.name, list(self._written), [])
    def apply(self, context):
        return propagators.ApplyResult(self.name, list(self._written), [], [])


def test_run_export_aggregates_injected_propagators(tmp_path):
    context = propagators.SyncContext(claude_dir=tmp_path / "c", repo_dir=tmp_path / "r")
    results = propagators.run_export(context, [_FakePropagator(["a"]), _FakePropagator(["b"])])
    assert [result.propagator for result in results] == ["fake", "fake"]
    assert [entry for result in results for entry in result.written] == ["a", "b"]
```

- [ ] **Step 2: Run — expect FAIL** (`No module named config_sync_propagators`).

Run: `.venv/bin/python -m pytest tests/test_propagators.py -q`

- [ ] **Step 3: Implement the seam**

```python
# scripts/config_sync_propagators.py
"""The Propagator seam — substitutable propagation channels for config-sync.

DIP: the sync cycle depends only on the Propagator Protocol; concrete
propagators receive an injected SyncContext per call (no module globals);
run_export/run_apply iterate an injected list. See the C1 design spec.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, runtime_checkable

MANIFEST_NAME = "bundle-manifest.json"
BUNDLE_KINDS = {"skill": "skills", "agent": "agents"}  # kind -> ~/.claude subdir


@dataclass(frozen=True)
class SyncContext:
    claude_dir: Path
    repo_dir: Path


@dataclass
class BundleConflict:
    kind: str
    name: str
    local_hash: str
    repo_hash: str
    local_exported_at: str
    repo_exported_at: str


@dataclass
class ExportResult:
    propagator: str
    written: list = field(default_factory=list)
    skipped: list = field(default_factory=list)


@dataclass
class ApplyResult:
    propagator: str
    applied: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)


@runtime_checkable
class Propagator(Protocol):
    name: str
    def export(self, context: SyncContext) -> ExportResult: ...
    def apply(self, context: SyncContext) -> ApplyResult: ...


def run_export(context: SyncContext, propagators: list) -> list:
    return [propagator.export(context) for propagator in propagators]


def run_apply(context: SyncContext, propagators: list) -> list:
    return [propagator.apply(context) for propagator in propagators]
```

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Commit** — `feat(config-sync): add Propagator seam (SyncContext, Protocol, run_export/apply) (Refs #25)`

---

## Task 2: ContentBundlePropagator.export — hash-gated bundle writing (PS3, D8)

**Files:** Modify `scripts/config_sync_propagators.py`; Modify `tests/test_propagators.py`.

**Interfaces:**
- Consumes: `SyncContext`, `ExportResult`.
- Produces: `ContentBundlePropagator` with `export`; helpers `_bundle_sources(context)`, `_payload_files(entry)`, `_content_hash(payload)`, `_repo_bundle_dir(context, kind, name)`, `_read_manifest(bundle_dir)`, `_write_bundle(...)`.

- [ ] **Step 1: Write the failing tests**

```python
def _write_skill(claude_dir, name, files):
    skill_dir = claude_dir / "skills" / name
    for relative, content in files.items():
        target = skill_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return skill_dir


def test_export_writes_all_files_of_multifile_skill(tmp_path):
    claude_dir = tmp_path / "c"; repo_dir = tmp_path / "r"
    _write_skill(claude_dir, "demo", {"SKILL.md": "# demo", "scripts/x.py": "print(1)", "fonts.css": "body{}"})
    context = propagators.SyncContext(claude_dir=claude_dir, repo_dir=repo_dir)

    result = propagators.ContentBundlePropagator().export(context)

    bundle = repo_dir / "bundles" / "skills" / "demo"
    assert (bundle / "scripts" / "x.py").read_text() == "print(1)"   # non-.md/.json/.txt travels (PS2)
    assert (bundle / "fonts.css").read_text() == "body{}"
    assert (bundle / propagators.MANIFEST_NAME).exists()
    assert "skill/demo" in result.written


def test_export_skips_unchanged_and_reexports_changed(tmp_path):
    claude_dir = tmp_path / "c"; repo_dir = tmp_path / "r"
    _write_skill(claude_dir, "demo", {"SKILL.md": "v1"})
    context = propagators.SyncContext(claude_dir=claude_dir, repo_dir=repo_dir)
    bundle_propagator = propagators.ContentBundlePropagator()

    bundle_propagator.export(context)
    second = bundle_propagator.export(context)
    assert "skill/demo" in second.skipped and "skill/demo" not in second.written   # hash gate (D8)

    (claude_dir / "skills" / "demo" / "SKILL.md").write_text("v2")   # rebuild
    third = bundle_propagator.export(context)
    assert "skill/demo" in third.written                             # re-exports (PS3)
```

- [ ] **Step 2: Run — expect FAIL** (`ContentBundlePropagator` undefined).

- [ ] **Step 3: Implement** `ContentBundlePropagator` + helpers:

```python
def _payload_files(entry: Path) -> dict:
    """Map {relative_posix_path: bytes} for a bundle source (file or dir)."""
    if entry.is_file():
        return {entry.name: entry.read_bytes()}
    payload = {}
    for file_path in sorted(entry.rglob("*")):
        if file_path.is_file() and file_path.name != MANIFEST_NAME:
            payload[file_path.relative_to(entry).as_posix()] = file_path.read_bytes()
    return payload


def _content_hash(payload: dict) -> str:
    hasher = hashlib.sha256()
    for relative_path in sorted(payload):
        hasher.update(relative_path.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(payload[relative_path])
        hasher.update(b"\0")
    return hasher.hexdigest()


def _read_manifest(bundle_dir: Path) -> dict:
    manifest_path = bundle_dir / MANIFEST_NAME
    if not manifest_path.exists():
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


class ContentBundlePropagator:
    name = "content-bundle"

    def _sources(self, context: SyncContext):
        for kind, subdir in BUNDLE_KINDS.items():
            root = context.claude_dir / subdir
            if not root.exists():
                continue
            for entry in sorted(root.iterdir()):
                if entry.name == MANIFEST_NAME:
                    continue
                yield kind, entry

    def export(self, context: SyncContext) -> ExportResult:
        result = ExportResult(self.name)
        for kind, entry in self._sources(context):
            name = entry.name
            payload = _payload_files(entry)
            local_hash = _content_hash(payload)
            bundle_dir = context.repo_dir / "bundles" / BUNDLE_KINDS[kind] / name
            if _read_manifest(bundle_dir).get("content_hash") == local_hash:
                result.skipped.append(f"{kind}/{name}")
                continue
            self._write_bundle(bundle_dir, payload, kind, name, entry.is_dir(), local_hash, context)
            result.written.append(f"{kind}/{name}")
        return result

    def _write_bundle(self, bundle_dir, payload, kind, name, is_dir, content_hash, context):
        if bundle_dir.exists():
            import shutil
            shutil.rmtree(bundle_dir)
        for relative_path, content in payload.items():
            target = bundle_dir / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        manifest = {
            "name": name, "kind": kind, "is_dir": is_dir,
            "content_hash": content_hash,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "machine_id": _machine_id(context),
        }
        (bundle_dir / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
```

Add a context-aware `_machine_id(context)` that reads/writes `context.claude_dir / "config-sync-machine-id"` (mirror `config_sync._machine_id` but injected):

```python
def _machine_id(context: SyncContext) -> str:
    id_file = context.claude_dir / "config-sync-machine-id"
    if id_file.exists():
        return id_file.read_text().strip()
    import platform, uuid
    machine_id = f"{platform.node()}-{uuid.uuid4().hex[:8]}"
    id_file.parent.mkdir(parents=True, exist_ok=True)
    id_file.write_text(machine_id)
    return machine_id
```

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Commit** — `feat(config-sync): ContentBundlePropagator.export — hash-gated all-file bundles (Refs #23, Refs #24, Refs #16)`

---

## Task 3: ContentBundlePropagator.apply — install + conflict detection (PS2)

**Files:** Modify `scripts/config_sync_propagators.py`; Modify `tests/test_propagators.py`.

**Interfaces:**
- Consumes: `SyncContext`, `ApplyResult`, `BundleConflict`, `_content_hash`, `_payload_files`, `_read_manifest`, `config_sync._is_within`.
- Produces: `ContentBundlePropagator.apply`; helper `_local_entry_path(context, kind, name)`.

- [ ] **Step 1: Write the failing tests**

```python
def _write_repo_bundle(repo_dir, kind, name, files, content_hash, exported_at="2026-01-01T00:00:00+00:00"):
    bundle = repo_dir / "bundles" / (kind + "s") / name
    for relative, content in files.items():
        target = bundle / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    (bundle / propagators.MANIFEST_NAME).write_text(propagators.json.dumps({
        "name": name, "kind": kind, "is_dir": True,
        "content_hash": content_hash, "exported_at": exported_at, "machine_id": "m",
    }))
    return bundle


def test_apply_installs_absent_bundle_with_all_files(tmp_path):
    claude_dir = tmp_path / "c"; repo_dir = tmp_path / "r"; claude_dir.mkdir()
    files = {"SKILL.md": "# d", "scripts/x.py": "print(1)"}
    _write_repo_bundle(repo_dir, "skill", "demo", files, propagators._content_hash(
        {"SKILL.md": b"# d", "scripts/x.py": b"print(1)"}))
    context = propagators.SyncContext(claude_dir=claude_dir, repo_dir=repo_dir)

    result = propagators.ContentBundlePropagator().apply(context)

    assert (claude_dir / "skills" / "demo" / "scripts" / "x.py").read_text() == "print(1)"
    assert "skill/demo" in result.applied


def test_apply_flags_conflict_and_does_not_overwrite(tmp_path):
    claude_dir = tmp_path / "c"; repo_dir = tmp_path / "r"
    (claude_dir / "skills" / "demo").mkdir(parents=True)
    (claude_dir / "skills" / "demo" / "SKILL.md").write_text("LOCAL")
    _write_repo_bundle(repo_dir, "skill", "demo", {"SKILL.md": "REPO"},
                       content_hash="repo-hash-differs")
    context = propagators.SyncContext(claude_dir=claude_dir, repo_dir=repo_dir)

    result = propagators.ContentBundlePropagator().apply(context)

    assert (claude_dir / "skills" / "demo" / "SKILL.md").read_text() == "LOCAL"   # untouched
    assert len(result.conflicts) == 1 and result.conflicts[0].name == "demo"
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Implement** `apply`:

```python
    def apply(self, context: SyncContext) -> ApplyResult:
        import config_sync
        result = ApplyResult(self.name)
        for kind, subdir in BUNDLE_KINDS.items():
            bundles_root = context.repo_dir / "bundles" / subdir
            if not bundles_root.exists():
                continue
            for bundle_dir in sorted(bundles_root.iterdir()):
                if not bundle_dir.is_dir():
                    continue
                manifest = _read_manifest(bundle_dir)
                name = manifest.get("name", bundle_dir.name)
                repo_hash = manifest.get("content_hash")
                destination = self._local_entry_path(context, kind, name, manifest.get("is_dir", True))
                if not config_sync._is_within(destination, context.claude_dir):
                    result.skipped.append(f"{kind}/{name} (escapes ~/.claude)")
                    continue
                if not destination.exists():
                    self._install(bundle_dir, destination, manifest)
                    result.applied.append(f"{kind}/{name}")
                    continue
                local_hash = _content_hash(_payload_files(destination))
                if local_hash == repo_hash:
                    result.skipped.append(f"{kind}/{name}")
                    continue
                result.conflicts.append(BundleConflict(
                    kind=kind, name=name, local_hash=local_hash, repo_hash=repo_hash or "",
                    local_exported_at="", repo_exported_at=manifest.get("exported_at", ""),
                ))
        return result

    def _local_entry_path(self, context, kind, name, is_dir):
        return context.claude_dir / BUNDLE_KINDS[kind] / name

    def _install(self, bundle_dir, destination, manifest):
        import shutil
        payload = {relative: (bundle_dir / relative).read_bytes()
                   for relative in _payload_files(bundle_dir)}
        if manifest.get("is_dir", True):
            if destination.exists():
                shutil.rmtree(destination)
            for relative_path, content in payload.items():
                target = destination / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(next(iter(payload.values())))
```

Note: `_payload_files(bundle_dir)` on the repo bundle dir naturally excludes `MANIFEST_NAME`.

- [ ] **Step 4: Run — expect PASS.** Add a test: a bundle named `../escape` is skipped via `_is_within`.

- [ ] **Step 5: Commit** — `feat(config-sync): ContentBundlePropagator.apply — install + conflict detection (Refs #23)`

---

## Task 4: resolve_bundle — perform the prompted conflict choice

**Files:** Modify `scripts/config_sync_propagators.py`; Modify `tests/test_propagators.py`.

**Interfaces:**
- Produces: `resolve_bundle(context, kind, name, winner)` where `winner in {"local","repo"}`.

- [ ] **Step 1: Failing tests**

```python
def test_resolve_bundle_repo_overwrites_local(tmp_path):
    claude_dir = tmp_path / "c"; repo_dir = tmp_path / "r"
    (claude_dir / "skills" / "demo").mkdir(parents=True)
    (claude_dir / "skills" / "demo" / "SKILL.md").write_text("LOCAL")
    _write_repo_bundle(repo_dir, "skill", "demo", {"SKILL.md": "REPO"}, content_hash="h")
    context = propagators.SyncContext(claude_dir=claude_dir, repo_dir=repo_dir)

    propagators.resolve_bundle(context, "skill", "demo", "repo")
    assert (claude_dir / "skills" / "demo" / "SKILL.md").read_text() == "REPO"


def test_resolve_bundle_local_reexports_into_repo(tmp_path):
    claude_dir = tmp_path / "c"; repo_dir = tmp_path / "r"
    (claude_dir / "skills" / "demo").mkdir(parents=True)
    (claude_dir / "skills" / "demo" / "SKILL.md").write_text("LOCAL-NEW")
    _write_repo_bundle(repo_dir, "skill", "demo", {"SKILL.md": "OLD"}, content_hash="old")
    context = propagators.SyncContext(claude_dir=claude_dir, repo_dir=repo_dir)

    propagators.resolve_bundle(context, "skill", "demo", "local")
    assert (repo_dir / "bundles" / "skills" / "demo" / "SKILL.md").read_text() == "LOCAL-NEW"
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Implement**

```python
def resolve_bundle(context: SyncContext, kind: str, name: str, winner: str) -> None:
    """Perform a prompted bundle-conflict resolution.

    winner="repo"  -> overwrite the local skill/agent from the repo bundle.
    winner="local" -> re-export the local entry into the repo bundle (local wins).
    """
    propagator = ContentBundlePropagator()
    if winner == "repo":
        bundle_dir = context.repo_dir / "bundles" / BUNDLE_KINDS[kind] / name
        manifest = _read_manifest(bundle_dir)
        destination = propagator._local_entry_path(context, kind, name, manifest.get("is_dir", True))
        propagator._install(bundle_dir, destination, manifest)
    elif winner == "local":
        entry = context.claude_dir / BUNDLE_KINDS[kind] / name
        payload = _payload_files(entry)
        bundle_dir = context.repo_dir / "bundles" / BUNDLE_KINDS[kind] / name
        propagator._write_bundle(bundle_dir, payload, kind, name, entry.is_dir(),
                                 _content_hash(payload), context)
    else:
        raise ValueError(f"winner must be 'local' or 'repo', got {winner!r}")
```

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Commit** — `feat(config-sync): resolve_bundle for prompted conflict resolution (Refs #23)`

---

## Task 5: SnapshotPropagator — config-only export/apply, skip skills/agents

**Files:** Modify `scripts/config_sync_propagators.py`; Modify `tests/test_propagators.py`.

**Interfaces:**
- Consumes: `config_sync._collect_dir`, `_clean_settings`, `_merge_import_settings`, `_read`, `_write`, `_is_within`.
- Produces: `SnapshotPropagator` with `export`/`apply`; module constants `SNAPSHOT_CONFIG_FILES = ["CLAUDE.md", "settings.json", "keybindings.json"]`, `SNAPSHOT_CONFIG_DIRS = ["memory", "rules"]`.

- [ ] **Step 1: Failing tests**

```python
import config_sync


def test_snapshot_export_excludes_skills_and_agents(tmp_path):
    claude_dir = tmp_path / "c"; repo_dir = tmp_path / "r"
    (claude_dir / "rules").mkdir(parents=True)
    (claude_dir / "rules" / "style.md").write_text("be nice")
    (claude_dir / "skills" / "demo").mkdir(parents=True)
    (claude_dir / "skills" / "demo" / "SKILL.md").write_text("# demo")
    (claude_dir / "config-sync-machine-id").write_text("m1")
    context = propagators.SyncContext(claude_dir=claude_dir, repo_dir=repo_dir)

    propagators.SnapshotPropagator().export(context)

    snapshot = config_sync.json.loads((repo_dir / "machines" / "m1.json").read_text())
    assert "rules/style.md" in snapshot["files"]
    assert not any(key.startswith("skills/") for key in snapshot["files"])   # skills excluded


def test_snapshot_apply_writes_config_and_skips_skill_keys(tmp_path):
    claude_dir = tmp_path / "c"; repo_dir = tmp_path / "r"; claude_dir.mkdir()
    consolidated = repo_dir / "consolidated"; consolidated.mkdir(parents=True)
    consolidated.joinpath("snapshot.json").write_text(config_sync.json.dumps({"files": {
        "CLAUDE.md": "hello",
        "rules/style.md": "be nice",
        "skills/legacy/SKILL.md": "SHOULD BE SKIPPED",
    }}))
    context = propagators.SyncContext(claude_dir=claude_dir, repo_dir=repo_dir)

    result = propagators.SnapshotPropagator().apply(context)

    assert (claude_dir / "CLAUDE.md").read_text() == "hello"
    assert not (claude_dir / "skills" / "legacy" / "SKILL.md").exists()   # legacy skill key skipped
    assert "skills/legacy/SKILL.md" in result.skipped
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Implement**

```python
SNAPSHOT_CONFIG_FILES = ["CLAUDE.md", "settings.json", "keybindings.json"]
SNAPSHOT_CONFIG_DIRS = ["memory", "rules"]
_SKIP_APPLY_PREFIXES = ("skills/", "agents/")


class SnapshotPropagator:
    name = "snapshot"

    def export(self, context: SyncContext) -> ExportResult:
        import platform
        import config_sync
        files = {}
        for filename in SNAPSHOT_CONFIG_FILES:
            path = context.claude_dir / filename
            if not path.exists():
                continue
            if filename == "settings.json":
                files[filename] = config_sync.json.dumps(config_sync._clean_settings(config_sync._read(path)))
            else:
                files[filename] = config_sync._read(path)
        for directory in SNAPSHOT_CONFIG_DIRS:
            files.update(config_sync._collect_dir(context.claude_dir, directory))

        machine_id = _machine_id(context)
        snapshot = {
            "machine_id": machine_id, "hostname": platform.node(),
            "platform": platform.system(),
            "timestamp": datetime.now(timezone.utc).isoformat(), "files": files,
        }
        machines_dir = context.repo_dir / "machines"
        machines_dir.mkdir(parents=True, exist_ok=True)
        (machines_dir / f"{machine_id}.json").write_text(
            config_sync.json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
        return ExportResult(self.name, written=[f"machines/{machine_id}.json"])

    def apply(self, context: SyncContext) -> ApplyResult:
        import config_sync
        result = ApplyResult(self.name)
        consolidated = context.repo_dir / "consolidated" / "snapshot.json"
        if not consolidated.exists():
            return result
        files = config_sync.json.loads(consolidated.read_text(encoding="utf-8")).get("files", {})
        for relative_path, content in files.items():
            if relative_path.startswith(_SKIP_APPLY_PREFIXES):
                result.skipped.append(relative_path)
                continue
            destination = context.claude_dir / relative_path
            if not config_sync._is_within(destination, context.claude_dir):
                result.skipped.append(relative_path)
                continue
            if relative_path == "settings.json":
                incoming = config_sync.json.loads(content) if content.strip() else {}
                local_raw = config_sync._read(destination)
                existing = config_sync.json.loads(local_raw) if local_raw.strip() else {}
                merged = config_sync.json.dumps(
                    config_sync._merge_import_settings(incoming, existing), indent=2, ensure_ascii=False)
                if local_raw == merged:
                    result.skipped.append(relative_path); continue
                config_sync._write(destination, merged); result.applied.append(relative_path); continue
            if config_sync._read(destination) == content:
                result.skipped.append(relative_path); continue
            config_sync._write(destination, content); result.applied.append(relative_path)
        return result
```

- [ ] **Step 4: Run — expect PASS.** Add `default_propagators()` returning `[SnapshotPropagator(), ContentBundlePropagator()]` and a test asserting both names appear from `run_export`.

- [ ] **Step 5: Commit** — `feat(config-sync): SnapshotPropagator — config-only, skips skills/agents (Refs #25, Refs #26)`

---

## Task 6: CLI wiring — propagate-export / propagate-apply / resolve-bundle

**Files:** Modify `scripts/config_sync.py`.

**Interfaces:**
- Consumes: `config_sync_propagators.{SyncContext, run_export, run_apply, resolve_bundle, default_propagators}`.
- Produces: `cmd_propagate_export(repo)`, `cmd_propagate_apply(repo)`, `cmd_resolve_bundle(repo, kind, name, winner)`; `COMMANDS` entries.

- [ ] **Step 1: Failing test** (`tests/test_propagate_cli.py`) — uses the existing `claude_home` fixture so `CLAUDE_DIR` is isolated:

```python
import config_sync


def test_propagate_export_writes_snapshot_and_bundles(claude_home, tmp_path, capsys):
    (claude_home / "CLAUDE.md").write_text("hi")
    (claude_home / "skills" / "demo").mkdir(parents=True)
    (claude_home / "skills" / "demo" / "SKILL.md").write_text("# d")
    repo = tmp_path / "repo"; repo.mkdir()

    config_sync.cmd_propagate_export(str(repo))
    capsys.readouterr()

    assert list((repo / "machines").glob("*.json"))
    assert (repo / "bundles" / "skills" / "demo" / "SKILL.md").read_text() == "# d"
```

- [ ] **Step 2: Run — expect FAIL** (`cmd_propagate_export` undefined).

- [ ] **Step 3: Implement** in `config_sync.py` (near the other commands). Import lazily to keep the module load cheap and avoid a hard import cycle:

```python
def _sync_context(repo_path):
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    import config_sync_propagators as propagators
    return propagators, propagators.SyncContext(claude_dir=CLAUDE_DIR, repo_dir=Path(repo_path))


def cmd_propagate_export(repo_path):
    propagators, context = _sync_context(repo_path)
    results = propagators.run_export(context, propagators.default_propagators())
    print(json.dumps({result.propagator: {"written": result.written, "skipped": result.skipped}
                      for result in results}, indent=2))


def cmd_propagate_apply(repo_path):
    propagators, context = _sync_context(repo_path)
    results = propagators.run_apply(context, propagators.default_propagators())
    payload = {}
    for result in results:
        payload[result.propagator] = {
            "applied": result.applied, "skipped": result.skipped,
            "conflicts": [vars(conflict) for conflict in result.conflicts],
        }
    print(json.dumps(payload, indent=2))


def cmd_resolve_bundle(repo_path, kind, name, winner):
    propagators, context = _sync_context(repo_path)
    propagators.resolve_bundle(context, kind, name, winner)
    print(json.dumps({"resolved": f"{kind}/{name}", "winner": winner}))
```

Register:

```python
    "propagate-export": (cmd_propagate_export, 1),
    "propagate-apply": (cmd_propagate_apply, 1),
    "resolve-bundle": (cmd_resolve_bundle, 4),
```

- [ ] **Step 4: Run — expect PASS** (full suite too).

- [ ] **Step 5: Commit** — `feat(config-sync): CLI wrappers propagate-export/apply + resolve-bundle (Refs #26)`

---

## Task 7: SKILL orchestration — wire the seam, retire the heredoc (SK1)

**Files:** Modify `skills/config-sync/SKILL.md`; Modify `skills/config-sync-manage/SKILL.md`.

- [ ] **Step 1: Step 1 export.** Replace the plugin-export heredoc (the `python3 - "$REPO" <<'PYEOF' … PYEOF` block) **and** the standalone `export > machines/$MACHINE_ID.json` with:

```bash
# Export local config snapshot + skill/agent bundles through the propagator seam
python3 "$ENGINE" propagate-export "$REPO"
```

Keep the preceding `reconcile` call. `git add machines/ bundles/` in the commit step (replace `shared/plugins/`).

- [ ] **Step 2: Step 4 apply.** Replace the standalone `import "$CONSOLIDATED"` with:

```bash
BACKUP_PATH=$(python3 "$ENGINE" backup); echo "Backup saved: $BACKUP_PATH"
APPLY=$(python3 "$ENGINE" propagate-apply "$REPO"); echo "$APPLY"
```

Then document: parse `$APPLY`; for each entry in `content-bundle.conflicts`, use **AskUserQuestion** ("Skill/agent `<name>` differs between this machine and the network — keep local or take network?") and run:

```bash
python3 "$ENGINE" resolve-bundle "$REPO" "<kind>" "<name>" "<local|repo>"
```

- [ ] **Step 3: Step 4b.** Narrow `apply-shared` to plugins/legacy only (skills/agents now flow through `propagate-apply`); update the surrounding prose. Update the Step 7 summary to report bundle applies + conflicts.

- [ ] **Step 4: manage + versions.** In `config-sync-manage` Share, note skills/agents auto-propagate (share is plugin-only until C2). Bump `config-sync` version `0.5.0`→`0.6.0`.

- [ ] **Step 5: Verify + Commit.** `.venv/bin/python -m pytest tests/ -q`; `grep -n 'PYEOF\|export > ' skills/config-sync/SKILL.md` returns nothing. Commit — `feat(config-sync): wire propagator seam into the sync skill; retire export heredoc (Fixes #26, Fixes #23, Fixes #24, Fixes #16, Fixes #25)`

---

## Verification (end-to-end)

- **Unit:** `.venv/bin/python -m pytest tests/ -q` — all green (existing 21 + new propagator tests).
- **PS2 proof (isolated $HOME):**
  ```bash
  PY314="$(pyenv root)/versions/3.14.6/bin/python3"
  TMPHOME=$(mktemp -d); mkdir -p "$TMPHOME/.claude/skills/demo/scripts"
  echo "# demo" > "$TMPHOME/.claude/skills/demo/SKILL.md"
  echo "print(1)" > "$TMPHOME/.claude/skills/demo/scripts/engine.py"
  REPO=$(mktemp -d)
  HOME="$TMPHOME" "$PY314" scripts/config_sync.py propagate-export "$REPO"
  test -f "$REPO/bundles/skills/demo/scripts/engine.py" && echo "PS2 FIXED: non-.md asset travelled"
  ```
- **PS3 proof:** re-run `propagate-export` unchanged → `demo` in `skipped`; edit `SKILL.md`; re-run → `demo` in `written`.
- **Apply/conflict:** into a second throwaway `$HOME`, `propagate-apply` installs all files; pre-seed a divergent local `demo`, re-run → a `content-bundle.conflicts` entry, local untouched; `resolve-bundle … repo` overwrites.
- **SK1 check:** `grep -rn 'PYEOF' skills/config-sync/SKILL.md` → nothing.
```
