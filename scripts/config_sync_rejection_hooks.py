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


def _same_site(left, right) -> bool:
    """Identity by position in the hooks block, not by command — two entries can
    carry the same command and still be different registrations."""
    return (
        left.event == right.event
        and left.group_index == right.group_index
        and left.hook_index == right.hook_index
    )
