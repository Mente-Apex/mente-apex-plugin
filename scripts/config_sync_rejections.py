"""Durable "I have seen this and I do not want it" decisions for pulled config.

DIP: consumers depend only on the RejectionPolicy protocol; concrete stores and
addressors are injected. See
docs/superpowers/specs/2026-08-03-config-sync-rejection-ledger-design.md.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

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
    try:
        return [_record_from(entry) for entry in payload.get("rejections", [])]
    except (KeyError, TypeError, AttributeError) as exc:
        raise CorruptRejectionLedgerError(
            f"{path} has a malformed rejection entry: {exc}"
        ) from exc


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
    shared repo by accident. Reads honour scope too: a record only counts when
    its own `scope` matches the store it came from, so a local-scoped record
    that ended up sitting in a shared-repo file (an older client, a hand edit,
    a bad merge) is never honoured by a network-only policy. That boundary is
    a correctness property, not a preference — see
    docs/superpowers/specs/2026-08-03-config-sync-rejection-ledger-design.md:115.
    """

    def __init__(self, stores: list, rule=None):
        self._stores = stores
        self._rule = rule if rule is not None else TimestampedRejectionRule()

    def all(self) -> list[RejectionRecord]:
        found: list[RejectionRecord] = []
        for store in self._stores:
            found.extend(
                record for record in store.all() if record.scope == store.scope
            )
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
