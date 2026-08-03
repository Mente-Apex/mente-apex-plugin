# Rejection Ledger Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Declining pulled snapshot content records a durable decision — scoped to this machine or to the whole network — so it is never re-proposed.

**Architecture:** A new `scripts/config_sync_rejections.py` holds a `RejectionPolicy` protocol with two storage implementations (a never-committed local file, a git-tracked per-machine file in the config repo), a single `TimestampedRejectionRule` deciding when a rejection still bites, and one `UnitAddressor` per rejectable kind. `cmd_consolidate` subtracts network rejections during its fold — including from the `base_files` seeded by the prior consolidated snapshot, which is the ratchet that makes content immortal — and `SnapshotPropagator.apply` subtracts local ones.

**Tech Stack:** Python 3, stdlib only (`json`, `hashlib`, `dataclasses`, `pathlib`, `datetime`), pytest, black, ruff.

## Global Constraints

- **No new runtime dependencies.** Stdlib only; the engine runs under `bin/mente-python`, which may resolve to a bare system interpreter.
- **Formatting is not hand-edited.** `uv run black .` owns whitespace; `uv run ruff check --fix .` must be clean before every commit.
- **Descriptive names throughout**, including in comprehensions and generator expressions — no single-letter or abbreviated loop variables.
- **Timestamps are UTC ISO 8601 strings** (`datetime.now(UTC).isoformat()`), matching every existing snapshot field. They are compared lexicographically; do not parse them.
- **Repo state is per-file and git-tracked**, following `machines/<id>.json` and `bundles/.index/<id>.json`, so two machines never write the same file.
- **Fail closed.** A corrupt ledger aborts with a named error; it never degrades to "no rejections".
- **Tests import from `scripts/` directly** (`import config_sync_rejections as rejections`) — `tests/conftest.py` already puts `scripts/` on `sys.path`.
- **Run the suite with** `uv run pytest tests/ -q` from the repo root.
- Branch: `feat/config-sync-rejection-ledger`. Commit after every task.

## File Structure

| File | Responsibility |
|---|---|
| `scripts/config_sync_rejections.py` (create) | Records, the policy protocol, the timestamp rule, both stores, the composite, snapshot addressors, and the snapshot filter function. |
| `tests/test_rejection_rule.py` (create) | The timestamp rule, including the equality boundary. |
| `tests/test_rejection_stores.py` (create) | One shared contract suite run against both stores, plus per-store specifics. |
| `tests/test_rejection_addressors.py` (create) | Section/file addressing and the section round-trip. |
| `tests/test_consolidate_rejections.py` (create) | The ratchet regression and scope isolation. |
| `tests/test_rejection_cli.py` (create) | Command surface end to end. |
| `scripts/config_sync.py` (modify) | Four new commands, `COMMANDS` entries, `cmd_consolidate` filtering, `main()` error handling. |
| `scripts/config_sync_propagators.py` (modify) | `SnapshotPropagator` policy injection, `rejection_removals` on `ApplyResult`. |
| `skills/config-sync/SKILL.md` (modify) | Step 4 reject branch, Step 4e removal prompts, Step 7 summary line. |

Phase 2 (`settings-key`, `hook-registration`, `plugin`) is a separate plan; nothing here may assume those kinds exist beyond leaving `REJECTION_KINDS` open for them.

---

### Task 1: Records and the timestamp rule

**Files:**
- Create: `scripts/config_sync_rejections.py`
- Test: `tests/test_rejection_rule.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `RejectionTarget(kind: str, address: str)`; `RejectionRecord(id, kind, address, scope, rejected_at, machine_id, reason="", tier="", revives=None)`; `rejection_id_of(kind: str, address: str) -> str`; `TimestampedRejectionRule.suppresses(record: RejectionRecord, source_timestamp: str) -> bool`; `REJECTION_KINDS: tuple[str, ...]`.

- [ ] **Step 1: Write the failing test**

```python
"""The rule that decides whether a rejection still bites.

A re-add must be STRICTLY newer than the rejection to count as fresh intent;
equal timestamps let the rejection win. That boundary is the whole rule, so it
is asserted directly rather than inferred from a higher-level behaviour.
"""

import config_sync_rejections as rejections
from config_sync_rejections import RejectionRecord, TimestampedRejectionRule


def _record(rejected_at):
    return RejectionRecord(
        id="abc123def456",
        kind="snapshot-section",
        address="CLAUDE.md",
        scope="network",
        rejected_at=rejected_at,
        machine_id="machine-a",
    )


def test_content_older_than_the_rejection_is_suppressed():
    rule = TimestampedRejectionRule()
    assert rule.suppresses(_record("2026-08-03T09:00:00+00:00"), "2026-08-03T08:00:00+00:00")


def test_content_strictly_newer_than_the_rejection_is_fresh_intent():
    rule = TimestampedRejectionRule()
    assert not rule.suppresses(_record("2026-08-03T09:00:00+00:00"), "2026-08-03T11:00:00+00:00")


def test_equal_timestamps_let_the_rejection_win():
    rule = TimestampedRejectionRule()
    same = "2026-08-03T09:00:00+00:00"
    assert rule.suppresses(_record(same), same)


def test_missing_source_timestamp_is_suppressed_rather_than_guessed():
    rule = TimestampedRejectionRule()
    assert rule.suppresses(_record("2026-08-03T09:00:00+00:00"), "")


def test_rejection_id_is_stable_over_kind_and_address_only():
    first = rejections.rejection_id_of("snapshot-file", "rules/a.md")
    second = rejections.rejection_id_of("snapshot-file", "rules/a.md")
    assert first == second
    assert first != rejections.rejection_id_of("snapshot-section", "rules/a.md")


def test_rejection_id_cannot_be_forged_across_the_field_boundary():
    assert rejections.rejection_id_of("ab", "c") != rejections.rejection_id_of("a", "bc")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rejection_rule.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'config_sync_rejections'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/config_sync_rejections.py`:

```python
"""Durable "I have seen this and I do not want it" decisions for pulled config.

DIP: consumers depend only on the RejectionPolicy protocol; concrete stores and
addressors are injected. See
docs/superpowers/specs/2026-08-03-config-sync-rejection-ledger-design.md.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

REJECTION_KINDS = (
    "snapshot-section",
    "snapshot-file",
    "settings-key",
    "hook-registration",
    "plugin",
)

REJECTION_SCOPES = ("local", "network")


@dataclass(frozen=True)
class RejectionTarget:
    """What a rejection points at. `address` is produced by the kind's addressor."""

    kind: str
    address: str


@dataclass(frozen=True)
class RejectionRecord:
    id: str
    kind: str
    address: str
    scope: str
    rejected_at: str
    machine_id: str
    reason: str = ""
    tier: str = ""
    revives: str | None = None


def rejection_id_of(kind: str, address: str) -> str:
    """Stable 12-hex identity over (kind, address) — deliberately NOT scope, so a
    target has at most one active record and cannot disagree with itself.

    Null-joined so no field boundary can be forged by another, matching
    `config_sync_hooks.hook_id_of`.
    """
    payload = "\0".join([kind, address]).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:12]


class TimestampedRejectionRule:
    """A rejection suppresses its target unless the content is strictly newer.

    Timestamps are UTC ISO 8601 and compare lexicographically, so no parsing is
    needed. Equality suppresses: a re-add must be strictly newer to read as fresh
    intent rather than as the same content arriving again.
    """

    def suppresses(self, record: RejectionRecord, source_timestamp: str) -> bool:
        if not source_timestamp:
            return True
        return source_timestamp <= record.rejected_at
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_rejection_rule.py -q`
Expected: 6 passed

- [ ] **Step 5: Format, lint, commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black scripts/config_sync_rejections.py tests/test_rejection_rule.py
uv run ruff check --fix scripts/config_sync_rejections.py tests/test_rejection_rule.py
uv run pytest tests/ -q
git add scripts/config_sync_rejections.py tests/test_rejection_rule.py
git commit -m "feat(config-sync): add rejection records and the timestamp rule"
```

---

### Task 2: Both stores behind one contract

**Files:**
- Modify: `scripts/config_sync_rejections.py`
- Test: `tests/test_rejection_stores.py`

**Interfaces:**
- Consumes: `RejectionRecord`, `rejection_id_of` from Task 1.
- Produces: `CorruptRejectionLedgerError(RuntimeError)`; `LocalRejectionStore(path: Path)` and `SharedRejectionStore(repo_dir: Path, machine_id: str)`, both exposing `scope: str`, `all() -> list[RejectionRecord]`, `record(record: RejectionRecord) -> None`, `forget(rejection_id: str) -> None`.

The two stores differ in a way that matters: the local one reads and writes a single file, while the shared one **reads every machine's file** and writes only its own. That is why they are two classes rather than one parameterised by path.

- [ ] **Step 1: Write the failing test**

```python
"""Both stores satisfy one contract; each has one behaviour the other cannot.

The contract suite is parameterised over both constructors, so substituting
either is proven rather than assumed (LSP).
"""

import json

import pytest

from config_sync_rejections import (
    CorruptRejectionLedgerError,
    LocalRejectionStore,
    RejectionRecord,
    SharedRejectionStore,
)


def _record(rejection_id="abc123def456", scope="local", rejected_at="2026-08-03T09:00:00+00:00"):
    return RejectionRecord(
        id=rejection_id,
        kind="snapshot-file",
        address="rules/a.md",
        scope=scope,
        rejected_at=rejected_at,
        machine_id="machine-a",
    )


def _local(tmp_path):
    return LocalRejectionStore(tmp_path / "config-sync-rejections.json")


def _shared(tmp_path):
    return SharedRejectionStore(tmp_path / "repo", "machine-a")


@pytest.fixture(params=[_local, _shared], ids=["local", "shared"])
def store(request, tmp_path):
    return request.param(tmp_path)


def test_absent_backing_file_reads_as_empty(store):
    assert store.all() == []


def test_recorded_rejection_round_trips(store):
    written = _record(scope=store.scope)
    store.record(written)
    assert store.all() == [written]


def test_recording_the_same_id_twice_replaces_rather_than_duplicates(store):
    store.record(_record(scope=store.scope, rejected_at="2026-08-03T09:00:00+00:00"))
    store.record(_record(scope=store.scope, rejected_at="2026-08-03T10:00:00+00:00"))
    assert [found.rejected_at for found in store.all()] == ["2026-08-03T10:00:00+00:00"]


def test_forget_removes_the_record(store):
    store.record(_record(scope=store.scope))
    store.forget("abc123def456")
    assert store.all() == []


def test_forgetting_an_unknown_id_is_a_no_op(store):
    store.record(_record(scope=store.scope))
    store.forget("notarealid00")
    assert len(store.all()) == 1


def test_corrupt_backing_file_fails_closed(store, tmp_path):
    store.record(_record(scope=store.scope))
    for corruptible in tmp_path.rglob("*.json"):
        corruptible.write_text("{not json", encoding="utf-8")
    with pytest.raises(CorruptRejectionLedgerError):
        store.all()


def test_shared_store_reads_every_machines_file(tmp_path):
    SharedRejectionStore(tmp_path / "repo", "machine-a").record(
        _record(rejection_id="aaaaaaaaaaaa", scope="network")
    )
    SharedRejectionStore(tmp_path / "repo", "machine-b").record(
        _record(rejection_id="bbbbbbbbbbbb", scope="network")
    )
    seen = SharedRejectionStore(tmp_path / "repo", "machine-a").all()
    assert {found.id for found in seen} == {"aaaaaaaaaaaa", "bbbbbbbbbbbb"}


def test_shared_store_writes_only_its_own_machine_file(tmp_path):
    SharedRejectionStore(tmp_path / "repo", "machine-a").record(_record(scope="network"))
    written = sorted(path.name for path in (tmp_path / "repo" / "rejections").glob("*.json"))
    assert written == ["machine-a.json"]


def test_shared_store_forget_leaves_another_machines_record_alone(tmp_path):
    SharedRejectionStore(tmp_path / "repo", "machine-b").record(
        _record(rejection_id="bbbbbbbbbbbb", scope="network")
    )
    SharedRejectionStore(tmp_path / "repo", "machine-a").forget("bbbbbbbbbbbb")
    assert len(SharedRejectionStore(tmp_path / "repo", "machine-a").all()) == 1


def test_local_store_payload_is_a_plain_list_of_records(tmp_path):
    store = _local(tmp_path)
    store.record(_record())
    payload = json.loads((tmp_path / "config-sync-rejections.json").read_text(encoding="utf-8"))
    assert payload["rejections"][0]["address"] == "rules/a.md"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rejection_stores.py -q`
Expected: FAIL with `ImportError: cannot import name 'CorruptRejectionLedgerError'`

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/config_sync_rejections.py` (and add `import json` plus `from pathlib import Path` to the imports at the top):

```python
class CorruptRejectionLedgerError(RuntimeError):
    """A rejection ledger on disk does not parse.

    Raised rather than swallowed: treating an unreadable ledger as "no
    rejections" would silently resurrect exactly the content the operator
    killed, which is the defect this module exists to prevent.
    """


def _record_from(payload: dict) -> RejectionRecord:
    return RejectionRecord(
        id=payload["id"],
        kind=payload["kind"],
        address=payload["address"],
        scope=payload["scope"],
        rejected_at=payload["rejected_at"],
        machine_id=payload["machine_id"],
        reason=payload.get("reason", ""),
        tier=payload.get("tier", ""),
        revives=payload.get("revives"),
    )


def _read_ledger(path: Path) -> list[RejectionRecord]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError) as exc:
        raise CorruptRejectionLedgerError(f"{path} does not parse: {exc}") from exc
    return [_record_from(entry) for entry in payload.get("rejections", [])]


def _write_ledger(path: Path, records: list[RejectionRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"rejections": [vars(record) for record in records]}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _replacing(records: list[RejectionRecord], incoming: RejectionRecord) -> list:
    kept = [record for record in records if record.id != incoming.id]
    kept.append(incoming)
    return kept


class LocalRejectionStore:
    """This machine's private vetoes. Never committed — a local preference that
    reached the shared repo would impose one machine's taste on the network."""

    scope = "local"

    def __init__(self, path: Path):
        self._path = Path(path)

    def all(self) -> list[RejectionRecord]:
        return _read_ledger(self._path)

    def record(self, record: RejectionRecord) -> None:
        _write_ledger(self._path, _replacing(self.all(), record))

    def forget(self, rejection_id: str) -> None:
        remaining = [found for found in self.all() if found.id != rejection_id]
        _write_ledger(self._path, remaining)


class SharedRejectionStore:
    """Network-wide tombstones. Reads every machine's file, writes only its own —
    the per-file pattern `machines/<id>.json` uses, so two machines never touch
    the same file and the state converges without merge conflicts."""

    scope = "network"

    def __init__(self, repo_dir: Path, machine_id: str):
        self._directory = Path(repo_dir) / "rejections"
        self._machine_id = machine_id

    @property
    def _own_path(self) -> Path:
        return self._directory / f"{self._machine_id}.json"

    def all(self) -> list[RejectionRecord]:
        if not self._directory.exists():
            return []
        found: list[RejectionRecord] = []
        for ledger_path in sorted(self._directory.glob("*.json")):
            found.extend(_read_ledger(ledger_path))
        return found

    def record(self, record: RejectionRecord) -> None:
        _write_ledger(self._own_path, _replacing(_read_ledger(self._own_path), record))

    def forget(self, rejection_id: str) -> None:
        remaining = [
            found for found in _read_ledger(self._own_path) if found.id != rejection_id
        ]
        _write_ledger(self._own_path, remaining)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_rejection_stores.py -q`
Expected: 16 passed (6 contract tests × 2 stores, plus 4 store-specific)

- [ ] **Step 5: Format, lint, commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black scripts/config_sync_rejections.py tests/test_rejection_stores.py
uv run ruff check --fix scripts/config_sync_rejections.py tests/test_rejection_stores.py
uv run pytest tests/ -q
git add scripts/config_sync_rejections.py tests/test_rejection_stores.py
git commit -m "feat(config-sync): add local and shared rejection stores behind one contract"
```

---

### Task 3: The composite policy and revival precedence

**Files:**
- Modify: `scripts/config_sync_rejections.py`
- Test: `tests/test_rejection_composite.py`

**Interfaces:**
- Consumes: `RejectionRecord`, `RejectionTarget`, `TimestampedRejectionRule`, both stores.
- Produces: `RejectionPolicy` (Protocol) with `is_rejected(target: RejectionTarget, source_timestamp: str) -> bool`, `record(record) -> None`, `forget(rejection_id: str) -> None`, `all() -> list[RejectionRecord]`; `NullRejectionPolicy`; `CompositeRejectionPolicy(stores: list, rule=None)`.

A revival is an ordinary `RejectionRecord` whose `revives` names the rejection it overrules. Machine A cannot write machine B's file, so "keep it" is expressed as A's own newer record rather than a deletion in B's.

- [ ] **Step 1: Write the failing test**

```python
"""Fanning a query across stores, and letting one machine overrule another."""

from config_sync_rejections import (
    CompositeRejectionPolicy,
    LocalRejectionStore,
    NullRejectionPolicy,
    RejectionRecord,
    RejectionTarget,
    SharedRejectionStore,
    rejection_id_of,
)

TARGET = RejectionTarget(kind="snapshot-file", address="rules/a.md")
TARGET_ID = rejection_id_of("snapshot-file", "rules/a.md")
OLD_CONTENT = "2026-08-03T08:00:00+00:00"


def _rejection(rejected_at, machine_id="machine-a", scope="network", revives=None, suffix=""):
    return RejectionRecord(
        id=(TARGET_ID + suffix) if revives else TARGET_ID,
        kind="snapshot-file",
        address="rules/a.md",
        scope=scope,
        rejected_at=rejected_at,
        machine_id=machine_id,
        revives=revives,
    )


def _policy(tmp_path):
    return CompositeRejectionPolicy(
        [
            LocalRejectionStore(tmp_path / "local.json"),
            SharedRejectionStore(tmp_path / "repo", "machine-a"),
        ]
    )


def test_null_policy_never_rejects():
    assert not NullRejectionPolicy().is_rejected(TARGET, OLD_CONTENT)


def test_unrecorded_target_is_not_rejected(tmp_path):
    assert not _policy(tmp_path).is_rejected(TARGET, OLD_CONTENT)


def test_a_rejection_in_either_store_suppresses(tmp_path):
    policy = _policy(tmp_path)
    policy.record(_rejection("2026-08-03T09:00:00+00:00", scope="local"))
    assert policy.is_rejected(TARGET, OLD_CONTENT)


def test_content_newer_than_the_rejection_survives(tmp_path):
    policy = _policy(tmp_path)
    policy.record(_rejection("2026-08-03T09:00:00+00:00", scope="local"))
    assert not policy.is_rejected(TARGET, "2026-08-03T11:00:00+00:00")


def test_a_newer_revival_un_suppresses(tmp_path):
    policy = _policy(tmp_path)
    SharedRejectionStore(tmp_path / "repo", "machine-b").record(
        _rejection("2026-08-03T09:00:00+00:00", machine_id="machine-b")
    )
    policy.record(
        _rejection(
            "2026-08-03T10:00:00+00:00", revives=TARGET_ID, suffix="R", scope="network"
        )
    )
    assert not policy.is_rejected(TARGET, OLD_CONTENT)


def test_a_revival_older_than_the_rejection_does_not_un_suppress(tmp_path):
    policy = _policy(tmp_path)
    SharedRejectionStore(tmp_path / "repo", "machine-b").record(
        _rejection("2026-08-03T10:00:00+00:00", machine_id="machine-b")
    )
    policy.record(
        _rejection(
            "2026-08-03T09:00:00+00:00", revives=TARGET_ID, suffix="R", scope="network"
        )
    )
    assert policy.is_rejected(TARGET, OLD_CONTENT)


def test_record_routes_to_the_store_matching_its_scope(tmp_path):
    policy = _policy(tmp_path)
    policy.record(_rejection("2026-08-03T09:00:00+00:00", scope="network"))
    assert (tmp_path / "repo" / "rejections" / "machine-a.json").exists()
    assert not (tmp_path / "local.json").exists()


def test_forget_reaches_every_store(tmp_path):
    policy = _policy(tmp_path)
    policy.record(_rejection("2026-08-03T09:00:00+00:00", scope="local"))
    policy.forget(TARGET_ID)
    assert not policy.is_rejected(TARGET, OLD_CONTENT)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rejection_composite.py -q`
Expected: FAIL with `ImportError: cannot import name 'CompositeRejectionPolicy'`

- [ ] **Step 3: Write minimal implementation**

Add `from typing import Protocol, runtime_checkable` to the imports, then append:

```python
@runtime_checkable
class RejectionPolicy(Protocol):
    """The only seam consumers depend on. One reason to change: what counts as
    rejected."""

    def is_rejected(self, target: RejectionTarget, source_timestamp: str) -> bool: ...

    def record(self, record: RejectionRecord) -> None: ...

    def forget(self, rejection_id: str) -> None: ...

    def all(self) -> list[RejectionRecord]: ...


class NullRejectionPolicy:
    """Rejects nothing. The explicit stand-in for "no ledger here", so callers
    never branch on a None policy."""

    def is_rejected(self, target: RejectionTarget, source_timestamp: str) -> bool:
        return False

    def record(self, record: RejectionRecord) -> None:
        raise NotImplementedError("NullRejectionPolicy is read-only")

    def forget(self, rejection_id: str) -> None:
        raise NotImplementedError("NullRejectionPolicy is read-only")

    def all(self) -> list[RejectionRecord]:
        return []


class CompositeRejectionPolicy:
    """Fans a query across stores. Callers cannot tell which store answered.

    Writes route by the record's own scope, so a local veto can never reach the
    shared repo by accident.
    """

    def __init__(self, stores: list, rule=None):
        self._stores = stores
        self._rule = rule if rule is not None else TimestampedRejectionRule()

    def all(self) -> list[RejectionRecord]:
        found: list[RejectionRecord] = []
        for store in self._stores:
            found.extend(store.all())
        return found

    def record(self, record: RejectionRecord) -> None:
        for store in self._stores:
            if store.scope == record.scope:
                store.record(record)
                return
        raise ValueError(f"no store for scope {record.scope!r}")

    def forget(self, rejection_id: str) -> None:
        for store in self._stores:
            store.forget(rejection_id)

    def is_rejected(self, target: RejectionTarget, source_timestamp: str) -> bool:
        target_id = rejection_id_of(target.kind, target.address)
        rejections = [
            found
            for found in self.all()
            if found.revives is None and found.id == target_id
        ]
        if not rejections:
            return False
        newest = max(rejections, key=lambda found: found.rejected_at)
        revivals = [
            found
            for found in self.all()
            if found.revives == target_id and found.rejected_at > newest.rejected_at
        ]
        if revivals:
            return False
        return self._rule.suppresses(newest, source_timestamp)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_rejection_composite.py -q`
Expected: 8 passed

- [ ] **Step 5: Format, lint, commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black scripts/config_sync_rejections.py tests/test_rejection_composite.py
uv run ruff check --fix scripts/config_sync_rejections.py tests/test_rejection_composite.py
uv run pytest tests/ -q
git add scripts/config_sync_rejections.py tests/test_rejection_composite.py
git commit -m "feat(config-sync): fan rejections across stores with revival precedence"
```

---

### Task 4: Snapshot addressors and the filter

**Files:**
- Modify: `scripts/config_sync_rejections.py`
- Test: `tests/test_rejection_addressors.py`

**Interfaces:**
- Consumes: `RejectionTarget`, `RejectionPolicy` from Tasks 1 and 3.
- Produces: `SnapshotFileAddressor` and `SnapshotSectionAddressor`, each with `kind: str`; `section_address(file_key: str, heading: str, occurrence: int) -> str`; `filter_snapshot_files(files: dict, policy, source_timestamp: str) -> tuple[dict, list[str]]` returning `(kept_files, removed_addresses)`.

Section identity is borrowed from `config_sync_merge._parse_sections`, which already returns `(heading, nth_occurrence)` keys that survive repeated headings. **Step 1 asserts the split/rejoin round-trip first** — every later behaviour depends on rejoining being lossless, so it is pinned before anything is built on it.

- [ ] **Step 1: Write the failing test**

```python
"""Addressing a snapshot file or one section of it, and subtracting rejections.

The round-trip test comes first deliberately: section removal rewrites a file by
splitting and rejoining it, so a lossy rejoin would corrupt every file it
touched. Pin that before building on it.
"""

import json

import config_sync_merge as merge
import config_sync_rejections as rejections
from config_sync_rejections import (
    NullRejectionPolicy,
    RejectionTarget,
    SnapshotFileAddressor,
    SnapshotSectionAddressor,
    filter_snapshot_files,
)

DOCUMENT = """preamble line

## Alpha

alpha body

## Beta

beta body

## Alpha

second alpha body
"""


class _RejectingPolicy:
    """Rejects exactly the addresses it was given. Substitutes for the real
    policy so addressing is tested without a ledger on disk."""

    def __init__(self, rejected_addresses):
        self._rejected = set(rejected_addresses)

    def is_rejected(self, target, source_timestamp):
        return target.address in self._rejected


def test_split_then_rejoin_is_lossless():
    assert rejections.rejoin_sections(merge._parse_sections(DOCUMENT)) == DOCUMENT


def test_section_address_round_trips_through_the_addressor():
    addressor = SnapshotSectionAddressor()
    address = rejections.section_address("CLAUDE.md", "## Beta", 0)
    assert addressor.matches(address, ("CLAUDE.md", "## Beta", 0))
    assert not addressor.matches(address, ("CLAUDE.md", "## Beta", 1))
    assert not addressor.matches(address, ("other.md", "## Beta", 0))


def test_section_address_is_json_so_headings_may_contain_any_character():
    address = rejections.section_address("CLAUDE.md", "## Weird # heading", 2)
    assert json.loads(address) == {
        "file": "CLAUDE.md",
        "heading": "## Weird # heading",
        "occurrence": 2,
    }


def test_file_addressor_uses_the_snapshot_key(tmp_path):
    addressor = SnapshotFileAddressor()
    assert addressor.identify("rules/a.md") == "rules/a.md"
    assert addressor.matches("rules/a.md", "rules/a.md")


def test_null_policy_leaves_every_file_untouched():
    files = {"CLAUDE.md": DOCUMENT, "rules/a.md": "keep me"}
    kept, removed = filter_snapshot_files(files, NullRejectionPolicy(), "2026-08-03T09:00:00+00:00")
    assert kept == files
    assert removed == []


def test_a_rejected_file_is_dropped_whole():
    files = {"CLAUDE.md": DOCUMENT, "rules/a.md": "drop me"}
    policy = _RejectingPolicy(["rules/a.md"])
    kept, removed = filter_snapshot_files(files, policy, "2026-08-03T09:00:00+00:00")
    assert set(kept) == {"CLAUDE.md"}
    assert removed == ["rules/a.md"]


def test_a_rejected_section_is_removed_and_the_rest_survives():
    policy = _RejectingPolicy([rejections.section_address("CLAUDE.md", "## Beta", 0)])
    kept, removed = filter_snapshot_files(
        {"CLAUDE.md": DOCUMENT}, policy, "2026-08-03T09:00:00+00:00"
    )
    assert "beta body" not in kept["CLAUDE.md"]
    assert "alpha body" in kept["CLAUDE.md"]
    assert "second alpha body" in kept["CLAUDE.md"]
    assert len(removed) == 1


def test_the_nth_repeated_heading_is_addressed_independently():
    policy = _RejectingPolicy([rejections.section_address("CLAUDE.md", "## Alpha", 1)])
    kept, _ = filter_snapshot_files({"CLAUDE.md": DOCUMENT}, policy, "2026-08-03T09:00:00+00:00")
    assert "alpha body" in kept["CLAUDE.md"]
    assert "second alpha body" not in kept["CLAUDE.md"]


def test_rejecting_every_section_leaves_an_empty_file_not_a_missing_one():
    every_address = [
        rejections.section_address("CLAUDE.md", heading_text, occurrence)
        for (heading_text, occurrence), _heading, _body in merge._parse_sections(DOCUMENT)
    ]
    kept, _ = filter_snapshot_files(
        {"CLAUDE.md": DOCUMENT}, _RejectingPolicy(every_address), "2026-08-03T09:00:00+00:00"
    )
    assert "CLAUDE.md" in kept
    assert kept["CLAUDE.md"].strip() == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rejection_addressors.py -q`
Expected: FAIL with `AttributeError: module 'config_sync_rejections' has no attribute 'rejoin_sections'`

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/config_sync_rejections.py`:

```python
def rejoin_sections(sections: list) -> str:
    """Inverse of `config_sync_merge._parse_sections`.

    That function stores a section's heading line separately from its body (the
    lines that followed it), so rejoining puts the heading back with the newline
    the split consumed. The preamble has no heading line to restore.
    """
    # Deferred import: config_sync_merge is a sibling script, not a package.
    import config_sync_merge as merge

    parts = []
    for _key, heading, body in sections:
        if heading == merge._PREAMBLE:
            parts.append(body)
        else:
            parts.append(heading + "\n" + body)
    return "".join(parts)


def section_address(file_key: str, heading: str, occurrence: int) -> str:
    """JSON rather than a delimited string: a heading may legitimately contain
    any character, including whatever separator a flat encoding would pick."""
    return json.dumps(
        {"file": file_key, "heading": heading, "occurrence": occurrence},
        sort_keys=True,
        ensure_ascii=False,
    )


class SnapshotFileAddressor:
    """A whole file in the snapshot, addressed by its own dict key."""

    kind = "snapshot-file"

    def identify(self, file_key: str) -> str:
        return file_key

    def matches(self, address: str, file_key: str) -> bool:
        return address == file_key


class SnapshotSectionAddressor:
    """One markdown section, addressed by (file, heading, nth occurrence) — the
    key `_parse_sections` already produces, so repeated headings stay distinct."""

    kind = "snapshot-section"

    def identify(self, unit) -> str:
        file_key, heading, occurrence = unit
        return section_address(file_key, heading, occurrence)

    def matches(self, address: str, unit) -> bool:
        return address == self.identify(unit)


def filter_snapshot_files(files: dict, policy, source_timestamp: str) -> tuple:
    """Subtract rejected files and sections from a snapshot `files` mapping.

    Returns `(kept_files, removed_addresses)`. A file whose every section is
    rejected is kept as empty rather than dropped — dropping it would be a
    *file* rejection the operator never asked for.
    """
    # Deferred import: config_sync_merge is a sibling script, not a package.
    import config_sync_merge as merge

    file_addressor = SnapshotFileAddressor()
    section_addressor = SnapshotSectionAddressor()
    kept: dict = {}
    removed: list = []

    for file_key, content in files.items():
        file_target = RejectionTarget(
            kind=file_addressor.kind, address=file_addressor.identify(file_key)
        )
        if policy.is_rejected(file_target, source_timestamp):
            removed.append(file_target.address)
            continue

        if not isinstance(content, str) or not file_key.endswith(".md"):
            kept[file_key] = content
            continue

        surviving_sections = []
        for (heading_text, occurrence), heading, body in merge._parse_sections(content):
            unit = (file_key, heading_text, occurrence)
            section_target = RejectionTarget(
                kind=section_addressor.kind, address=section_addressor.identify(unit)
            )
            if policy.is_rejected(section_target, source_timestamp):
                removed.append(section_target.address)
                continue
            surviving_sections.append(((heading_text, occurrence), heading, body))
        kept[file_key] = rejoin_sections(surviving_sections)

    return kept, removed
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_rejection_addressors.py -q`
Expected: 9 passed

If `test_split_then_rejoin_is_lossless` fails, fix `rejoin_sections` to match what `_parse_sections` actually stores before continuing — every other test in this task depends on it.

- [ ] **Step 5: Format, lint, commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black scripts/config_sync_rejections.py tests/test_rejection_addressors.py
uv run ruff check --fix scripts/config_sync_rejections.py tests/test_rejection_addressors.py
uv run pytest tests/ -q
git add scripts/config_sync_rejections.py tests/test_rejection_addressors.py
git commit -m "feat(config-sync): address snapshot files and sections, subtract rejections"
```

---

### Task 5: Break the ratchet in consolidate

**Files:**
- Modify: `scripts/config_sync.py` (`cmd_consolidate`, around lines 865-920)
- Test: `tests/test_consolidate_rejections.py`

**Interfaces:**
- Consumes: `filter_snapshot_files`, `CompositeRejectionPolicy`, `SharedRejectionStore`, `NullRejectionPolicy`.
- Produces: `network_rejection_policy(repo_dir, machine_id) -> CompositeRejectionPolicy`; `cmd_consolidate(repo_path, policy=None)` where `None` builds the network-only policy.

**This is the task the whole feature exists for.** `cmd_consolidate` seeds `base_files` from the prior consolidated snapshot, so content that ever entered it is immortal. Filtering the folded result is not enough — `base_files` must be filtered too.

`cmd_consolidate` is handed a **network-only** policy. Passing the composite here would let one machine's private veto strip content from shared state for everyone.

- [ ] **Step 1: Write the failing test**

```python
"""Consolidate must be able to forget.

The first test reproduces 2026-08-03 exactly: three machines were clean, and the
consolidated snapshot alone carried the superseded content. Anything that folds
`base_files` in without filtering it will pass every other test here and still
fail this one.
"""

import json

import config_sync
from config_sync_rejections import (
    RejectionRecord,
    SharedRejectionStore,
    rejection_id_of,
    section_address,
)

STALE = "## Memory protocol"
DOCUMENT = f"""# User Preferences

{STALE}

use the /memory skill
"""


def _repo(tmp_path, machine_files, consolidated_files):
    repo = tmp_path / "repo"
    (repo / "machines").mkdir(parents=True)
    (repo / "consolidated").mkdir(parents=True)
    for machine_id, files in machine_files.items():
        (repo / "machines" / f"{machine_id}.json").write_text(
            json.dumps(
                {
                    "machine_id": machine_id,
                    "timestamp": "2026-08-03T08:00:00+00:00",
                    "files": files,
                }
            ),
            encoding="utf-8",
        )
    (repo / "consolidated" / "snapshot.json").write_text(
        json.dumps({"machine_id": "consolidated", "files": consolidated_files}),
        encoding="utf-8",
    )
    return repo


def _reject(repo, address, kind="snapshot-section", rejected_at="2026-08-03T09:00:00+00:00"):
    SharedRejectionStore(repo, "machine-a").record(
        RejectionRecord(
            id=rejection_id_of(kind, address),
            kind=kind,
            address=address,
            scope="network",
            rejected_at=rejected_at,
            machine_id="machine-a",
        )
    )


def _consolidated(repo):
    return json.loads((repo / "consolidated" / "snapshot.json").read_text(encoding="utf-8"))


def test_content_carried_only_by_the_prior_consolidated_snapshot_is_stripped(tmp_path, capsys):
    repo = _repo(
        tmp_path,
        machine_files={"machine-a": {"CLAUDE.md": "# User Preferences\n"}},
        consolidated_files={"CLAUDE.md": DOCUMENT},
    )
    _reject(repo, section_address("CLAUDE.md", STALE, 0))

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert STALE not in _consolidated(repo)["files"]["CLAUDE.md"]


def test_an_empty_ledger_changes_nothing(tmp_path, capsys):
    repo = _repo(
        tmp_path,
        machine_files={"machine-a": {"CLAUDE.md": DOCUMENT}},
        consolidated_files={"CLAUDE.md": DOCUMENT},
    )
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()
    assert STALE in _consolidated(repo)["files"]["CLAUDE.md"]


def test_a_machine_re_adding_it_later_wins(tmp_path, capsys):
    repo = _repo(
        tmp_path,
        machine_files={"machine-b": {"CLAUDE.md": DOCUMENT}},
        consolidated_files={},
    )
    (repo / "machines" / "machine-b.json").write_text(
        json.dumps(
            {
                "machine_id": "machine-b",
                "timestamp": "2026-08-03T11:00:00+00:00",
                "files": {"CLAUDE.md": DOCUMENT},
            }
        ),
        encoding="utf-8",
    )
    _reject(repo, section_address("CLAUDE.md", STALE, 0), rejected_at="2026-08-03T09:00:00+00:00")

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert STALE in _consolidated(repo)["files"]["CLAUDE.md"]


def test_a_rejected_whole_file_never_reaches_the_consolidated_snapshot(tmp_path, capsys):
    repo = _repo(
        tmp_path,
        machine_files={"machine-a": {"rules/unwanted.md": "no thanks"}},
        consolidated_files={},
    )
    _reject(repo, "rules/unwanted.md", kind="snapshot-file")

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert "rules/unwanted.md" not in _consolidated(repo)["files"]


def test_a_local_scope_rejection_does_not_touch_shared_state(tmp_path, capsys):
    repo = _repo(
        tmp_path,
        machine_files={"machine-a": {"CLAUDE.md": DOCUMENT}},
        consolidated_files={},
    )
    address = section_address("CLAUDE.md", STALE, 0)
    SharedRejectionStore(repo, "machine-a").record(
        RejectionRecord(
            id=rejection_id_of("snapshot-section", address),
            kind="snapshot-section",
            address=address,
            scope="local",
            rejected_at="2026-08-03T09:00:00+00:00",
            machine_id="machine-a",
        )
    )

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert STALE in _consolidated(repo)["files"]["CLAUDE.md"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_consolidate_rejections.py -q`
Expected: FAIL — `test_content_carried_only_by_the_prior_consolidated_snapshot_is_stripped` finds `STALE` still present.

- [ ] **Step 3: Write minimal implementation**

In `scripts/config_sync.py`, add the policy builder near the other helpers:

```python
def network_rejection_policy(repo_dir, machine_id):
    """The policy `cmd_consolidate` uses: network scope ONLY.

    Consolidate writes shared state. A local veto leaking in here would impose
    one machine's private preference on every other machine, so the composite is
    deliberately not used at this call site.
    """
    import config_sync_rejections as rejections_module

    return rejections_module.CompositeRejectionPolicy(
        [rejections_module.SharedRejectionStore(Path(repo_dir), machine_id)]
    )
```

Then change `cmd_consolidate`'s signature and its two fold points:

```python
def cmd_consolidate(repo_path: str, policy=None):
    import config_sync_rejections as rejections_module

    repo = Path(repo_path)
    consolidated_path = repo / "consolidated" / "snapshot.json"
    machines_dir = repo / "machines"

    if policy is None:
        policy = network_rejection_policy(repo, _machine_id())

    snapshots = []
    if machines_dir.exists():
        for snapshot_file in sorted(machines_dir.glob("*.json")):
            snapshots.append(json.loads(snapshot_file.read_text(encoding="utf-8")))
    snapshots.sort(key=lambda snapshot: snapshot.get("timestamp", ""))

    if consolidated_path.exists():
        base_files = json.loads(consolidated_path.read_text(encoding="utf-8")).get(
            "files", {}
        )
    else:
        base_files = {}

    # The ratchet. `base_files` is the prior consolidated snapshot, which folds
    # its own output back in every run — so content that ever entered it is
    # immortal unless it is filtered HERE, not merely on the way in. Its own
    # timestamp is unknown and older than any live rejection by construction, so
    # the empty string reads as "no fresher intent".
    base_files, base_removed = rejections_module.filter_snapshot_files(
        base_files, policy, ""
    )
    rejected_addresses = list(base_removed)
```

Leave the existing `budget = _LlmMergeBudget(MAX_LLM_MERGES)` and `merge_log = []`
lines exactly where they are — the snippet above replaces only the lines it shows.

Then, inside the existing per-snapshot fold loop, filter each snapshot's files with that snapshot's own timestamp before merging:

```python
    for snapshot in snapshots:
        incoming_files, incoming_removed = rejections_module.filter_snapshot_files(
            snapshot.get("files", {}), policy, snapshot.get("timestamp", "")
        )
        rejected_addresses.extend(incoming_removed)
        base_files, log = _merge_snapshot_files(base_files, incoming_files, budget)
        merge_log.extend(log)
```

Add `"rejected": rejected_addresses` to both the written snapshot dict and the stdout payload, alongside the existing `"merge_log"` key.

Keep the `COMMANDS` entry at `("consolidate", cmd_consolidate, 1)` — `policy` is injected by tests, never from the CLI.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_consolidate_rejections.py -q`
Expected: 5 passed

Then confirm nothing regressed: `uv run pytest tests/ -q`

- [ ] **Step 5: Format, lint, commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black scripts/config_sync.py tests/test_consolidate_rejections.py
uv run ruff check --fix scripts/config_sync.py tests/test_consolidate_rejections.py
uv run pytest tests/ -q
git add scripts/config_sync.py tests/test_consolidate_rejections.py
git commit -m "fix(config-sync): let consolidate forget, breaking the base_files ratchet"
```

---

### Task 6: Local rejections at apply, and removal proposals

**Files:**
- Modify: `scripts/config_sync_propagators.py` (`SnapshotPropagator`, `ApplyResult`, `apply_propagators`)
- Modify: `scripts/config_sync.py` (`cmd_propagate_apply` payload)
- Test: `tests/test_snapshot_propagator_rejections.py`

**Interfaces:**
- Consumes: `NullRejectionPolicy`, `filter_snapshot_files`.
- Produces: `SnapshotPropagator(policy=None)` defaulting to `NullRejectionPolicy`; `ApplyResult.rejection_removals: list`; `apply_propagators(context=None)`.

- [ ] **Step 1: Write the failing test**

```python
"""A local veto withholds content from THIS machine without touching the repo."""

import json

from config_sync_propagators import SnapshotPropagator, SyncContext
from config_sync_rejections import (
    CompositeRejectionPolicy,
    LocalRejectionStore,
    RejectionRecord,
    rejection_id_of,
    section_address,
)

STALE = "## Memory protocol"
DOCUMENT = f"# User Preferences\n\n{STALE}\n\nuse the /memory skill\n"


def _context(tmp_path):
    context = SyncContext(claude_dir=tmp_path / "claude", repo_dir=tmp_path / "repo")
    (context.repo_dir / "consolidated").mkdir(parents=True)
    (context.repo_dir / "consolidated" / "snapshot.json").write_text(
        json.dumps({"files": {"CLAUDE.md": DOCUMENT}}), encoding="utf-8"
    )
    context.claude_dir.mkdir(parents=True, exist_ok=True)
    return context


def _local_policy(tmp_path, address, kind="snapshot-section"):
    store = LocalRejectionStore(tmp_path / "local.json")
    store.record(
        RejectionRecord(
            id=rejection_id_of(kind, address),
            kind=kind,
            address=address,
            scope="local",
            rejected_at="2026-08-03T09:00:00+00:00",
            machine_id="machine-a",
        )
    )
    return CompositeRejectionPolicy([store])


def test_without_a_policy_apply_behaves_exactly_as_before(tmp_path):
    context = _context(tmp_path)
    SnapshotPropagator().apply(context)
    assert STALE in (context.claude_dir / "CLAUDE.md").read_text(encoding="utf-8")


def test_a_locally_rejected_section_is_never_written(tmp_path):
    context = _context(tmp_path)
    policy = _local_policy(tmp_path, section_address("CLAUDE.md", STALE, 0))
    SnapshotPropagator(policy=policy).apply(context)
    written = (context.claude_dir / "CLAUDE.md").read_text(encoding="utf-8")
    assert STALE not in written
    assert "# User Preferences" in written


def test_the_shared_snapshot_is_left_untouched(tmp_path):
    context = _context(tmp_path)
    policy = _local_policy(tmp_path, section_address("CLAUDE.md", STALE, 0))
    SnapshotPropagator(policy=policy).apply(context)
    snapshot = json.loads(
        (context.repo_dir / "consolidated" / "snapshot.json").read_text(encoding="utf-8")
    )
    assert STALE in snapshot["files"]["CLAUDE.md"]


def test_removed_addresses_are_reported_for_the_operator(tmp_path):
    context = _context(tmp_path)
    address = section_address("CLAUDE.md", STALE, 0)
    result = SnapshotPropagator(policy=_local_policy(tmp_path, address)).apply(context)
    assert result.rejection_removals == [address]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_snapshot_propagator_rejections.py -q`
Expected: FAIL with `TypeError: SnapshotPropagator() takes no arguments`

- [ ] **Step 3: Write minimal implementation**

Add the field to `ApplyResult` (`config_sync_propagators.py:120`):

```python
@dataclass
class ApplyResult:
    propagator: str
    applied: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    deletions: list = field(default_factory=list)
    rejection_removals: list = field(default_factory=list)
```

Give `SnapshotPropagator` its injected policy and filter the snapshot before writing:

```python
class SnapshotPropagator:
    name = "snapshot"

    def __init__(self, policy=None):
        # Deferred: sibling script, not a package.
        import config_sync_rejections as rejections_module

        self._policy = (
            policy if policy is not None else rejections_module.NullRejectionPolicy()
        )
```

Inside `apply`, immediately after `files = snapshot.get("files", {})`:

```python
        import config_sync_rejections as rejections_module

        files, removed_addresses = rejections_module.filter_snapshot_files(
            files, self._policy, snapshot.get("timestamp", "")
        )
        result.rejection_removals.extend(removed_addresses)
```

Make the composition root build the real composite:

```python
def apply_propagators(context=None) -> list:
    """Composition root for the local-file apply sweep (Snapshot + ContentBundle).

    Apply writes LOCAL files only, so it is handed the COMPOSITE policy — both
    scopes are correct here, unlike `cmd_consolidate`, which writes shared state
    and gets a network-only policy.
    """
    if context is None:
        return [SnapshotPropagator(), ContentBundlePropagator()]

    import config_sync_rejections as rejections_module

    # `_machine_id(context)` from THIS module, never config_sync's argless one:
    # the context-injected variant honours the caller's claude_dir, so a test
    # cannot be made to read the operator's real ~/.claude.
    policy = rejections_module.CompositeRejectionPolicy(
        [
            rejections_module.LocalRejectionStore(
                context.claude_dir / "config-sync-rejections.json"
            ),
            rejections_module.SharedRejectionStore(
                context.repo_dir, _machine_id(context)
            ),
        ]
    )
    return [SnapshotPropagator(policy=policy), ContentBundlePropagator()]
```

In `config_sync.py`, pass the context (`propagators.apply_propagators(context)`) and add `"rejection_removals": result.rejection_removals` to `cmd_propagate_apply`'s payload dict.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_snapshot_propagator_rejections.py -q`
Expected: 4 passed

Then: `uv run pytest tests/ -q`

- [ ] **Step 5: Format, lint, commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black scripts/config_sync_propagators.py scripts/config_sync.py tests/test_snapshot_propagator_rejections.py
uv run ruff check --fix scripts/config_sync_propagators.py scripts/config_sync.py tests/test_snapshot_propagator_rejections.py
uv run pytest tests/ -q
git add scripts/config_sync_propagators.py scripts/config_sync.py tests/test_snapshot_propagator_rejections.py
git commit -m "feat(config-sync): withhold locally rejected content at apply"
```

---

### Task 7: The `reject`, `rejections` and `unreject` commands

**Files:**
- Modify: `scripts/config_sync.py`
- Test: `tests/test_rejection_cli.py`

**Interfaces:**
- Consumes: everything from Tasks 1-4.
- Produces: `cmd_reject(repo_path, *args)`, `cmd_rejections(repo_path)`, `cmd_unreject(repo_path, rejection_id)`; `COMMANDS` entries `"reject"`, `"rejections"`, `"unreject"`.

`reject` resolves its address against the current consolidated snapshot and **errors when nothing matches**, so a typo cannot sit in the ledger forever doing nothing.

- [ ] **Step 1: Write the failing test**

```python
"""The operator-facing surface: reject, list, undo."""

import json

import pytest

import config_sync
from config_sync_rejections import CorruptRejectionLedgerError  # noqa: F401

STALE = "## Memory protocol"
DOCUMENT = f"# User Preferences\n\n{STALE}\n\nuse the /memory skill\n"


def _repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "consolidated").mkdir(parents=True)
    (repo / "consolidated" / "snapshot.json").write_text(
        json.dumps({"files": {"CLAUDE.md": DOCUMENT, "rules/a.md": "hi"}}),
        encoding="utf-8",
    )
    return repo


def test_rejecting_a_section_records_it(tmp_path, capsys):
    repo = _repo(tmp_path)
    config_sync.cmd_reject(str(repo), "snapshot-section", "CLAUDE.md", "--section", STALE)
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "snapshot-section"
    assert payload["scope"] == "network"


def test_scope_defaults_to_network_and_local_is_selectable(tmp_path, capsys):
    repo = _repo(tmp_path)
    config_sync.cmd_reject(
        str(repo), "snapshot-file", "rules/a.md", "--scope", "local"
    )
    assert json.loads(capsys.readouterr().out)["scope"] == "local"


def test_an_address_matching_nothing_is_refused(tmp_path):
    repo = _repo(tmp_path)
    with pytest.raises(config_sync.UnknownRejectionTargetError):
        config_sync.cmd_reject(str(repo), "snapshot-file", "rules/nope.md")


def test_a_section_heading_matching_nothing_is_refused(tmp_path):
    repo = _repo(tmp_path)
    with pytest.raises(config_sync.UnknownRejectionTargetError):
        config_sync.cmd_reject(
            str(repo), "snapshot-section", "CLAUDE.md", "--section", "## Nope"
        )


def test_an_unknown_kind_is_refused(tmp_path):
    repo = _repo(tmp_path)
    with pytest.raises(ValueError):
        config_sync.cmd_reject(str(repo), "not-a-kind", "CLAUDE.md")


def test_rejections_lists_what_was_recorded(tmp_path, capsys):
    repo = _repo(tmp_path)
    config_sync.cmd_reject(str(repo), "snapshot-file", "rules/a.md")
    capsys.readouterr()
    config_sync.cmd_rejections(str(repo))
    listed = json.loads(capsys.readouterr().out)["rejections"]
    assert [entry["address"] for entry in listed] == ["rules/a.md"]


def test_unreject_removes_it(tmp_path, capsys):
    repo = _repo(tmp_path)
    config_sync.cmd_reject(str(repo), "snapshot-file", "rules/a.md")
    rejection_id = json.loads(capsys.readouterr().out)["id"]
    config_sync.cmd_unreject(str(repo), rejection_id)
    capsys.readouterr()
    config_sync.cmd_rejections(str(repo))
    assert json.loads(capsys.readouterr().out)["rejections"] == []


def test_the_commands_are_registered():
    for name in ("reject", "rejections", "unreject"):
        assert name in config_sync.COMMANDS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rejection_cli.py -q`
Expected: FAIL with `AttributeError: module 'config_sync' has no attribute 'cmd_reject'`

- [ ] **Step 3: Write minimal implementation**

In `scripts/config_sync.py`:

```python
class UnknownRejectionTargetError(RuntimeError):
    """A rejection address matches nothing in the consolidated snapshot.

    Refused rather than recorded: a typo'd address would otherwise sit in the
    ledger forever, suppressing nothing and explaining nothing.
    """


def _consolidated_files(repo_dir):
    path = Path(repo_dir) / "consolidated" / "snapshot.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("files", {})


def _resolve_rejection_address(repo_dir, kind, subject, section_heading, occurrence):
    """The address for `subject`, proven to exist in the consolidated snapshot."""
    import config_sync_merge as merge
    import config_sync_rejections as rejections_module

    files = _consolidated_files(repo_dir)
    if kind == "snapshot-file":
        if subject not in files:
            raise UnknownRejectionTargetError(
                f"no snapshot file {subject!r}; known files: {sorted(files)}"
            )
        return subject
    if kind == "snapshot-section":
        if subject not in files:
            raise UnknownRejectionTargetError(
                f"no snapshot file {subject!r}; known files: {sorted(files)}"
            )
        headings = [
            heading_text
            for (heading_text, _occurrence), _heading, _body in merge._parse_sections(
                files[subject]
            )
        ]
        if section_heading not in headings:
            raise UnknownRejectionTargetError(
                f"no section {section_heading!r} in {subject}; found: {headings}"
            )
        return rejections_module.section_address(subject, section_heading, occurrence)
    raise ValueError(f"kind {kind!r} is not addressable in phase 1")


def cmd_reject(repo_path, *args):
    import config_sync_rejections as rejections_module

    kind = args[0] if args else ""
    if kind not in rejections_module.REJECTION_KINDS:
        raise ValueError(
            f"unknown kind {kind!r}; expected one of {rejections_module.REJECTION_KINDS}"
        )
    subject = args[1]
    options = list(args[2:])

    def option(name, default=None):
        return options[options.index(name) + 1] if name in options else default

    scope = option("--scope", "network")
    if scope not in rejections_module.REJECTION_SCOPES:
        raise ValueError(f"unknown scope {scope!r}")
    section_heading = option("--section")
    occurrence = int(option("--occurrence", "0"))
    reason = option("--reason", "")

    address = _resolve_rejection_address(
        repo_path, kind, subject, section_heading, occurrence
    )
    record = rejections_module.RejectionRecord(
        id=rejections_module.rejection_id_of(kind, address),
        kind=kind,
        address=address,
        scope=scope,
        rejected_at=datetime.now(UTC).isoformat(),
        machine_id=_machine_id(),
        reason=reason,
    )
    _rejection_policy(repo_path).record(record)
    print(json.dumps(vars(record), indent=2, ensure_ascii=False))


def _rejection_policy(repo_path):
    """Composition root for the rejection commands: both scopes, since the
    operator chooses per rejection."""
    import config_sync_rejections as rejections_module

    return rejections_module.CompositeRejectionPolicy(
        [
            rejections_module.LocalRejectionStore(
                Path.home() / ".claude" / "config-sync-rejections.json"
            ),
            rejections_module.SharedRejectionStore(Path(repo_path), _machine_id()),
        ]
    )


def cmd_rejections(repo_path):
    records = _rejection_policy(repo_path).all()
    print(
        json.dumps(
            {"rejections": [vars(record) for record in records]},
            indent=2,
            ensure_ascii=False,
        )
    )


def cmd_unreject(repo_path, rejection_id):
    _rejection_policy(repo_path).forget(rejection_id)
    print(json.dumps({"unrejected": rejection_id}))
```

Register them in `COMMANDS`:

```python
    "reject": (cmd_reject, None),  # variadic: repo kind subject [--scope|--section|...]
    "rejections": (cmd_rejections, 1),
    "unreject": (cmd_unreject, 2),
```

And add the ledger error to the `main()` except clause so a corrupt ledger exits 2 like the other named refusals:

```python
    import config_sync_rejections

    try:
        fn(*args[1:])
    except (
        config_sync_hooks.CorruptSettingsError,
        config_sync_plugins.CorruptPluginStateError,
        config_sync_rejections.CorruptRejectionLedgerError,
        UnknownRejectionTargetError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)
```

In the test, `LocalRejectionStore` points at the real `~/.claude`. Add a fixture at the top of `tests/test_rejection_cli.py` that redirects it:

```python
@pytest.fixture(autouse=True)
def _isolate_home(tmp_path, monkeypatch):
    """Never let a test write the operator's real ~/.claude ledger."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "home")
    (tmp_path / "home" / ".claude").mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_rejection_cli.py -q`
Expected: 8 passed

Then: `uv run pytest tests/ -q`

- [ ] **Step 5: Write the failing test for the mass-rejection guard**

The spec refuses a rejection that would empty a whole file unless forced, reusing
the `_guard_mass_deletion` stance at `config_sync_propagators.py:505`. The guard
belongs **here**, at the consent surface — `filter_snapshot_files` stays total and
always returns a result, because a pure filter that raises is a filter that cannot
be used to preview anything.

Append to `tests/test_rejection_cli.py`:

```python
SINGLE_SECTION = "## Only\n\nthe only thing here\n"


def _repo_with_single_section_file(tmp_path):
    repo = tmp_path / "repo2"
    (repo / "consolidated").mkdir(parents=True)
    (repo / "consolidated" / "snapshot.json").write_text(
        json.dumps({"files": {"solo.md": SINGLE_SECTION}}), encoding="utf-8"
    )
    return repo


def test_a_rejection_that_would_empty_a_file_is_refused(tmp_path):
    repo = _repo_with_single_section_file(tmp_path)
    with pytest.raises(config_sync.MassRejectionRefusedError):
        config_sync.cmd_reject(str(repo), "snapshot-section", "solo.md", "--section", "## Only")


def test_force_overrides_the_mass_rejection_guard(tmp_path, capsys):
    repo = _repo_with_single_section_file(tmp_path)
    config_sync.cmd_reject(
        str(repo), "snapshot-section", "solo.md", "--section", "## Only", "--force"
    )
    assert json.loads(capsys.readouterr().out)["address"]


def test_rejecting_one_of_several_sections_is_not_guarded(tmp_path, capsys):
    repo = _repo(tmp_path)
    config_sync.cmd_reject(str(repo), "snapshot-section", "CLAUDE.md", "--section", STALE)
    assert json.loads(capsys.readouterr().out)["id"]
```

- [ ] **Step 6: Run test to verify it fails**

Run: `uv run pytest tests/test_rejection_cli.py -q`
Expected: FAIL with `AttributeError: module 'config_sync' has no attribute 'MassRejectionRefusedError'`

- [ ] **Step 7: Implement the guard**

```python
class MassRejectionRefusedError(RuntimeError):
    """A rejection would leave a snapshot file with no content at all.

    Refused rather than performed, mirroring `_guard_mass_deletion`: emptying a
    whole file is a *file* rejection, and the operator asked for a section one.
    `--force` says they meant it.
    """
```

In `cmd_reject`, read `--force` as a flag (`force = "--force" in options`) and, for
`snapshot-section` only, refuse before recording:

```python
    if kind == "snapshot-section" and not force:
        import config_sync_merge as merge

        remaining = [
            heading_text
            for (heading_text, _occurrence), _heading, _body in merge._parse_sections(
                _consolidated_files(repo_path)[subject]
            )
            if heading_text != section_heading
        ]
        if not any(heading.strip() for heading in remaining):
            raise MassRejectionRefusedError(
                f"rejecting {section_heading!r} would empty {subject}; "
                f"pass --force, or reject the file with kind snapshot-file"
            )
```

Add `MassRejectionRefusedError` to the `main()` except clause alongside
`UnknownRejectionTargetError`.

- [ ] **Step 8: Run test to verify it passes**

Run: `uv run pytest tests/test_rejection_cli.py -q`
Expected: 11 passed

Then: `uv run pytest tests/ -q`

- [ ] **Step 9: Format, lint, commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black scripts/config_sync.py tests/test_rejection_cli.py
uv run ruff check --fix scripts/config_sync.py tests/test_rejection_cli.py
uv run pytest tests/ -q
git add scripts/config_sync.py tests/test_rejection_cli.py
git commit -m "feat(config-sync): add reject, rejections and unreject commands"
```

---

### Task 8: `resolve-rejection` — the other machine's gate

**Files:**
- Modify: `scripts/config_sync.py`
- Test: `tests/test_resolve_rejection.py`

**Interfaces:**
- Consumes: `_rejection_policy`, `RejectionRecord`, `rejection_id_of`.
- Produces: `cmd_resolve_rejection(repo_path, rejection_id, decision)` where `decision` is `remove` or `keep`; `COMMANDS` entry `"resolve-rejection"`.

`keep` cannot delete another machine's record — that file belongs to them. It writes **this** machine's revival record with a newer timestamp, which Task 3's precedence rule resolves.

- [ ] **Step 1: Write the failing test**

```python
"""One machine overruling another's rejection, without writing their file."""

import json

import pytest

import config_sync
from config_sync_rejections import (
    RejectionRecord,
    SharedRejectionStore,
    rejection_id_of,
)

ADDRESS = "rules/a.md"
REJECTION_ID = rejection_id_of("snapshot-file", ADDRESS)


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "home")
    (tmp_path / "home" / ".claude").mkdir(parents=True, exist_ok=True)


def _repo_with_foreign_rejection(tmp_path):
    repo = tmp_path / "repo"
    SharedRejectionStore(repo, "machine-b").record(
        RejectionRecord(
            id=REJECTION_ID,
            kind="snapshot-file",
            address=ADDRESS,
            scope="network",
            rejected_at="2026-08-03T09:00:00+00:00",
            machine_id="machine-b",
        )
    )
    return repo


def test_keep_writes_a_revival_into_this_machines_own_file(tmp_path, capsys):
    repo = _repo_with_foreign_rejection(tmp_path)
    config_sync.cmd_resolve_rejection(str(repo), REJECTION_ID, "keep")
    capsys.readouterr()
    own = json.loads(
        (repo / "rejections" / f"{config_sync._machine_id()}.json").read_text(
            encoding="utf-8"
        )
    )
    assert own["rejections"][0]["revives"] == REJECTION_ID


def test_keep_leaves_the_other_machines_file_untouched(tmp_path, capsys):
    repo = _repo_with_foreign_rejection(tmp_path)
    before = (repo / "rejections" / "machine-b.json").read_text(encoding="utf-8")
    config_sync.cmd_resolve_rejection(str(repo), REJECTION_ID, "keep")
    capsys.readouterr()
    assert (repo / "rejections" / "machine-b.json").read_text(encoding="utf-8") == before


def test_remove_records_the_local_decision_without_a_revival(tmp_path, capsys):
    repo = _repo_with_foreign_rejection(tmp_path)
    config_sync.cmd_resolve_rejection(str(repo), REJECTION_ID, "remove")
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "remove"
    assert not (repo / "rejections" / f"{config_sync._machine_id()}.json").exists()


def test_an_unknown_decision_is_refused(tmp_path):
    repo = _repo_with_foreign_rejection(tmp_path)
    with pytest.raises(ValueError):
        config_sync.cmd_resolve_rejection(str(repo), REJECTION_ID, "maybe")


def test_an_unknown_rejection_id_is_refused(tmp_path):
    repo = _repo_with_foreign_rejection(tmp_path)
    with pytest.raises(config_sync.UnknownRejectionTargetError):
        config_sync.cmd_resolve_rejection(str(repo), "notarealid00", "keep")


def test_the_command_is_registered():
    assert "resolve-rejection" in config_sync.COMMANDS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_resolve_rejection.py -q`
Expected: FAIL with `AttributeError: module 'config_sync' has no attribute 'cmd_resolve_rejection'`

- [ ] **Step 3: Write minimal implementation**

```python
def cmd_resolve_rejection(repo_path, rejection_id, decision):
    """Answer another machine's rejection: remove the content here, or keep it.

    `keep` does NOT delete the original — that record lives in the rejecting
    machine's own file and is not ours to edit. It writes our own revival record
    with a newer timestamp, which the composite policy resolves in our favour.
    """
    import config_sync_rejections as rejections_module

    if decision not in ("remove", "keep"):
        raise ValueError(f"decision must be 'remove' or 'keep', got {decision!r}")

    policy = _rejection_policy(repo_path)
    original = next(
        (found for found in policy.all() if found.id == rejection_id), None
    )
    if original is None:
        raise UnknownRejectionTargetError(f"no rejection with id {rejection_id!r}")

    if decision == "keep":
        revival = rejections_module.RejectionRecord(
            id=rejections_module.rejection_id_of(
                original.kind, original.address + "\0revival"
            ),
            kind=original.kind,
            address=original.address,
            scope="network",
            rejected_at=datetime.now(UTC).isoformat(),
            machine_id=_machine_id(),
            reason=f"kept on {_machine_id()}",
            revives=rejection_id,
        )
        policy.record(revival)

    print(
        json.dumps(
            {"resolved": rejection_id, "decision": decision, "address": original.address}
        )
    )
```

Register it:

```python
    "resolve-rejection": (cmd_resolve_rejection, 3),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_resolve_rejection.py -q`
Expected: 6 passed

Then: `uv run pytest tests/ -q`

- [ ] **Step 5: Format, lint, commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black scripts/config_sync.py tests/test_resolve_rejection.py
uv run ruff check --fix scripts/config_sync.py tests/test_resolve_rejection.py
uv run pytest tests/ -q
git add scripts/config_sync.py tests/test_resolve_rejection.py
git commit -m "feat(config-sync): let a machine overrule a network rejection via revival"
```

---

### Task 9: Wire it into the sync cycle documentation

**Files:**
- Modify: `skills/config-sync/SKILL.md`
- Test: `tests/test_rejection_skill_docs.py`

**Interfaces:**
- Consumes: the command names from Tasks 7 and 8.
- Produces: no code. The SKILL is what an operator actually reads, so a command nobody documents is a command nobody runs.

- [ ] **Step 1: Write the failing test**

```python
"""The SKILL must teach the commands the engine now exposes.

This repo already tests SKILL structure elsewhere; a documented command that
does not exist, or an existing command nobody documents, is the failure mode.
"""

from pathlib import Path

import config_sync

SKILL = Path(__file__).resolve().parents[1] / "skills" / "config-sync" / "SKILL.md"


def test_every_new_command_is_documented():
    text = SKILL.read_text(encoding="utf-8")
    for command in ("reject", "rejections", "unreject", "resolve-rejection"):
        assert command in text, f"{command} is not documented in SKILL.md"


def test_documented_commands_exist_in_the_engine():
    for command in ("reject", "rejections", "unreject", "resolve-rejection"):
        assert command in config_sync.COMMANDS


def test_the_summary_block_reports_rejections():
    assert "Rejected" in SKILL.read_text(encoding="utf-8")


def test_the_union_only_warning_no_longer_claims_deletions_are_impossible():
    text = SKILL.read_text(encoding="utf-8")
    assert "resurrected" in text
    assert "`reject`" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rejection_skill_docs.py -q`
Expected: FAIL — `reject is not documented in SKILL.md`

- [ ] **Step 3: Write the documentation**

In `skills/config-sync/SKILL.md`:

1. In **Step 4**, after the bundle-deletion resolution paragraph, add:

```markdown
**Reject content you never want (if any).** For any proposal the user declines,
offer a third answer beyond apply/skip: reject it durably. Ask with
**AskUserQuestion** whether the rejection is for this machine only or for the
whole network, then record it:

```bash
# scope is `local` (this machine only) or `network` (tombstone for everyone)
py "$ENGINE" reject "$REPO" snapshot-section CLAUDE.md --section "## Memory protocol" --scope network
py "$ENGINE" reject "$REPO" snapshot-file rules/unwanted.md --scope local
```

A rejection is timestamped: content re-added *later* than the rejection is
proposed again as fresh intent. Review or undo with `py "$ENGINE" rejections "$REPO"`
and `py "$ENGINE" unreject "$REPO" <id>`.
```

2. Update the union-only warning in **Step 3** to:

```markdown
> **Bundle deletions propagate; config deletions need `reject`.** Skill/agent
> **bundles** carry deletion tombstones. **Snapshot config** (CLAUDE.md,
> `memory/`, `rules/`) is union-only, so a deletion alone is *resurrected* from
> another machine's snapshot — and from the consolidated snapshot itself, which
> folds its own prior output back in. To retire config content, `reject` it:
> `--scope network` strips it from the consolidated snapshot and prompts every
> other machine, `--scope local` withholds it here without touching shared state.
```

3. Add a new **Step 4e — Answer other machines' rejections** after Step 4d:

```markdown
## Step 4e — Answer other machines' rejections

`propagate-apply` reports a `rejection_removals` list: content this machine holds
that another machine has rejected network-wide. For each entry, ask with
**AskUserQuestion** ("`<address>` was rejected on `<machine>` at `<time>` — remove
it here, or keep it?") and apply the answer:

```bash
py "$ENGINE" resolve-rejection "$REPO" <id> remove   # delete it locally
py "$ENGINE" resolve-rejection "$REPO" <id> keep     # overrule: it returns for everyone
```

`keep` does not edit the rejecting machine's file. It records this machine's own
newer revival, which wins on timestamp — so one machine can always overrule the
network without a cross-machine write.
```

4. In **Step 7**, add `Rejected : <N> item(s) rejected (or "none")` to the summary block.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_rejection_skill_docs.py -q`
Expected: 4 passed

Then the full suite: `uv run pytest tests/ -q`

- [ ] **Step 5: Commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black tests/test_rejection_skill_docs.py
uv run ruff check --fix tests/test_rejection_skill_docs.py
uv run pytest tests/ -q
git add skills/config-sync/SKILL.md tests/test_rejection_skill_docs.py
git commit -m "docs(config-sync): teach the sync cycle to reject and resolve rejections"
```

---

## Verification

After Task 9, prove the original defect is gone against a scratch repo:

```bash
cd /tmp && rm -rf reject-check && mkdir -p reject-check/{machines,consolidated}
cd reject-check
printf '{"machine_id":"m1","timestamp":"2026-08-03T08:00:00+00:00","files":{"CLAUDE.md":"# Prefs\\n"}}' > machines/m1.json
printf '{"files":{"CLAUDE.md":"# Prefs\\n\\n## Stale\\n\\nold text\\n"}}' > consolidated/snapshot.json

ENGINE=/Users/ai/Projects/mente-apex-plugin/scripts/config_sync.py
python3 "$ENGINE" reject . snapshot-section CLAUDE.md --section "## Stale" --scope network
python3 "$ENGINE" consolidate .
python3 - <<'PY'
import json
snapshot = json.load(open("consolidated/snapshot.json"))
stale_present = "## Stale" in snapshot["files"]["CLAUDE.md"]
print("STILL PRESENT - FAIL" if stale_present else "stripped - PASS")
PY
```

A bare `grep -q "## Stale" consolidated/snapshot.json` cannot be used here: `consolidate`
writes the `rejected` audit trail into the same snapshot file as the content, and the
rejection's own address embeds the heading text (`{"file": "CLAUDE.md", "heading": "##
Stale", ...}`), so a whole-file grep matches that audit-trail entry even when the section
was correctly stripped from `files.CLAUDE.md` — a false "STILL PRESENT" on a working
implementation. Inspecting `.files["CLAUDE.md"]` specifically is what actually proves the
defect is gone.

Expected: `stripped - PASS`. Before this plan, the same check prints `STILL PRESENT`.

## Phase 2

`settings-key`, `hook-registration` (three identity tiers in
`scripts/config_sync_rejection_hooks.py`), and `plugin` with `plugins-plan`
filtering are a separate plan. Nothing in phase 1 assumes those kinds exist —
`REJECTION_KINDS` already names them, and `_resolve_rejection_address` raises
`ValueError` for anything it cannot yet address, which is the seam phase 2 extends.
