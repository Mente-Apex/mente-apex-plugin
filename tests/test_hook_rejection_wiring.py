"""A rejected hook is never wired, and an already-wired one is left alone.

Rejection withholds; it never deletes. `hooks-prune` removes what is already
registered — the two compose rather than compete.
"""

from config_sync_hooks import DeclaredHook, plan_hook_wiring
from config_sync_rejection_hooks import HookRegistrationAddressor
from config_sync_rejections import (
    CompositeRejectionPolicy,
    LocalRejectionStore,
    NullRejectionPolicy,
    RejectionRecord,
    rejection_id_of,
)

REJECTED_AT = "2026-08-03T09:00:00+00:00"

DECLARED = DeclaredHook(
    hook_id="aaaaaaaaaaaa",
    event="PreToolUse",
    matcher="Bash",
    command="${ROOT}/scripts/unwanted.py",
    timeout=None,
)
KEPT = DeclaredHook(
    hook_id="bbbbbbbbbbbb",
    event="PreToolUse",
    matcher="Bash",
    command="${ROOT}/scripts/wanted.py",
    timeout=None,
)


def _localize(command):
    return command.replace("${ROOT}", "/abs/root")


def _policy(tmp_path, address, tier):
    store = LocalRejectionStore(tmp_path / "local.json")
    store.record(
        RejectionRecord(
            id=rejection_id_of("hook-registration", address),
            kind="hook-registration",
            address=address,
            scope="local",
            rejected_at=REJECTED_AT,
            machine_id="machine-a",
            tier=str(tier),
        )
    )
    return CompositeRejectionPolicy([store])


def _address_of(declared):
    """The address the operator would have recorded, seen from settings."""
    from config_sync_hooks import HookSite

    site = HookSite(
        event=declared.event,
        group_index=0,
        hook_index=0,
        matcher=declared.matcher,
        command=_localize(declared.command),
    )
    return HookRegistrationAddressor().identify(site, [site])


def _marked_address_of(declared):
    """The tier-1 address of a declaration that is ALREADY wired by config-sync.

    A managed hook's live command carries its `# config-sync:<id>` marker, so the
    operator rejecting it records a tier-1 (marker) address. The planner must
    still recognise the declaration that would re-wire it, whose own command is
    pre-marker.
    """
    from config_sync_hooks import HookSite, marker_for

    site = HookSite(
        event=declared.event,
        group_index=0,
        hook_index=0,
        matcher=declared.matcher,
        command=_localize(declared.command) + " " + marker_for(declared.hook_id),
    )
    return HookRegistrationAddressor().identify(site, [site])


def test_a_marker_tier_rejection_is_enforced_against_the_declaration(tmp_path):
    """The tier-1 case: a config-sync-managed hook rejected from its MARKED live
    command must not be re-wired by the planner."""
    address, tier = _marked_address_of(DECLARED)
    assert (address, tier) == ("hooks/aaaaaaaaaaaa", 1)
    plan = plan_hook_wiring(
        [DECLARED, KEPT],
        {},
        localize=_localize,
        policy=_policy(tmp_path, address, tier),
    )
    assert {action.hook_id for action in plan.actions} == {"bbbbbbbbbbbb"}


def test_without_a_policy_every_declaration_is_planned():
    plan = plan_hook_wiring([DECLARED, KEPT], {}, localize=_localize)
    assert {action.hook_id for action in plan.actions} == {
        "aaaaaaaaaaaa",
        "bbbbbbbbbbbb",
    }


def test_a_rejected_declaration_is_not_registered(tmp_path):
    address, tier = _address_of(DECLARED)
    plan = plan_hook_wiring(
        [DECLARED, KEPT],
        {},
        localize=_localize,
        policy=_policy(tmp_path, address, tier),
    )
    assert {action.hook_id for action in plan.actions} == {"bbbbbbbbbbbb"}


def test_the_rejected_declaration_is_reported_as_skipped(tmp_path):
    address, tier = _address_of(DECLARED)
    plan = plan_hook_wiring(
        [DECLARED, KEPT],
        {},
        localize=_localize,
        policy=_policy(tmp_path, address, tier),
    )
    assert any(
        "unwanted.py" in str(entry) or "rejected" in str(entry)
        for entry in plan.skipped
    )


def test_the_null_policy_plans_exactly_what_it_did_before():
    with_null = plan_hook_wiring(
        [DECLARED, KEPT], {}, localize=_localize, policy=NullRejectionPolicy()
    )
    without = plan_hook_wiring([DECLARED, KEPT], {}, localize=_localize)
    assert [action.hook_id for action in with_null.actions] == [
        action.hook_id for action in without.actions
    ]


def test_an_already_registered_rejected_hook_is_not_deleted(tmp_path):
    """Rejection withholds; removal is hooks-prune's job. The settings block the
    planner was handed must come back untouched."""
    address, tier = _address_of(DECLARED)
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {"type": "command", "command": "/abs/root/scripts/unwanted.py"}
                    ],
                }
            ]
        }
    }
    before = dict(settings)
    plan_hook_wiring(
        [DECLARED],
        settings,
        localize=_localize,
        policy=_policy(tmp_path, address, tier),
    )
    assert settings == before
