"""When each addressable unit of a snapshot last changed.

Its own module because this is a different reason to change than "what is
addressable" (`config_sync_rejections.iter_addressable_units`) or "what is
rejected" (the policy). The engine's rejection rule asks whether incoming
content is strictly newer than the rejection; before this existed the only
answer available was the export's wall clock, so unchanged content re-exported
as newer and resurrected.

See docs/superpowers/specs/2026-08-04-config-sync-content-provenance-design.md.
"""

from __future__ import annotations

import hashlib


def hash_payload(payload: str) -> str:
    """A content hash for one addressable unit.

    sha1 is not a security boundary here -- this only answers "is this
    byte-for-byte what we saw last export?" -- but the blast radius of a
    collision is not free either, and the two directions are NOT symmetric. A
    restamp (`_previous_changed_at` answering None) costs at most one avoidable
    resurrection. A collision is the other direction: genuinely changed content
    would carry an old `changed_at` forward, so a re-add the operator meant
    would read as older than the rejection and stay withheld -- the wrong
    suppression `_previous_changed_at` is written never to cause.

    sha1 stays anyway, matching `config_sync_rejections.rejection_id_of` and
    `config_sync_hooks.hook_id_of`: reaching that case needs an adversarially
    constructed pair of config files, which is not a threat model for content
    this machine wrote itself.
    """
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


class ContentProvenanceStamper:
    """Decides each unit's `changed_at` by comparing hashes against the machine's
    previous export.

    Pure by construction: `now` is injected rather than read, nothing is written,
    and `previous` is never mutated. One reason to change: the rule for deciding
    that a unit changed.
    """

    def stamp(self, files: dict, previous: dict, now: str) -> dict:
        """The provenance map for `files`, carrying `changed_at` forward wherever
        the content hash still matches `previous`.

        Shape: `{kind: {address: {"changed_at": str, "hash": str}}}`. A unit
        absent from `files` drops out -- deletion propagation belongs to
        `BundleDeletionLedger`, not here.
        """
        # Deferred import: config_sync_rejections is a sibling script, not a package.
        import config_sync_rejections as rejections_module

        stamped: dict = {}
        for unit in rejections_module.iter_addressable_units(files):
            digest = hash_payload(unit.payload)
            carried = _previous_changed_at(previous, unit.kind, unit.address, digest)
            stamped.setdefault(unit.kind, {})[unit.address] = {
                "changed_at": carried if carried is not None else now,
                "hash": digest,
            }
        return stamped


def _previous_changed_at(previous, kind: str, address: str, digest: str):
    """The recorded `changed_at` for this unit if its hash is unchanged, else None.

    Anything malformed answers None, which restamps. Restamping is the
    conservative direction: it can cost one avoidable resurrection, never a
    wrong suppression.
    """
    if not isinstance(previous, dict):
        return None
    by_address = previous.get(kind)
    if not isinstance(by_address, dict):
        return None
    entry = by_address.get(address)
    if not isinstance(entry, dict):
        return None
    if entry.get("hash") != digest:
        return None
    changed_at = entry.get("changed_at")
    return changed_at if isinstance(changed_at, str) and changed_at else None
