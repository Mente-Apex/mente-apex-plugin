"""Durable "I have seen this and I do not want it" decisions for pulled config.

DIP: consumers depend only on the RejectionPolicy protocol; concrete stores and
addressors are injected. See
docs/superpowers/specs/2026-08-03-config-sync-rejection-ledger-design.md.
"""

from __future__ import annotations

import hashlib
import json
import os
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


@runtime_checkable
class SuppressionRule(Protocol):
    """Whether a rejection still applies to content arriving now.

    The seam `CompositeRejectionPolicy` depends on, so "what counts as fresh
    intent" can change without touching the policy. One reason to change.
    """

    def suppresses(self, record: RejectionRecord, source_timestamp: str) -> bool: ...


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
    """Write atomically: temp file in the same directory, then `os.replace`.

    Reads are deliberately fail-closed (`CorruptRejectionLedgerError`), so a
    write interrupted midway — Ctrl-C, a full disk, a crash — would leave a
    truncated ledger that aborts both `consolidate` and `apply` on every
    subsequent run until someone repairs it by hand. `os.replace` is atomic
    within a filesystem, and the temp file is created beside the target
    precisely to keep it on that filesystem.

    The temp name ends in `.tmp`, not `.json`, so a crash between write and
    replace cannot leave a file that `SharedRejectionStore.all()`'s `*.json`
    glob would pick up as a real ledger.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"rejections": [vars(record) for record in records]}
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    os.replace(temp_path, path)


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

    def __init__(self, stores: list, rule: SuppressionRule | None = None):
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
        # Bound ONCE. `all()` re-reads every ledger file on the shared store, and
        # `cmd_consolidate` asks this question per file and per section, per
        # machine — two calls here meant hundreds of redundant file reads per
        # fold.
        records = self.all()
        target_id = rejection_id_of(target.kind, target.address)
        rejections = [
            found
            for found in records
            if found.revives is None and found.id == target_id
        ]
        if not rejections:
            return False
        newest = max(rejections, key=lambda found: found.rejected_at)
        revivals = [
            found
            for found in records
            if found.revives == target_id and found.rejected_at > newest.rejected_at
        ]
        if revivals:
            return False
        return self._rule.suppresses(newest, source_timestamp)


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


def records_for_addresses(policy, addresses: list) -> list[RejectionRecord]:
    """Resolve removed addresses back to the ledger records that suppressed them.

    Deliberately NOT folded into `filter_snapshot_files`: subtracting rejected
    content from a snapshot and explaining why it went are two reasons to
    change. The filter stays a pure filter returning addresses; this maps those
    addresses to the records an operator needs in order to answer — `id` is what
    `resolve-rejection` takes, `machine_id` and `rejected_at` are what the
    prompt shows, and `scope` distinguishes another machine's network tombstone
    from this machine's own local veto.

    Matched on `address` alone because an address is all the filter reports.
    Revival records are skipped: a revival is an overrule, never the reason
    something was withheld. Where several records share an address the newest
    wins, mirroring `CompositeRejectionPolicy.is_rejected`. Output order follows
    `addresses`, deduplicated — the same address can be removed from more than
    one place in one pass.
    """
    wanted = set(addresses)
    newest_by_address: dict = {}
    for record in policy.all():
        if record.revives is not None or record.address not in wanted:
            continue
        previous = newest_by_address.get(record.address)
        if previous is None or record.rejected_at > previous.rejected_at:
            newest_by_address[record.address] = record

    resolved: list[RejectionRecord] = []
    already_seen: set = set()
    for address in addresses:
        if address in already_seen:
            continue
        already_seen.add(address)
        found = newest_by_address.get(address)
        if found is not None:
            resolved.append(found)
    return resolved


def filter_snapshot_files(files: dict, policy, source_timestamp: str) -> tuple:
    """Subtract rejected files and sections from a snapshot `files` mapping.

    Returns `(kept_files, removed_addresses)`. A file whose every section is
    rejected is kept as empty rather than dropped — dropping it would be a
    *file* rejection the operator never asked for.

    A file with no rejected section is passed through as the original
    `content` object, never round-tripped through `_parse_sections` and
    `rejoin_sections`. That round-trip is not lossless for every input: a
    document ending in a bodiless heading with no trailing newline (e.g.
    `"## Foo"`) gains a spurious `"\n"` on rejoin, because `_parse_sections`
    strips the heading line's own newline and relies on trailing content to
    supply it back — content that a bodiless final heading doesn't have. Since
    `_parse_sections` is not injective for that shape (`"## Foo"` and
    `"## Foo\n"` parse identically), no rejoin logic can recover which one was
    the input; the only fix that is exact for every untouched file is to never
    rewrite what nothing rejected.
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
        any_section_was_rejected = False
        for (heading_text, occurrence), heading, body in merge._parse_sections(content):
            unit = (file_key, heading_text, occurrence)
            section_target = RejectionTarget(
                kind=section_addressor.kind, address=section_addressor.identify(unit)
            )
            if policy.is_rejected(section_target, source_timestamp):
                removed.append(section_target.address)
                any_section_was_rejected = True
                continue
            surviving_sections.append(((heading_text, occurrence), heading, body))

        if any_section_was_rejected:
            kept[file_key] = rejoin_sections(surviving_sections)
        else:
            kept[file_key] = content

    return kept, removed


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
