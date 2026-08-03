"""Addressing one key inside settings.json, and subtracting rejected keys.

A settings key path is a LIST in JSON, not a delimited string: `permissions.allow`
would be indistinguishable from a literal top-level key named `permissions.allow`,
and plugin ids legitimately contain `@` and `-`.
"""

import json

import config_sync_rejections as rejections
from config_sync_rejections import (
    NullRejectionPolicy,
    SettingsKeyAddressor,
    filter_settings_keys,
)

SETTINGS = {
    "permissions": {"defaultMode": "acceptEdits", "allow": ["Bash(ls:*)"]},
    "enabledPlugins": {"open-memory@open-memory": True, "keep-me@keep-me": True},
    "model": "opus",
}


class _RejectingPolicy:
    """Rejects exactly the addresses it was given. Substitutes for the real policy
    so addressing is tested without a ledger on disk."""

    def __init__(self, rejected_addresses):
        self._rejected = set(rejected_addresses)

    def is_rejected(self, target, source_timestamp):
        return target.address in self._rejected


def test_a_key_path_is_json_so_a_key_may_contain_any_character():
    address = rejections.settings_key_address(
        ("enabledPlugins", "open-memory@open-memory")
    )
    assert json.loads(address) == ["enabledPlugins", "open-memory@open-memory"]


def test_a_dotted_key_is_not_confused_with_a_nested_path():
    nested = rejections.settings_key_address(("permissions", "defaultMode"))
    literal = rejections.settings_key_address(("permissions.defaultMode",))
    assert nested != literal


def test_the_addressor_round_trips_a_key_path():
    addressor = SettingsKeyAddressor()
    address = addressor.identify(("permissions", "defaultMode"))
    assert addressor.matches(address, ("permissions", "defaultMode"))
    assert not addressor.matches(address, ("permissions", "allow"))
    assert addressor.kind == "settings-key"


def test_null_policy_leaves_settings_untouched():
    kept, removed = filter_settings_keys(
        SETTINGS, NullRejectionPolicy(), "2026-08-03T09:00:00+00:00"
    )
    assert kept == SETTINGS
    assert removed == []


def test_a_rejected_leaf_is_removed_and_its_siblings_survive():
    address = rejections.settings_key_address(("permissions", "defaultMode"))
    kept, removed = filter_settings_keys(
        SETTINGS, _RejectingPolicy([address]), "2026-08-03T09:00:00+00:00"
    )
    assert "defaultMode" not in kept["permissions"]
    assert kept["permissions"]["allow"] == ["Bash(ls:*)"]
    assert removed == [address]


def test_a_rejected_subtree_takes_its_children_with_it():
    address = rejections.settings_key_address(("permissions",))
    kept, _removed = filter_settings_keys(
        SETTINGS, _RejectingPolicy([address]), "2026-08-03T09:00:00+00:00"
    )
    assert "permissions" not in kept
    assert kept["model"] == "opus"


def test_rejecting_one_plugin_entry_leaves_the_others():
    address = rejections.settings_key_address(
        ("enabledPlugins", "open-memory@open-memory")
    )
    kept, _removed = filter_settings_keys(
        SETTINGS, _RejectingPolicy([address]), "2026-08-03T09:00:00+00:00"
    )
    assert kept["enabledPlugins"] == {"keep-me@keep-me": True}


def test_the_input_dict_is_never_mutated():
    address = rejections.settings_key_address(("model",))
    before = json.dumps(SETTINGS, sort_keys=True)
    filter_settings_keys(
        SETTINGS, _RejectingPolicy([address]), "2026-08-03T09:00:00+00:00"
    )
    assert json.dumps(SETTINGS, sort_keys=True) == before


def test_a_rejected_key_that_is_absent_is_not_reported_as_removed():
    address = rejections.settings_key_address(("notPresent",))
    kept, removed = filter_settings_keys(
        SETTINGS, _RejectingPolicy([address]), "2026-08-03T09:00:00+00:00"
    )
    assert kept == SETTINGS
    assert removed == []
