"""One address per tier, and the selection of a tier, computed from a hook site.

The first half pins that each tier computes the address it promises, and that a
tier which cannot apply says so with None rather than inventing something. The
second half pins tier SELECTION: most stable first, falling downward to the more
specific tier on ambiguity, and never guessing between two matches.
"""

from config_sync_hooks import HookSite
from config_sync_rejection_hooks import (
    HOOK_TIER_EXACT,
    HOOK_TIER_MARKER,
    HOOK_TIER_SCRIPT,
    HookRegistrationAddressor,
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


TWIN_A = HookSite(
    event="PreToolUse",
    group_index=0,
    hook_index=0,
    matcher="Bash",
    command="python3 /Users/ai/.claude/mente-apex/enforce_gates.py",
)
TWIN_B = HookSite(
    event="PreToolUse",
    group_index=0,
    hook_index=1,
    matcher="Bash",
    command="python3 /Users/ai/Projects/mente-apex-memory/enforce_gates.py",
)
IDENTICAL_A = HookSite(
    event="Stop", group_index=0, hook_index=0, matcher="", command="run.sh"
)
IDENTICAL_B = HookSite(
    event="Stop", group_index=0, hook_index=1, matcher="", command="run.sh"
)


def test_a_marked_hook_resolves_to_tier_1():
    addressor = HookRegistrationAddressor()
    address, tier = addressor.identify(MARKED, [MARKED, UNMARKED])
    assert tier == HOOK_TIER_MARKER
    assert address == "hooks/abc123def456"


def test_an_unmarked_hook_with_a_unique_script_resolves_to_tier_2():
    addressor = HookRegistrationAddressor()
    address, tier = addressor.identify(UNMARKED, [UNMARKED, OPAQUE])
    assert tier == HOOK_TIER_SCRIPT
    assert address == "hooks/PreToolUse/Bash/enforce_gates.py"


def test_two_same_named_scripts_under_one_event_and_matcher_fall_to_tier_3():
    """The live enforce_gates.py case: tier 2 is ambiguous, tier 3 is not."""
    addressor = HookRegistrationAddressor()
    address_a, tier_a = addressor.identify(TWIN_A, [TWIN_A, TWIN_B])
    address_b, tier_b = addressor.identify(TWIN_B, [TWIN_A, TWIN_B])
    assert tier_a == tier_b == HOOK_TIER_EXACT
    assert address_a != address_b


def test_the_same_script_name_under_a_different_matcher_is_not_ambiguous():
    """Tier 2 is scoped BY event and matcher — a same-named script elsewhere is
    a different registration, not a collision."""
    elsewhere = HookSite(
        event="PreToolUse",
        group_index=1,
        hook_index=0,
        matcher="Write",
        command="python3 /somewhere/enforce_gates.py",
    )
    addressor = HookRegistrationAddressor()
    _address, tier = addressor.identify(UNMARKED, [UNMARKED, elsewhere])
    assert tier == HOOK_TIER_SCRIPT


def test_a_marked_hook_is_unaffected_by_a_tier_2_collision():
    """Tier 1 is checked first, so a marker wins even when the basename clashes."""
    addressor = HookRegistrationAddressor()
    _address, tier = addressor.identify(MARKED, [MARKED, TWIN_A, TWIN_B])
    assert tier == HOOK_TIER_MARKER


def test_two_byte_identical_registrations_share_one_address_rather_than_refusing():
    """Indistinguishable by construction, and an exact duplicate is precisely what
    one wants gone — so they are rejected together rather than refused."""
    addressor = HookRegistrationAddressor()
    address_a, tier_a = addressor.identify(IDENTICAL_A, [IDENTICAL_A, IDENTICAL_B])
    address_b, tier_b = addressor.identify(IDENTICAL_B, [IDENTICAL_A, IDENTICAL_B])
    assert tier_a == tier_b == HOOK_TIER_EXACT
    assert address_a == address_b


def test_an_opaque_command_resolves_to_tier_3():
    addressor = HookRegistrationAddressor()
    _address, tier = addressor.identify(OPAQUE, [OPAQUE])
    assert tier == HOOK_TIER_EXACT


def test_identify_refuses_a_site_that_is_not_among_the_sites_given():
    import pytest

    addressor = HookRegistrationAddressor()
    with pytest.raises(ValueError):
        addressor.identify(OPAQUE, [MARKED, UNMARKED])


def test_identify_refuses_a_stranger_that_only_shares_an_event():
    """Membership is POSITIONAL, not by event. A site whose event and matcher
    match a block it is not actually in must still be refused, or a stranger
    would resolve its ambiguity against registrations it is not among."""
    import pytest

    addressor = HookRegistrationAddressor()
    stranger = HookSite(
        event=MARKED.event,
        group_index=99,
        hook_index=99,
        matcher=MARKED.matcher,
        command=MARKED.command,
    )
    with pytest.raises(ValueError):
        addressor.identify(stranger, [MARKED])


def test_matches_recomputes_only_the_recorded_tier():
    addressor = HookRegistrationAddressor()
    address, tier = addressor.identify(UNMARKED, [UNMARKED])
    relocated = HookSite(
        event="PreToolUse",
        group_index=7,
        hook_index=3,
        matcher="Bash",
        command="/new/uv/bin/python /completely/different/enforce_gates.py",
    )
    assert addressor.matches(address, tier, relocated)


def test_a_tier_2_address_does_not_match_a_different_script():
    addressor = HookRegistrationAddressor()
    address, tier = addressor.identify(UNMARKED, [UNMARKED])
    other = HookSite(
        event="PreToolUse",
        group_index=0,
        hook_index=0,
        matcher="Bash",
        command="python3 /somewhere/other_script.py",
    )
    assert not addressor.matches(address, tier, other)


def test_a_tier_2_address_does_not_match_under_a_different_matcher():
    addressor = HookRegistrationAddressor()
    address, tier = addressor.identify(UNMARKED, [UNMARKED])
    elsewhere = HookSite(
        event="PreToolUse",
        group_index=0,
        hook_index=0,
        matcher="Write",
        command="python3 /somewhere/enforce_gates.py",
    )
    assert not addressor.matches(address, tier, elsewhere)


def test_a_tier_3_address_stops_matching_once_the_command_changes():
    """Deliberate: tier 3 is the exact-match floor. The operator rejected one
    specific command, so a changed command is a different registration."""
    addressor = HookRegistrationAddressor()
    address, tier = addressor.identify(OPAQUE, [OPAQUE])
    changed = HookSite(
        event="SessionStart",
        group_index=0,
        hook_index=0,
        matcher="",
        command="echo hello && exit 1",
    )
    assert addressor.matches(address, tier, OPAQUE)
    assert not addressor.matches(address, tier, changed)


def test_a_tier_1_address_survives_everything_but_losing_the_marker():
    addressor = HookRegistrationAddressor()
    address, tier = addressor.identify(MARKED, [MARKED])
    moved = HookSite(
        event="Stop",
        group_index=4,
        hook_index=1,
        matcher="Other",
        command="/anything/at/all.sh  # config-sync:abc123def456",
    )
    unmarked_now = HookSite(
        event="PreToolUse",
        group_index=0,
        hook_index=0,
        matcher="Bash",
        command="/abs/bin/py /abs/scripts/enforce_gates.py",
    )
    assert addressor.matches(address, tier, moved)
    assert not addressor.matches(address, tier, unmarked_now)


def test_matching_a_tier_that_cannot_apply_is_false_not_an_error():
    addressor = HookRegistrationAddressor()
    address, tier = addressor.identify(UNMARKED, [UNMARKED])
    assert not addressor.matches(address, tier, OPAQUE)
