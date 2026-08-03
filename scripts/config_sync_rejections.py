"""Durable "I have seen this and I do not want it" decisions for pulled config.

DIP: consumers depend only on the RejectionPolicy protocol; concrete stores and
addressors are injected. See
docs/superpowers/specs/2026-08-03-config-sync-rejection-ledger-design.md.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

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
