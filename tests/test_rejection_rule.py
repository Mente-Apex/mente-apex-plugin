"""The rule that decides whether a rejection still bites.

A re-add must be STRICTLY newer than the rejection to count as fresh intent;
equal timestamps let the rejection win. That boundary is the whole rule, so it
is asserted directly rather than inferred from a higher-level behaviour.
"""

import config_sync_rejections as rejections
from config_sync_rejections import RejectionRecord, TimestampedRejectionRule


def _record(rejected_at):
    return RejectionRecord(
        id="abc123def456",
        kind="snapshot-section",
        address="CLAUDE.md",
        scope="network",
        rejected_at=rejected_at,
        machine_id="machine-a",
    )


def test_content_older_than_the_rejection_is_suppressed():
    rule = TimestampedRejectionRule()
    assert rule.suppresses(
        _record("2026-08-03T09:00:00+00:00"), "2026-08-03T08:00:00+00:00"
    )


def test_content_strictly_newer_than_the_rejection_is_fresh_intent():
    rule = TimestampedRejectionRule()
    assert not rule.suppresses(
        _record("2026-08-03T09:00:00+00:00"), "2026-08-03T11:00:00+00:00"
    )


def test_equal_timestamps_let_the_rejection_win():
    rule = TimestampedRejectionRule()
    same = "2026-08-03T09:00:00+00:00"
    assert rule.suppresses(_record(same), same)


def test_missing_source_timestamp_is_suppressed_rather_than_guessed():
    rule = TimestampedRejectionRule()
    assert rule.suppresses(_record("2026-08-03T09:00:00+00:00"), "")


def test_rejection_id_is_stable_over_kind_and_address_only():
    first = rejections.rejection_id_of("snapshot-file", "rules/a.md")
    second = rejections.rejection_id_of("snapshot-file", "rules/a.md")
    assert first == second
    assert first != rejections.rejection_id_of("snapshot-section", "rules/a.md")


def test_rejection_id_cannot_be_forged_across_the_field_boundary():
    assert rejections.rejection_id_of("ab", "c") != rejections.rejection_id_of(
        "a", "bc"
    )
