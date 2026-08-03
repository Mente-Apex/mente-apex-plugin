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

    raise ValueError(
        f"unknown hook identity tier {tier!r}; expected one of {HOOK_TIERS}"
    )
