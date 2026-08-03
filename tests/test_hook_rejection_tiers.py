"""One address per tier, computed from a hook site.

Tier selection is Task 5's job; this pins only that each tier computes the
address it promises, and that a tier which cannot apply says so with None rather
than inventing something.
"""

from config_sync_hooks import HookSite
from config_sync_rejection_hooks import (
    HOOK_TIER_EXACT,
    HOOK_TIER_MARKER,
    HOOK_TIER_SCRIPT,
    hook_address_at_tier,
)

MARKED = HookSite(
    event="PreToolUse",
    group_index=0,
    hook_index=0,
    matcher="Bash",
    command="/abs/bin/py /abs/scripts/enforce_gates.py  # config-sync:abc123def456",
)
UNMARKED = HookSite(
    event="PreToolUse",
    group_index=0,
    hook_index=1,
    matcher="Bash",
    command="python3 /other/place/enforce_gates.py",
)
OPAQUE = HookSite(
    event="SessionStart",
    group_index=0,
    hook_index=0,
    matcher="",
    command="echo hello && exit 0",
)


def test_tier_1_reads_the_marker():
    assert hook_address_at_tier(MARKED, HOOK_TIER_MARKER) == "hooks/abc123def456"


def test_tier_1_is_unavailable_without_a_marker():
    assert hook_address_at_tier(UNMARKED, HOOK_TIER_MARKER) is None


def test_tier_2_is_event_matcher_and_script_basename():
    assert (
        hook_address_at_tier(UNMARKED, HOOK_TIER_SCRIPT)
        == "hooks/PreToolUse/Bash/enforce_gates.py"
    )


def test_tier_2_ignores_the_interpreter_and_the_directory():
    """The whole point: these two differ only in interpreter and path."""
    assert hook_address_at_tier(MARKED, HOOK_TIER_SCRIPT) == hook_address_at_tier(
        UNMARKED, HOOK_TIER_SCRIPT
    )


def test_tier_2_is_unavailable_for_a_command_with_no_script():
    assert hook_address_at_tier(OPAQUE, HOOK_TIER_SCRIPT) is None


def test_tier_3_hashes_the_marker_stripped_command():
    address = hook_address_at_tier(MARKED, HOOK_TIER_EXACT)
    assert address.startswith("hooks/PreToolUse/Bash/#")
    assert len(address.rsplit("#", 1)[1]) == 12


def test_tier_3_ignores_the_marker_so_marking_a_hook_does_not_move_it():
    unmarked_twin = HookSite(
        event="PreToolUse",
        group_index=0,
        hook_index=0,
        matcher="Bash",
        command="/abs/bin/py /abs/scripts/enforce_gates.py",
    )
    assert hook_address_at_tier(MARKED, HOOK_TIER_EXACT) == hook_address_at_tier(
        unmarked_twin, HOOK_TIER_EXACT
    )


def test_tier_3_distinguishes_two_same_named_scripts_from_different_paths():
    assert hook_address_at_tier(MARKED, HOOK_TIER_EXACT) != hook_address_at_tier(
        UNMARKED, HOOK_TIER_EXACT
    )


def test_tier_3_is_always_available():
    assert hook_address_at_tier(OPAQUE, HOOK_TIER_EXACT) is not None


def test_an_unknown_tier_is_refused_rather_than_guessed():
    import pytest

    with pytest.raises(ValueError):
        hook_address_at_tier(MARKED, 99)
