# Bundle deletion propagation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make deleting a skill/agent on one machine propagate to the others — behind a per-machine consent prompt — instead of leaving a stale bundle that gets resurrected.

**Architecture:** A new stateless `BundleDeletionLedger` (per-machine export index + per-bundle tombstones + a timestamp winner-rule), injected into `ContentBundlePropagator` via its constructor (like the existing `export_filter`). Export detects deletions (diff current-vs-index → tombstone + prune repo bundle); apply skips resurrection and *proposes* deletions in `ApplyResult`; a consent-gated `resolve-deletion` command performs the local removal. Snapshot config stays union-only.

**Tech Stack:** Python 3.14 stdlib only (`json`, `pathlib`, `shutil`, `dataclasses`, `datetime`); pytest.

## Global Constraints

- **Branch:** all work on `fix/bundle-deletion-propagation` (already created off `main`). Never commit to `main`.
- **Python:** stdlib only — no pip installs. Engine files import nothing third-party.
- **Test command:** `python3 -m pytest -q` (from repo root). If bare `python3` lacks pytest, use `~/.pyenv/versions/3.14.6/bin/python3 -m pytest -q` — this repo runs on pyenv 3.14.6.
- **DIP:** the ledger is injected into `ContentBundlePropagator.__init__` (default = production `BundleDeletionLedger()`); its methods take `repo_dir: Path` per call. No module globals.
- **Timestamps:** ISO-8601 UTC strings (`datetime.now(timezone.utc).isoformat()`), compared lexicographically (they sort correctly) — matching the snapshot consolidation.
- **Storage layout:** per-machine index at `bundles/.index/<machine_id>.json`; tombstones at `bundles/.tombstones/<skills|agents>/<name>.json`. These dot-dirs are siblings of `bundles/skills` & `bundles/agents`, so the existing `bundles/<subdir>/*` iterators never treat them as bundles.
- **`BUNDLE_KINDS`** (existing, in `config_sync_propagators.py`): `{"skill": "skills", "agent": "agents"}`.
- **Consent:** the destructive step is `resolve-deletion … remove`; `apply` only proposes, never removes.
- **Naming:** descriptive names; no single-letter/abbreviated variables, including comprehensions.
- **Commits:** Conventional Commits; body ends with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

## File Structure

**Modify:**
- `scripts/config_sync_propagators.py` — add `Tombstone`, `BundleDeletion`, `BundleDeletionLedger`; add `tombstoned` to `ExportResult`, `deletions` to `ApplyResult`; inject the ledger into `ContentBundlePropagator`; extend `export`/`apply`; add `resolve_deletion`.
- `scripts/config_sync.py` — `cmd_propagate_export` (emit `tombstoned`), `cmd_propagate_apply` (emit `deletions`), new `cmd_resolve_deletion` + dispatch entry.
- `skills/config-sync/SKILL.md` — Step 4 deletion-consent sub-step; update the "Deletions don't propagate" callout; Step 1/7 summary lines.
- `.claude-plugin/plugin.json`, `pyproject.toml`, `.claude-plugin/marketplace.json` — version 0.10.0 → 0.11.0.
- `README.md` — one line in the config-sync section.

**Create:**
- `tests/test_bundle_deletion.py` — ledger unit tests + export/apply/resolve deletion tests + a two-machine round-trip.
- (extend) `tests/test_propagate_cli.py` — `resolve-deletion` dispatch + new output fields.

---

## Task 1: BundleDeletionLedger + tombstone dataclasses

**Files:**
- Modify: `scripts/config_sync_propagators.py`
- Test: `tests/test_bundle_deletion.py`

**Interfaces:**
- Produces: `Tombstone(kind, name, deleted_at, machine_id)` and `BundleDeletion(kind, name, machine_id, deleted_at)` (frozen dataclasses); `BundleDeletionLedger` with methods `previously_exported(repo_dir, machine_id) -> set[str]`, `record_export(repo_dir, machine_id, current: set[str]) -> None`, `tombstone(repo_dir, kind, name, machine_id, when: str) -> None`, `clear_tombstone(repo_dir, kind, name) -> None`, `tombstone_for(repo_dir, kind, name) -> Tombstone | None`, `tombstones(repo_dir) -> list[Tombstone]`, `is_deleted(repo_dir, kind, name, bundle_exported_at: str) -> bool`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bundle_deletion.py`:

```python
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import config_sync_propagators as propagators  # noqa: E402


def _iso(text):
    # Small helper so tests read clearly; any ISO-8601 UTC string works.
    return text


def test_previously_exported_is_empty_without_index(tmp_path):
    ledger = propagators.BundleDeletionLedger()
    assert ledger.previously_exported(tmp_path, "machine-a") == set()


def test_record_export_round_trips(tmp_path):
    ledger = propagators.BundleDeletionLedger()
    ledger.record_export(tmp_path, "machine-a", {"skill/foo", "agent/bar"})
    assert ledger.previously_exported(tmp_path, "machine-a") == {"skill/foo", "agent/bar"}


def test_tombstone_write_read_and_clear(tmp_path):
    ledger = propagators.BundleDeletionLedger()
    ledger.tombstone(tmp_path, "skill", "gof", "machine-a", "2026-07-08T00:00:00+00:00")
    tombstone = ledger.tombstone_for(tmp_path, "skill", "gof")
    assert tombstone is not None
    assert tombstone.kind == "skill" and tombstone.name == "gof"
    assert tombstone.machine_id == "machine-a"
    assert [entry.name for entry in ledger.tombstones(tmp_path)] == ["gof"]
    ledger.clear_tombstone(tmp_path, "skill", "gof")
    assert ledger.tombstone_for(tmp_path, "skill", "gof") is None
    assert ledger.tombstones(tmp_path) == []


def test_is_deleted_compares_timestamps(tmp_path):
    ledger = propagators.BundleDeletionLedger()
    ledger.tombstone(tmp_path, "skill", "gof", "machine-a", "2026-07-08T12:00:00+00:00")
    # tombstone newer than the bundle export -> deleted wins
    assert ledger.is_deleted(tmp_path, "skill", "gof", "2026-07-08T11:00:00+00:00") is True
    # bundle re-exported after the tombstone -> not deleted
    assert ledger.is_deleted(tmp_path, "skill", "gof", "2026-07-08T13:00:00+00:00") is False
    # equal timestamps -> not deleted (strict >)
    assert ledger.is_deleted(tmp_path, "skill", "gof", "2026-07-08T12:00:00+00:00") is False
    # missing bundle export ("") -> tombstone wins
    assert ledger.is_deleted(tmp_path, "skill", "gof", "") is True
    # no tombstone -> not deleted
    assert ledger.is_deleted(tmp_path, "agent", "none", "") is False


def test_tombstone_rejects_name_with_separator(tmp_path):
    import pytest
    ledger = propagators.BundleDeletionLedger()
    with pytest.raises(ValueError):
        ledger.tombstone(tmp_path, "skill", "a/b", "machine-a", "2026-07-08T00:00:00+00:00")
```

- [ ] **Step 2: Run to verify they fail**

Run: `~/.pyenv/versions/3.14.6/bin/python3 -m pytest tests/test_bundle_deletion.py -q`
Expected: FAIL — `AttributeError: module 'config_sync_propagators' has no attribute 'BundleDeletionLedger'`.

- [ ] **Step 3: Implement the ledger**

In `scripts/config_sync_propagators.py`, after the `_read_manifest` helper (before `class ContentBundlePropagator`), add:

```python
INDEX_DIRNAME = ".index"
TOMBSTONES_DIRNAME = ".tombstones"


@dataclass(frozen=True)
class Tombstone:
    kind: str
    name: str
    deleted_at: str
    machine_id: str


@dataclass(frozen=True)
class BundleDeletion:
    kind: str
    name: str
    machine_id: str
    deleted_at: str


class BundleDeletionLedger:
    """Deletion bookkeeping for skill/agent bundles, persisted under the repo.

    Two records, both git-tracked and per-file so they converge without merge
    conflicts (the pattern machines/<id>.json already uses):
      - a per-machine export index (what a machine had at its last export), which
        makes deletion *detection* possible;
      - per-bundle tombstones ({kind, name, deleted_at, machine_id}).
    Stateless w.r.t. the repo: repo_dir flows in per call, so one instance serves
    any repo and is trivially faked in tests. One reason to change: the on-disk
    layout of these records.
    """

    def _index_path(self, repo_dir, machine_id):
        return repo_dir / "bundles" / INDEX_DIRNAME / f"{machine_id}.json"

    def _tombstone_path(self, repo_dir, kind, name):
        if "/" in name or "/" in kind:
            raise ValueError(f"bundle kind/name must not contain '/': {kind}/{name}")
        return repo_dir / "bundles" / TOMBSTONES_DIRNAME / BUNDLE_KINDS[kind] / f"{name}.json"

    def previously_exported(self, repo_dir, machine_id):
        index_path = self._index_path(repo_dir, machine_id)
        if not index_path.exists():
            return set()
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return set()
        return set(data.get("bundles", []))

    def record_export(self, repo_dir, machine_id, current):
        index_path = self._index_path(repo_dir, machine_id)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "machine_id": machine_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "bundles": sorted(current),
        }
        index_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def tombstone(self, repo_dir, kind, name, machine_id, when):
        tombstone_path = self._tombstone_path(repo_dir, kind, name)
        tombstone_path.parent.mkdir(parents=True, exist_ok=True)
        record = {"kind": kind, "name": name, "deleted_at": when, "machine_id": machine_id}
        tombstone_path.write_text(json.dumps(record, indent=2), encoding="utf-8")

    def clear_tombstone(self, repo_dir, kind, name):
        tombstone_path = self._tombstone_path(repo_dir, kind, name)
        if tombstone_path.exists():
            tombstone_path.unlink()

    def tombstone_for(self, repo_dir, kind, name):
        tombstone_path = self._tombstone_path(repo_dir, kind, name)
        if not tombstone_path.exists():
            return None
        data = json.loads(tombstone_path.read_text(encoding="utf-8"))
        return Tombstone(kind=data["kind"], name=data["name"],
                         deleted_at=data["deleted_at"], machine_id=data["machine_id"])

    def tombstones(self, repo_dir):
        root = repo_dir / "bundles" / TOMBSTONES_DIRNAME
        collected = []
        if not root.exists():
            return collected
        for kind, subdir in BUNDLE_KINDS.items():
            subdir_path = root / subdir
            if not subdir_path.exists():
                continue
            for tombstone_file in sorted(subdir_path.glob("*.json")):
                data = json.loads(tombstone_file.read_text(encoding="utf-8"))
                collected.append(Tombstone(kind=data["kind"], name=data["name"],
                                           deleted_at=data["deleted_at"], machine_id=data["machine_id"]))
        return collected

    def is_deleted(self, repo_dir, kind, name, bundle_exported_at):
        tombstone = self.tombstone_for(repo_dir, kind, name)
        if tombstone is None:
            return False
        return tombstone.deleted_at > (bundle_exported_at or "")
```

(`dataclass`, `field`, `json`, `datetime`, `timezone`, `Path` are already imported at the top of the file.)

- [ ] **Step 4: Run to verify pass**

Run: `~/.pyenv/versions/3.14.6/bin/python3 -m pytest tests/test_bundle_deletion.py -q`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/config_sync_propagators.py tests/test_bundle_deletion.py
git commit -m "feat(config-sync): BundleDeletionLedger — per-machine index + tombstones

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Export detects & records deletions

**Files:**
- Modify: `scripts/config_sync_propagators.py` (`ExportResult`, `ContentBundlePropagator.__init__` + `.export`)
- Test: `tests/test_bundle_deletion.py`

**Interfaces:**
- Consumes: `BundleDeletionLedger` (Task 1).
- Produces: `ExportResult.tombstoned: list[str]`; `ContentBundlePropagator(export_filter=None, ledger=None)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bundle_deletion.py`:

```python
def _write_skill(claude_dir, name, files):
    skill_dir = claude_dir / "skills" / name
    for relative_path, content in files.items():
        target = skill_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return skill_dir


def _context(tmp_path):
    claude_dir = tmp_path / "claude"
    repo_dir = tmp_path / "repo"
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "config-sync-machine-id").write_text("machine-a")
    return propagators.SyncContext(claude_dir=claude_dir, repo_dir=repo_dir)


def test_export_tombstones_and_prunes_a_deleted_skill(tmp_path):
    context = _context(tmp_path)
    skill_dir = _write_skill(context.claude_dir, "gof", {"SKILL.md": "# gof"})
    bundle_propagator = propagators.ContentBundlePropagator()

    bundle_propagator.export(context)  # first export: records index, writes bundle
    assert (context.repo_dir / "bundles" / "skills" / "gof").exists()

    import shutil
    shutil.rmtree(skill_dir)  # user deletes the skill locally
    result = bundle_propagator.export(context)  # second export: should detect deletion

    assert "skill/gof" in result.tombstoned
    assert not (context.repo_dir / "bundles" / "skills" / "gof").exists()  # bundle pruned
    assert propagators.BundleDeletionLedger().tombstone_for(context.repo_dir, "skill", "gof") is not None


def test_export_reexport_supersedes_tombstone(tmp_path):
    context = _context(tmp_path)
    ledger = propagators.BundleDeletionLedger()
    ledger.tombstone(context.repo_dir, "skill", "gof", "machine-b", "2000-01-01T00:00:00+00:00")
    _write_skill(context.claude_dir, "gof", {"SKILL.md": "# gof back"})

    propagators.ContentBundlePropagator().export(context)

    assert ledger.tombstone_for(context.repo_dir, "skill", "gof") is None  # re-add cleared it
    assert (context.repo_dir / "bundles" / "skills" / "gof").exists()


def test_first_export_tombstones_nothing(tmp_path):
    context = _context(tmp_path)
    _write_skill(context.claude_dir, "keep", {"SKILL.md": "# keep"})
    result = propagators.ContentBundlePropagator().export(context)
    assert result.tombstoned == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `~/.pyenv/versions/3.14.6/bin/python3 -m pytest tests/test_bundle_deletion.py -q -k "export"`
Expected: FAIL — `AttributeError: 'ExportResult' object has no attribute 'tombstoned'` (and the deletion isn't detected).

- [ ] **Step 3: Add the `tombstoned` field**

In `scripts/config_sync_propagators.py`, extend `ExportResult`:

```python
@dataclass
class ExportResult:
    propagator: str
    written: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    tombstoned: list = field(default_factory=list)
```

- [ ] **Step 4: Inject the ledger and extend `export`**

Replace `ContentBundlePropagator.__init__` and `.export` with:

```python
    def __init__(self, export_filter=None, ledger=None):
        # DIP: both the exclusion policy and the deletion ledger are injected
        # collaborators. Defaults are the production implementations; the
        # constructor is the seam tests substitute through.
        self._export_filter = export_filter if export_filter is not None else DefaultBundleExportFilter()
        self._ledger = ledger if ledger is not None else BundleDeletionLedger()

    def export(self, context: SyncContext) -> ExportResult:
        result = ExportResult(self.name)
        machine_id = _machine_id(context)
        current = {f"{kind}/{entry.name}" for kind, entry in self._sources(context)}
        previously_exported = self._ledger.previously_exported(context.repo_dir, machine_id)
        deleted_at = datetime.now(timezone.utc).isoformat()

        # Deletions: bundles this machine used to have and no longer does.
        import shutil
        for deleted_key in sorted(previously_exported - current):
            deleted_kind, deleted_name = deleted_key.split("/", 1)
            self._ledger.tombstone(context.repo_dir, deleted_kind, deleted_name, machine_id, deleted_at)
            stale_bundle = context.repo_dir / "bundles" / BUNDLE_KINDS[deleted_kind] / deleted_name
            if stale_bundle.exists():
                shutil.rmtree(stale_bundle)
            result.tombstoned.append(deleted_key)

        for kind, entry in self._sources(context):
            name = entry.name
            # A locally-present bundle supersedes any tombstone for it (deliberate re-add).
            if self._ledger.tombstone_for(context.repo_dir, kind, name) is not None:
                self._ledger.clear_tombstone(context.repo_dir, kind, name)
            payload = _payload_files(entry, self._export_filter)
            local_hash = _content_hash(payload)
            bundle_dir = context.repo_dir / "bundles" / BUNDLE_KINDS[kind] / name
            if _read_manifest(bundle_dir).get("content_hash") == local_hash:
                result.skipped.append(f"{kind}/{name}")
                continue
            self._write_bundle(bundle_dir, payload, kind, name, entry.is_dir(), local_hash, context)
            result.written.append(f"{kind}/{name}")

        self._ledger.record_export(context.repo_dir, machine_id, current)
        return result
```

- [ ] **Step 5: Run to verify pass**

Run: `~/.pyenv/versions/3.14.6/bin/python3 -m pytest tests/test_bundle_deletion.py -q`
Expected: 8 passed. Then the full propagator suite for regressions:
Run: `~/.pyenv/versions/3.14.6/bin/python3 -m pytest tests/test_propagators.py -q`
Expected: all pass (existing export tests unaffected — the new steps are additive; a first export on a fresh repo tombstones nothing).

- [ ] **Step 6: Commit**

```bash
git add scripts/config_sync_propagators.py tests/test_bundle_deletion.py
git commit -m "feat(config-sync): export detects deletions -> tombstone + prune bundle

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Apply skips resurrection & proposes deletions

**Files:**
- Modify: `scripts/config_sync_propagators.py` (`ApplyResult`, `ContentBundlePropagator.apply`)
- Test: `tests/test_bundle_deletion.py`

**Interfaces:**
- Consumes: `BundleDeletionLedger`, `BundleDeletion` (Task 1).
- Produces: `ApplyResult.deletions: list[BundleDeletion]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bundle_deletion.py`:

```python
def test_apply_does_not_resurrect_a_tombstoned_bundle(tmp_path):
    context = _context(tmp_path)
    # A repo bundle exists but a newer tombstone retires it; skill is absent locally.
    bundle_dir = context.repo_dir / "bundles" / "skills" / "gof"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "SKILL.md").write_text("# gof")
    (bundle_dir / propagators.MANIFEST_NAME).write_text(
        '{"name":"gof","kind":"skill","is_dir":true,"content_hash":"x","exported_at":"2000-01-01T00:00:00+00:00"}')
    propagators.BundleDeletionLedger().tombstone(
        context.repo_dir, "skill", "gof", "machine-b", "2026-07-08T00:00:00+00:00")

    result = propagators.ContentBundlePropagator().apply(context)

    assert not (context.claude_dir / "skills" / "gof").exists()  # not resurrected
    assert "skill/gof" not in result.applied


def test_apply_proposes_deletion_for_locally_present_tombstoned_skill(tmp_path):
    context = _context(tmp_path)
    _write_skill(context.claude_dir, "gof", {"SKILL.md": "# gof"})  # still present locally
    propagators.BundleDeletionLedger().tombstone(
        context.repo_dir, "skill", "gof", "machine-b", "2026-07-08T00:00:00+00:00")

    result = propagators.ContentBundlePropagator().apply(context)

    assert [(deletion.kind, deletion.name, deletion.machine_id) for deletion in result.deletions] \
        == [("skill", "gof", "machine-b")]
    assert (context.claude_dir / "skills" / "gof").exists()  # apply removed nothing
```

- [ ] **Step 2: Run to verify they fail**

Run: `~/.pyenv/versions/3.14.6/bin/python3 -m pytest tests/test_bundle_deletion.py -q -k "apply"`
Expected: FAIL — resurrection still happens / `ApplyResult` has no `deletions`.

- [ ] **Step 3: Add the `deletions` field**

Extend `ApplyResult`:

```python
@dataclass
class ApplyResult:
    propagator: str
    applied: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    deletions: list = field(default_factory=list)
```

- [ ] **Step 4: Extend `apply` — guard resurrection + propose deletions**

In `ContentBundlePropagator.apply`, inside the bundle loop, replace the `if not destination.exists():` block with a tombstone-guarded version, and add a proposal pass before `return result`:

```python
                if not destination.exists():
                    if self._ledger.is_deleted(context.repo_dir, kind, name, manifest.get("exported_at", "")):
                        result.skipped.append(f"{kind}/{name} (tombstoned)")
                        continue
                    self._install(bundle_dir, destination, manifest)
                    result.applied.append(f"{kind}/{name}")
                    continue
```

Then, immediately before `return result` at the end of `apply`, add:

```python
        # Propose local removals for bundles the network has retired but this
        # machine still has. Nothing is removed here — resolve-deletion does that
        # after consent.
        for tombstone in self._ledger.tombstones(context.repo_dir):
            destination = self._local_entry_path(context, tombstone.kind, tombstone.name, True)
            if not destination.exists():
                continue
            repo_bundle = context.repo_dir / "bundles" / BUNDLE_KINDS[tombstone.kind] / tombstone.name
            bundle_exported_at = _read_manifest(repo_bundle).get("exported_at", "")
            if self._ledger.is_deleted(context.repo_dir, tombstone.kind, tombstone.name, bundle_exported_at):
                result.deletions.append(BundleDeletion(
                    kind=tombstone.kind, name=tombstone.name,
                    machine_id=tombstone.machine_id, deleted_at=tombstone.deleted_at))
```

- [ ] **Step 5: Run to verify pass**

Run: `~/.pyenv/versions/3.14.6/bin/python3 -m pytest tests/test_bundle_deletion.py tests/test_propagators.py -q`
Expected: all pass (10 in test_bundle_deletion.py; existing propagator tests unaffected).

- [ ] **Step 6: Commit**

```bash
git add scripts/config_sync_propagators.py tests/test_bundle_deletion.py
git commit -m "feat(config-sync): apply skips tombstoned resurrection, proposes deletions

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: resolve_deletion + two-machine round-trip

**Files:**
- Modify: `scripts/config_sync_propagators.py` (add `resolve_deletion`)
- Test: `tests/test_bundle_deletion.py`

**Interfaces:**
- Produces: `resolve_deletion(context: SyncContext, kind: str, name: str, decision: str) -> None` (decision ∈ {"remove","keep"}).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bundle_deletion.py`:

```python
def test_resolve_deletion_remove_deletes_local_bundle(tmp_path):
    context = _context(tmp_path)
    _write_skill(context.claude_dir, "gof", {"SKILL.md": "# gof"})
    propagators.resolve_deletion(context, "skill", "gof", "remove")
    assert not (context.claude_dir / "skills" / "gof").exists()


def test_resolve_deletion_keep_leaves_local_bundle(tmp_path):
    context = _context(tmp_path)
    _write_skill(context.claude_dir, "gof", {"SKILL.md": "# gof"})
    propagators.resolve_deletion(context, "skill", "gof", "keep")
    assert (context.claude_dir / "skills" / "gof").exists()


def test_resolve_deletion_rejects_unknown_decision(tmp_path):
    import pytest
    context = _context(tmp_path)
    with pytest.raises(ValueError):
        propagators.resolve_deletion(context, "skill", "gof", "maybe")


def test_two_machine_round_trip(tmp_path):
    # Shared repo; machine A deletes a skill, machine B applies + consents to remove.
    repo_dir = tmp_path / "repo"
    machine_a = tmp_path / "a"
    machine_b = tmp_path / "b"
    for home, machine_id in [(machine_a, "machine-a"), (machine_b, "machine-b")]:
        home.mkdir(parents=True)
        (home / "config-sync-machine-id").write_text(machine_id)

    context_a = propagators.SyncContext(claude_dir=machine_a, repo_dir=repo_dir)
    context_b = propagators.SyncContext(claude_dir=machine_b, repo_dir=repo_dir)
    bundle_propagator = propagators.ContentBundlePropagator()

    # A creates gof and exports; B applies (installs gof).
    _write_skill(machine_a, "gof", {"SKILL.md": "# gof"})
    bundle_propagator.export(context_a)
    bundle_propagator.apply(context_b)
    assert (machine_b / "skills" / "gof").exists()

    # A deletes gof and re-exports -> tombstone + prune.
    import shutil
    shutil.rmtree(machine_a / "skills" / "gof")
    export_result = bundle_propagator.export(context_a)
    assert "skill/gof" in export_result.tombstoned

    # B applies -> proposes the deletion (does not remove); consent removes it.
    apply_result = bundle_propagator.apply(context_b)
    assert [deletion.name for deletion in apply_result.deletions] == ["gof"]
    assert (machine_b / "skills" / "gof").exists()  # still there until consent
    propagators.resolve_deletion(context_b, "skill", "gof", "remove")
    assert not (machine_b / "skills" / "gof").exists()  # gone after consent
```

- [ ] **Step 2: Run to verify they fail**

Run: `~/.pyenv/versions/3.14.6/bin/python3 -m pytest tests/test_bundle_deletion.py -q -k "resolve or round_trip"`
Expected: FAIL — `module 'config_sync_propagators' has no attribute 'resolve_deletion'`.

- [ ] **Step 3: Implement `resolve_deletion`**

In `scripts/config_sync_propagators.py`, after the existing `resolve_bundle` function, add:

```python
def resolve_deletion(context: SyncContext, kind: str, name: str, decision: str) -> None:
    """Perform a prompted bundle-deletion resolution.

    decision="remove" -> delete the local skill/agent (the network retired it). The
      repo tombstone stays so other machines also see the deletion.
    decision="keep"   -> leave it. Because the machine still has it, the next export
      re-adds the bundle and supersedes the tombstone (disagreement resolves as
      most-recent-action-wins).
    """
    if decision == "keep":
        return
    if decision != "remove":
        raise ValueError(f"decision must be 'remove' or 'keep', got {decision!r}")
    if kind not in BUNDLE_KINDS:
        raise ValueError(f"unknown bundle kind: {kind!r}")
    import shutil
    # Deferred import: config_sync <-> config_sync_propagators is a two-way dep (SOLID M2).
    import config_sync
    destination = context.claude_dir / BUNDLE_KINDS[kind] / name
    if not config_sync._is_within(destination, context.claude_dir):
        raise ValueError(f"refusing to remove a path escaping ~/.claude: {destination}")
    if destination.exists():
        shutil.rmtree(destination)
```

- [ ] **Step 4: Run to verify pass**

Run: `~/.pyenv/versions/3.14.6/bin/python3 -m pytest tests/test_bundle_deletion.py -q`
Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/config_sync_propagators.py tests/test_bundle_deletion.py
git commit -m "feat(config-sync): resolve-deletion (consent-gated local removal) + round-trip

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: CLI wiring

**Files:**
- Modify: `scripts/config_sync.py` (`cmd_propagate_export`, `cmd_propagate_apply`, new `cmd_resolve_deletion`, dispatch table)
- Test: `tests/test_propagate_cli.py`

**Interfaces:**
- Consumes: `resolve_deletion` (Task 4), `ExportResult.tombstoned` (Task 2), `ApplyResult.deletions` (Task 3).
- Produces: CLI command `resolve-deletion <repo> <kind> <name> <remove|keep>`; `content-bundle` export output gains `tombstoned`; apply output gains `deletions`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_propagate_cli.py`. It already imports `config_sync` and uses the
`claude_home` fixture (from `tests/conftest.py`), which monkeypatches
`config_sync.CLAUDE_DIR` to a throwaway dir — so `_sync_context` (which reads
`CLAUDE_DIR`) builds its context against `claude_home`. Use that, matching the
existing `test_propagate_export_writes_snapshot_and_bundles`:

```python
def test_resolve_deletion_is_registered_with_four_args():
    handler, arg_count = config_sync.COMMANDS["resolve-deletion"]
    assert arg_count == 4
    assert handler.__name__ == "cmd_resolve_deletion"


def test_cmd_resolve_deletion_removes_local_bundle(claude_home, tmp_path, capsys):
    (claude_home / "skills" / "gof").mkdir(parents=True)
    (claude_home / "skills" / "gof" / "SKILL.md").write_text("# gof")
    repo = tmp_path / "repo"
    repo.mkdir()

    config_sync.cmd_resolve_deletion(str(repo), "skill", "gof", "remove")

    assert not (claude_home / "skills" / "gof").exists()
    assert '"resolved": "skill/gof"' in capsys.readouterr().out


def test_cmd_propagate_apply_reports_deletions(claude_home, tmp_path, capsys):
    import config_sync_propagators as propagators
    (claude_home / "skills" / "gof").mkdir(parents=True)
    (claude_home / "skills" / "gof" / "SKILL.md").write_text("# gof")
    (claude_home / "config-sync-machine-id").write_text("machine-a")
    repo = tmp_path / "repo"
    repo.mkdir()
    propagators.BundleDeletionLedger().tombstone(
        repo, "skill", "gof", "machine-b", "2026-07-08T00:00:00+00:00")

    config_sync.cmd_propagate_apply(str(repo))

    import json as json_module
    payload = json_module.loads(capsys.readouterr().out)
    assert payload["content-bundle"]["deletions"][0]["name"] == "gof"
```

- [ ] **Step 2: Run to verify it fails**

Run: `~/.pyenv/versions/3.14.6/bin/python3 -m pytest tests/test_propagate_cli.py -q -k "resolve_deletion"`
Expected: FAIL — `KeyError: 'resolve-deletion'` / `cmd_resolve_deletion` undefined.

- [ ] **Step 3: Extend the export/apply commands and add `cmd_resolve_deletion`**

In `scripts/config_sync.py`:

Extend `cmd_propagate_export`'s printed dict to include `tombstoned`:

```python
    print(json.dumps({result.propagator: {"written": result.written,
                                           "skipped": result.skipped,
                                           "warnings": result.warnings,
                                           "tombstoned": result.tombstoned}
                      for result in results}, indent=2))
```

Extend `cmd_propagate_apply`'s per-result payload to include `deletions`:

```python
        payload[result.propagator] = {
            "applied": result.applied,
            "skipped": result.skipped,
            "conflicts": [vars(conflict) for conflict in result.conflicts],
            "deletions": [vars(deletion) for deletion in result.deletions],
        }
```

Add the command function after `cmd_resolve_bundle`:

```python
def cmd_resolve_deletion(repo_path, kind, name, decision):
    propagators, context = _sync_context(repo_path)
    propagators.resolve_deletion(context, kind, name, decision)
    print(json.dumps({"resolved": f"{kind}/{name}", "decision": decision}))
```

Add the dispatch entry (in the `COMMANDS` dict, next to `"resolve-bundle"`):

```python
    "resolve-deletion": (cmd_resolve_deletion, 4),
```

> The dispatch dict is the one containing `"resolve-bundle": (cmd_resolve_bundle, 4)`. If it is not literally named `COMMANDS`, the registration test above must reference the actual name — grep `resolve-bundle` in `config_sync.py` to find it and use the same object.

- [ ] **Step 4: Run to verify pass**

Run: `~/.pyenv/versions/3.14.6/bin/python3 -m pytest tests/test_propagate_cli.py -q`
Expected: pass. Then the full suite:
Run: `~/.pyenv/versions/3.14.6/bin/python3 -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/config_sync.py tests/test_propagate_cli.py
git commit -m "feat(config-sync): CLI — resolve-deletion + tombstoned/deletions output

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Skill workflow + documentation

**Files:**
- Modify: `skills/config-sync/SKILL.md`

**Interfaces:**
- Consumes: the `content-bundle.deletions` apply output (Task 5), `resolve-deletion` command (Task 5), `tombstoned` export output (Task 5).

- [ ] **Step 1: Update the "Deletions don't propagate" callout (Step 3 of the skill)**

Find the blockquote beginning `> **Deletions don't propagate.**` and replace it with:

```markdown
> **Bundle deletions propagate; config deletions don't.** Skill/agent **bundles**
> now carry deletion tombstones: delete a skill on one machine and, on the next
> sync, other machines are *prompted* to remove it (Step 4). **Snapshot config**
> (CLAUDE.md, `memory/`, `rules/`) is still **union-only** — a memory or rule you
> delete on one machine is *resurrected* from another machine's snapshot. To remove
> config content everywhere: delete it on **every** machine **and** from
> `consolidated/snapshot.json` + each `machines/*.json`, then re-push.
```

- [ ] **Step 2: Add the deletion-consent sub-step in Step 4**

Immediately after the **"Resolve bundle conflicts (if any)."** block (the one ending with the `resolve-bundle` fenced command), add:

```markdown
**Resolve bundle deletions (if any).** For each entry in `content-bundle.deletions` —
a skill/agent the network retired that this machine still has — ask the user with
**AskUserQuestion** ("Skill/agent `<name>` was deleted on `<machine_id>` at
`<deleted_at>` — remove it here, or keep it?"), then apply their choice:

```bash
# decision is "remove" (delete this machine's copy) or "keep" (retain it; the next
# export re-adds it for everyone)
python3 "$ENGINE" resolve-deletion "$REPO" "<kind>" "<name>" "<decision>"
```
```

- [ ] **Step 3: Add summary lines**

In **Step 1**, after the marketplace-warnings block, add a line to the guidance:
"If `propagate-export` reported any `content-bundle.tombstoned` entries, tell the user which skills/agents were retired and will be proposed for removal on other machines."

In **Step 7**'s summary template, add a line under `Merged`:
```
  Retired  : <N> skill/agent bundle(s) tombstoned or removed (or "none")
```

- [ ] **Step 4: Verify no skill-shell-safety regressions**

Run: `~/.pyenv/versions/3.14.6/bin/python3 -m pytest tests/test_skill_shell_safety.py tests/test_skill_integrity.py -q`
Expected: pass (the SKILL.md edits introduce no `echo "$JSON"` and no dangling links).

- [ ] **Step 5: Commit**

```bash
git add skills/config-sync/SKILL.md
git commit -m "docs(config-sync): SKILL workflow — bundle-deletion consent step

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Version bump + README

**Files:**
- Modify: `.claude-plugin/plugin.json`, `pyproject.toml`, `.claude-plugin/marketplace.json`, `README.md`

- [ ] **Step 1: Bump the three version mirrors to `0.11.0`**

- `.claude-plugin/plugin.json`: `"version": "0.11.0"`.
- `pyproject.toml`: `version = "0.11.0"  # mirrors .claude-plugin/plugin.json (canonical source of truth)`.
- `.claude-plugin/marketplace.json`: `plugins[0].version` → `"0.11.0"`.

- [ ] **Step 2: Note the capability in README**

In `README.md`'s config-sync section, add one line: "Skill/agent **deletions** now propagate — a retired skill on one machine is proposed for removal on the others (consent-gated); snapshot config remains union-only."

- [ ] **Step 3: Run the full suite**

Run: `~/.pyenv/versions/3.14.6/bin/python3 -m pytest -q`
Expected: all pass — `test_version_mirrors_match` (from `tests/test_skill_integrity.py`) is green only when all three mirrors read `0.11.0`.

- [ ] **Step 4: Commit**

```bash
git add .claude-plugin/plugin.json pyproject.toml .claude-plugin/marketplace.json README.md
git commit -m "chore(config-sync): document bundle-deletion propagation; bump 0.10.0 -> 0.11.0

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage** (spec §→task): §3 ledger → T1; §4 export detection → T2; §5 apply proposal + resolve-deletion → T3, T4; §6 skill workflow/doc → T6; §7 tests → T1–T5 (+ round-trip in T4); §8 delivery/version → T7. The §9 open questions are resolved: tombstone filename safety → `_tombstone_path` raises on a `/` in the name (T1, tested); sync-log auditing of `tombstoned`/`deletions` → surfaced in the SKILL summary (T6), not persisted to `meta/sync-log.json` (kept out per YAGNI — the JSON output already carries it for the run).

**Placeholder scan:** all code steps carry complete code; the one soft spot — the CLI unit test's dependence on `_sync_context` reading globals — is handled explicitly with a `monkeypatch` fake and a note to fall back to the dispatch-registration test, not left as "figure it out."

**Type/name consistency:** `BundleDeletionLedger` method signatures (all take `repo_dir` first) are identical across T1 (definition), T2/T3 (propagator calls), and T4 (`is_deleted`). `ExportResult.tombstoned` / `ApplyResult.deletions` are defined in T2/T3 and consumed verbatim in T5. `resolve_deletion(context, kind, name, decision)` matches between T4 (def) and T5 (`cmd_resolve_deletion` call). `BUNDLE_KINDS` used consistently (`skill`/`agent` keys → `skills`/`agents` dirs). Version `0.11.0` applied to all three mirrors in T7 and enforced by `test_version_mirrors_match`.
